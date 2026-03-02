"""
Request for Quotation Quantity Validation for Project Component Master

Validates RFQ quantities against Component Master total_qty_limit.
Hard block (frappe.throw) if quantity exceeds limit.
Provides pre-order layer of enforcement before PO validation.
"""

import frappe
from frappe import _


def validate_rfq_qty(doc, method=None):
    """
    Validate RFQ quantities against Project Component Master limits.
    Hook: Request for Quotation validate event.

    Only enforces limits for "Buy" items (items that are actually procured).
    "Make" items are assembled in-house and don't need RFQ validation.

    Skips silently if no project is set on the RFQ.
    """
    # RFQ uses custom_project field (no trailing underscore)
    project = doc.get("custom_project")
    if not project:
        return  # No project, skip validation

    for item in doc.items:
        _validate_item_qty(project, item.item_code, item.qty, doc.name)


def _validate_item_qty(project, item_code, rfq_qty, rfq_name):
    """
    Validate individual item quantity against Component Master limit.
    Only enforces for "Buy" items — "Make" items are not directly procured.

    Args:
        project: Project name
        item_code: Item code
        rfq_qty: Requested quantity in this RFQ
        rfq_name: RFQ document name (excluded from existing qty calculation)
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

    # Get existing RFQ quantities (exclude current RFQ if updating)
    # Sum all non-cancelled RFQs for this project + item
    existing_rfq_qty = frappe.db.sql(
        """
        SELECT COALESCE(SUM(rfqi.qty), 0)
        FROM `tabRequest for Quotation Item` rfqi
        INNER JOIN `tabRequest for Quotation` rfq ON rfqi.parent = rfq.name
        WHERE rfq.custom_project = %s
          AND rfqi.item_code = %s
          AND rfq.docstatus < 2
          AND rfq.name != %s
        """,
        (project, item_code, rfq_name or ""),
    )[0][0] or 0

    total_procurement = existing_rfq_qty + rfq_qty
    max_allowed = max(0, component.total_qty_limit - existing_rfq_qty)

    # Hard limit check
    if total_procurement > component.total_qty_limit:
        frappe.throw(
            _(
                "Cannot add {0} units of {1} to Request for Quotation.<br><br>"
                "<b>Procurement Limit Exceeded:</b><br>"
                "<table class='table table-bordered' style='width:auto;margin-top:10px'>"
                "<tr><td>Total Limit:</td><td style='text-align:right'><b>{2}</b></td></tr>"
                "<tr><td>Existing RFQs:</td><td style='text-align:right'>{3}</td></tr>"
                "<tr><td>This RFQ:</td><td style='text-align:right'>{4}</td></tr>"
                "<tr class='text-danger'><td>Total:</td><td style='text-align:right'><b>{5}</b></td></tr>"
                "<tr class='text-success'><td>Max Allowed:</td><td style='text-align:right'><b>{6}</b></td></tr>"
                "</table>"
                "<br><small><i class='fa fa-info-circle'></i> "
                "Update quantity limit in Project Component Master <b>{7}</b> if needed</small>"
            ).format(
                rfq_qty,
                frappe.bold(item_code),
                component.total_qty_limit,
                existing_rfq_qty,
                rfq_qty,
                total_procurement,
                max_allowed,
                component.name,
            ),
            title=_("Procurement Limit Exceeded"),
        )
