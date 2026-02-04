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

    for item in doc.items:
        _validate_item_qty(project, item.item_code, item.qty, doc.name)


def _validate_item_qty(project, item_code, po_qty, po_name):
    """
    Validate individual item quantity against Component Master limit.
    Only enforces for "Buy" items — "Make" items are not directly procured.

    Args:
        project: Project name
        item_code: Item code
        po_qty: Ordered quantity in this PO
        po_name: PO document name (excluded from existing qty calculation)
    """
    component = frappe.db.get_value(
        "Project Component Master",
        {"project": project, "item_code": item_code},
        [
            "name", "total_qty_limit", "total_qty_procured",
            "is_loose_item", "bom_qty_required", "project_qty",
            "make_or_buy",
        ],
        as_dict=True,
    )

    if not component:
        return  # Item not in Component Master, no restriction

    # Only validate "Buy" items — "Make" items are assembled in-house
    if component.make_or_buy and component.make_or_buy != "Buy":
        return  # Make items are not directly procured, skip validation

    if not component.total_qty_limit:
        return  # No limit set

    # Get existing PO quantities (exclude current PO if updating)
    # Sum all non-cancelled POs for this project + item
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
    max_allowed = max(0, component.total_qty_limit - existing_po_qty)

    # Hard limit check
    if total_procurement > component.total_qty_limit:
        frappe.throw(
            _(
                "Cannot add {0} units of {1} to Purchase Order.<br><br>"
                "<b>Procurement Limit Exceeded:</b><br>"
                "<table class='table table-bordered' style='width:auto;margin-top:10px'>"
                "<tr><td>Total Limit:</td><td style='text-align:right'><b>{2}</b></td></tr>"
                "<tr><td>Existing POs:</td><td style='text-align:right'>{3}</td></tr>"
                "<tr><td>This PO:</td><td style='text-align:right'>{4}</td></tr>"
                "<tr class='text-danger'><td>Total:</td><td style='text-align:right'><b>{5}</b></td></tr>"
                "<tr class='text-success'><td>Max Allowed:</td><td style='text-align:right'><b>{6}</b></td></tr>"
                "</table>"
                "<br><small><i class='fa fa-info-circle'></i> "
                "Update quantity limit in Project Component Master <b>{7}</b> if needed</small>"
            ).format(
                po_qty,
                frappe.bold(item_code),
                component.total_qty_limit,
                existing_po_qty,
                po_qty,
                total_procurement,
                max_allowed,
                component.name,
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
