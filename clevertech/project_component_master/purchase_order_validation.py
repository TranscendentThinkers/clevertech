"""
Purchase Order Quantity Validation for Project Component Master

Validates PO quantities against Component Master total_qty_limit.
Hard block (frappe.throw) if quantity exceeds limit.
Provides second layer of enforcement after MR validation (defense in depth).
"""

import frappe
from frappe import _


def validate_purchase_order_qty(doc, method=None):
    """
    Validate PO quantities against Project Component Master limits.
    Hook: Purchase Order validate event.

    Only enforces limits for "Buy" items (items that are actually procured).
    "Make" items are assembled in-house and don't need PO validation.

    Skips silently if no project is set on the PO.
    Handles cases where:
    - POs are created directly without MRs
    - PO quantities are manually edited after creation
    - Multiple POs exceed the limit
    """
    # Purchase Order uses standard 'project' field
    project = doc.get("project")
    if not project:
        return  # No project, skip validation

    # Bug Fix 2026-02-09: Build cost_center → machine_code lookup cache
    # PO doesn't have header-level machine_code, derive from item cost_center
    cost_center_to_machine = {}

    for item in doc.items:
        machine_code = None
        if item.cost_center:
            if item.cost_center not in cost_center_to_machine:
                # Cache the lookup to avoid N+1 queries
                cost_center_to_machine[item.cost_center] = frappe.db.get_value(
                    "Cost Center", item.cost_center, "custom_machine_code"
                )
            machine_code = cost_center_to_machine[item.cost_center]

        # Decision 20 (2026-02-10): Get bom_no from source MR item if available
        bom_no = None
        if item.material_request_item:
            bom_no = frappe.db.get_value(
                "Material Request Item", item.material_request_item, "bom_no"
            )

        _validate_item_qty(project, item.item_code, item.qty, doc.name, machine_code, bom_no)


