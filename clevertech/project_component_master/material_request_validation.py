"""
Material Request Quantity Validation for Project Component Master

Validates MR quantities against Component Master total_qty_limit.
Hard block (frappe.throw) if quantity exceeds limit.
Warning for loose item over-procurement.
"""

import frappe
from frappe import _


def validate_material_request_qty(doc, method=None):
    """
    Validate MR quantities against Project Component Master limits.
    Hook: Material Request validate event.

    Only enforces limits for "Buy" items (items that are actually procured).
    "Make" items are assembled in-house and don't need MR validation.

    Skips silently if no project is set on the MR.
    """
    # Material Request uses custom_project_ field (with trailing underscore)
    project = doc.get("custom_project_")
    if not project:
        return  # No project, skip validation

    for item in doc.items:
        _validate_item_qty(project, item.item_code, item.qty, doc.name)


def _validate_item_qty(project, item_code, mr_qty, mr_name):
    """
    Validate individual item quantity against Component Master limit.
    Only enforces for "Buy" items — "Make" items are not directly procured.

    Args:
        project: Project name
        item_code: Item code
        mr_qty: Requested quantity in this MR
        mr_name: MR document name (excluded from existing qty calculation)
    """
    component = frappe.db.get_value(
        "Project Component Master",
        {"project": project, "item_code": item_code},
        [
            "name", "total_qty_limit", "total_qty_procured",
            "is_loose_item", "loose_qty_required", "bom_qty_required",
            "bom_conversion_status", "make_or_buy",
        ],
        as_dict=True,
    )

    if not component:
        return  # Item not in Component Master, no restriction

    # Block "Make" items — they are assembled in-house, not procured
    if component.make_or_buy == "Make":
        frappe.throw(
            _(
                "Cannot add {0} to Material Request.<br><br>"
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

    if not component.total_qty_limit:
        return  # No limit set

    # Get existing MR quantities (exclude current MR if updating)
    # Note: Material Request uses custom_project_ field (with trailing underscore)
    existing_mr_qty = frappe.db.sql(
        """
        SELECT COALESCE(SUM(mri.qty), 0)
        FROM `tabMaterial Request Item` mri
        INNER JOIN `tabMaterial Request` mr ON mri.parent = mr.name
        WHERE mr.custom_project_ = %s
          AND mri.item_code = %s
          AND mr.docstatus < 2
          AND mr.name != %s
        """,
        (project, item_code, mr_name or ""),
    )[0][0] or 0

    total_procurement = existing_mr_qty + mr_qty
    max_allowed = max(0, component.total_qty_limit - existing_mr_qty)

    # Hard limit check
    if total_procurement > component.total_qty_limit:
        frappe.throw(
            _(
                "Cannot add {0} units of {1} to Material Request.<br><br>"
                "<b>Procurement Limit Exceeded:</b><br>"
                "<table class='table table-bordered' style='width:auto;margin-top:10px'>"
                "<tr><td>Total Limit:</td><td style='text-align:right'><b>{2}</b></td></tr>"
                "<tr><td>Existing MRs:</td><td style='text-align:right'>{3}</td></tr>"
                "<tr><td>This MR:</td><td style='text-align:right'>{4}</td></tr>"
                "<tr class='text-danger'><td>Total:</td><td style='text-align:right'><b>{5}</b></td></tr>"
                "<tr class='text-success'><td>Max Allowed:</td><td style='text-align:right'><b>{6}</b></td></tr>"
                "</table>"
                "<br><small><i class='fa fa-info-circle'></i> "
                "Update quantity limit in Project Component Master if needed</small>"
            ).format(
                mr_qty,
                frappe.bold(item_code),
                component.total_qty_limit,
                existing_mr_qty,
                mr_qty,
                total_procurement,
                max_allowed,
            ),
            title=_("Procurement Limit Exceeded"),
        )

    # Warning for loose item over-procurement
    if (
        component.is_loose_item
        and component.bom_conversion_status == "Converted to BOM"
    ):
        loose_qty = component.loose_qty_required or 0
        bom_qty = component.bom_qty_required or 0

        if loose_qty > bom_qty:
            frappe.msgprint(
                _(
                    "<div class='alert alert-warning'>"
                    "<i class='fa fa-exclamation-triangle'></i> <b>Note:</b> "
                    "Item {0} was procured as loose item (<b>{1} units</b>) "
                    "but BOM requires only <b>{2} units</b>. "
                    "Current MR adds <b>{3} units</b> (Total limit: <b>{4}</b>)"
                    "</div>"
                ).format(
                    frappe.bold(item_code),
                    loose_qty,
                    bom_qty,
                    mr_qty,
                    component.total_qty_limit,
                ),
                indicator="orange",
                title=_("Over-procurement Warning"),
            )