def _validate_item_qty(project, item_code, po_qty, po_name, machine_code=None, bom_no=None):
    """
    Validate individual item quantity against Component Master limit.
    Only enforces for "Buy" items — "Make" items are not directly procured.

    Decision 20 (2026-02-10): G-code level validation
    - If PO item traces back to MR with bom_no, validate against G-code aggregate limit
    - Otherwise, validate against CM-level total_qty_limit

    Args:
        project: Project name
        item_code: Item code
        po_qty: Ordered quantity in this PO
        po_name: PO document name (excluded from existing qty calculation)
        machine_code: Machine code for filtering (Bug Fix 2026-02-09)
        bom_no: BOM reference (traced from source MR item) (Decision 20)
    """
    # Bug Fix 2026-02-09: Add machine_code filter to prevent cross-machine CM collision
    # When item exists in multiple machines, pick the correct CM for this machine
    filters = {"project": project, "item_code": item_code}
    if machine_code:
        filters["machine_code"] = machine_code

    component = frappe.db.get_value(
        "Project Component Master",
        filters,
        [
            "name", "total_qty_limit", "total_qty_procured",
            "is_loose_item", "bom_qty_required", "project_qty",
            "make_or_buy",
        ],
        as_dict=True,
    )

    if not component:
        return  # Item not in Component Master, no restriction (old projects)

    # Block "Make" items — they are assembled in-house, not procured
    if component.make_or_buy == "Make":
        frappe.throw(
            _(
                "Cannot add {0} to Purchase Order.<br><br>"
                "<b>Item is marked as 'Make' in Project Component Master</b><br><br>"
                "'Make' items are assembled in-house from their child components. "
                "Only the child parts (marked as 'Buy') should be procured.<br><br>"
                "<small><i class='fa fa-info-circle'></i> "
                "If this item should be purchased, update Make/Buy flag in "
                "<a href='/app/project-component-master/{1}'>{1}</a></small>"
            ).format(
                frappe.bold(item_code),
                component.name,
            ),
            title=_("Cannot Procure 'Make' Item"),
        )

    # Bug Fix 2026-02-09: Removed total_qty_limit early return check
    # Both 0 and NULL should block procurement (0 = parent is Buy, NULL = not calculated)
    # Only items without Component Master (old projects) skip validation

    # Decision 20 (2026-02-10): G-code level validation
    # If PO traces back to MR with bom_no, validate against G-code-specific limit
    qty_limit = component.total_qty_limit or 0
    validation_context = "overall limit"

    if bom_no:
        # Extract G-code from BOM's item field
        g_code_item = frappe.db.get_value("BOM", bom_no, "item")

        if g_code_item:
            # Load Component Master with bom_usage child table
            cm_doc = frappe.get_doc("Project Component Master", component.name)

            # Sum total_qty_required for all bom_usage rows matching this G-code
            g_code_limit = sum(
                row.total_qty_required or 0
                for row in cm_doc.bom_usage
                if row.g_code == g_code_item
            )

            if g_code_limit > 0:
                qty_limit = g_code_limit
                validation_context = f"G-code {g_code_item}"

    # Get existing PO quantities (exclude current PO if updating)
    # Bug Fix 2026-02-09: Filter by machine_code to prevent cross-machine contamination
    # Sum all non-cancelled POs for this project + item + machine
    if machine_code:
        existing_po_qty = frappe.db.sql(
            """
            SELECT COALESCE(SUM(poi.qty), 0)
            FROM `tabPurchase Order Item` poi
            INNER JOIN `tabPurchase Order` po ON poi.parent = po.name
            LEFT JOIN `tabCost Center` cc ON poi.cost_center = cc.name
            WHERE po.project = %s
              AND poi.item_code = %s
              AND cc.custom_machine_code = %s
              AND po.docstatus < 2
              AND po.name != %s
            """,
            (project, item_code, machine_code, po_name or ""),
        )[0][0] or 0
    else:
        # Fallback: no machine filtering (old POs without cost_center)
        existing_po_qty = frappe.db.sql(
            """
            SELECT COALESCE(SUM(poi.qty), 0)
            FROM `tabPurchase Order Item` poi
            INNER JOIN `tabPurchase Order` po ON poi.parent = po.name
            WHERE po.project = %s
              AND poi.item_code = %s
              AND po.docstatus < 2
              AND po.name != %s
            """,
            (project, item_code, po_name or ""),
        )[0][0] or 0

    total_procurement = existing_po_qty + po_qty
    max_allowed = max(0, qty_limit - existing_po_qty)

    # Hard limit check
    if total_procurement > qty_limit:
        frappe.throw(
            _(
                "Cannot add {0} units of {1} to Purchase Order.<br><br>"
                "<b>Procurement Limit Exceeded ({8}):</b><br>"
                "<table class='table table-bordered' style='width:auto;margin-top:10px'>"
                "<tr><td>Total Limit:</td><td style='text-align:right'><b>{2}</b></td></tr>"
                "<tr><td>Existing POs:</td><td style='text-align:right'>{3}</td></tr>"
                "<tr><td>This PO:</td><td style='text-align:right'>{4}</td></tr>"
                "<tr class='text-danger'><td>Total:</td><td style='text-align:right'><b>{5}</b></td></tr>"
                "<tr class='text-success'><td>Max Allowed:</td><td style='text-align:right'><b>{6}</b></td></tr>"
                "</table>"
                "<br><small><i class='fa fa-info-circle'></i> "
                "Update quantity limit in Component Master "
                "<a href='/app/project-component-master/{7}' target='_blank'><b>{7}</b></a> if needed</small>"
            ).format(
                po_qty,
                frappe.bold(item_code),
                qty_limit,
                existing_po_qty,
                po_qty,
                total_procurement,
                max_allowed,
                component.name,
                validation_context,
            ),
            title=_("Procurement Limit Exceeded"),
        )

    # Info message for loose items with manual project_qty
    if component.is_loose_item and component.project_qty:
        bom_qty = component.bom_qty_required or 0
        project_qty = component.project_qty or 0

        if project_qty > bom_qty and total_procurement > bom_qty:
            frappe.msgprint(
                _(
                    "<div class='alert alert-info'>"
                    "<i class='fa fa-info-circle'></i> <b>Note:</b> "
                    "Item {0} is a loose item. BOM requires <b>{1} units</b> "
                    "but project qty is set to <b>{2} units</b>. "
                    "Current PO adds <b>{3} units</b> (Total limit: <b>{4}</b>)"
                    "</div>"
                ).format(
                    frappe.bold(item_code),
                    bom_qty,
                    project_qty,
                    po_qty,
                    component.total_qty_limit,
                ),
                indicator="blue",
                title=_("Loose Item Procurement Info"),
            )
