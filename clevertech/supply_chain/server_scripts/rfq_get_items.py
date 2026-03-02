"""
Override ERPNext's "Get Items from Material Request" functions for RFQ
to exclude MR items that already have non-cancelled RFQs (Draft or Submitted).

Overrides:
1. make_request_for_quotation — "Get Items From" → "Material Request"
2. get_item_from_material_requests_based_on_supplier — "Get Items From" → "Possible Supplier"

Shows a message listing excluded items with their RFQ numbers and status.
"""

import frappe
from frappe import _
from frappe.model.mapper import get_mapped_doc


def _get_mr_items_with_rfq():
    """
    Return a dict of {mr_item_name: [(rfq_no, status), ...]} for MR items
    that already have a non-cancelled RFQ (Draft or Submitted).
    """
    rows = frappe.db.sql("""
        SELECT
            rfqi.material_request_item,
            rfqi.item_code,
            rfqi.parent as rfq_no,
            CASE rfq.docstatus
                WHEN 0 THEN 'Draft'
                WHEN 1 THEN 'Submitted'
            END as rfq_status
        FROM `tabRequest for Quotation Item` rfqi
        INNER JOIN `tabRequest for Quotation` rfq ON rfq.name = rfqi.parent
        WHERE rfq.docstatus < 2
        AND rfqi.material_request_item IS NOT NULL
        AND rfqi.material_request_item != ''
    """, as_dict=True)

    result = {}
    for r in rows:
        result.setdefault(r.material_request_item, []).append({
            "rfq_no": r.rfq_no,
            "rfq_status": r.rfq_status,
            "item_code": r.item_code
        })
    return result


def _show_excluded_message(existing_map, mr_item_names):
    """
    Show a message listing excluded items with their RFQ numbers and statuses.
    """
    excluded = []
    for mi_name in mr_item_names:
        if mi_name in existing_map:
            for info in existing_map[mi_name]:
                excluded.append(info)

    if not excluded:
        return

    # Group by RFQ
    by_rfq = {}
    for e in excluded:
        by_rfq.setdefault(e["rfq_no"], {"status": e["rfq_status"], "items": []})
        by_rfq[e["rfq_no"]]["items"].append(e["item_code"])

    msg_parts = []
    for rfq_no, data in by_rfq.items():
        items_str = ", ".join(data["items"][:5])
        if len(data["items"]) > 5:
            items_str += f" and {len(data['items']) - 5} more"
        msg_parts.append(
            f"<b>{rfq_no}</b> ({data['status']}): {items_str}"
        )

    frappe.msgprint(
        _("The following items were excluded as they already exist in RFQs:") +
        "<br><br>" + "<br>".join(msg_parts),
        title=_("Items Excluded"),
        indicator="orange"
    )


@frappe.whitelist()
def make_request_for_quotation(source_name, target_doc=None):
    """
    Override of erpnext.stock.doctype.material_request.material_request.make_request_for_quotation

    Excludes MR items that already have non-cancelled RFQs and shows a message.
    """
    existing_map = _get_mr_items_with_rfq()
    existing_set = set(existing_map.keys())

    # Get all MR item names to check which ones will be excluded
    all_mr_items = frappe.get_all(
        "Material Request Item",
        filters={"parent": source_name},
        pluck="name"
    )

    doclist = get_mapped_doc(
        "Material Request",
        source_name,
        {
            "Material Request": {
                "doctype": "Request for Quotation",
                "validation": {"docstatus": ["=", 1], "material_request_type": ["=", "Purchase"]},
            },
            "Material Request Item": {
                "doctype": "Request for Quotation Item",
                "condition": lambda row: row.name not in existing_set,
                "field_map": [
                    ["name", "material_request_item"],
                    ["parent", "material_request"],
                    ["project", "project_name"],
                ],
            },
        },
        target_doc,
    )

    _show_excluded_message(existing_map, all_mr_items)

    return doclist


@frappe.whitelist()
def get_item_from_material_requests_based_on_supplier(source_name, target_doc=None):
    """
    Override of erpnext.buying.doctype.request_for_quotation.request_for_quotation
        .get_item_from_material_requests_based_on_supplier

    Excludes MR items that already have non-cancelled RFQs and shows a message.
    """
    existing_map = _get_mr_items_with_rfq()
    existing_set = set(existing_map.keys())

    mr_items_list = frappe.db.sql(
        """
        SELECT
            mr.name, mr_item.item_code, mr_item.name as mr_item_name
        FROM
            `tabItem` as item,
            `tabItem Supplier` as item_supp,
            `tabMaterial Request Item` as mr_item,
            `tabMaterial Request` as mr
        WHERE item_supp.supplier = %(supplier)s
            AND item.name = item_supp.parent
            AND mr_item.parent = mr.name
            AND mr_item.item_code = item.name
            AND mr.status != "Stopped"
            AND mr.material_request_type = "Purchase"
            AND mr.docstatus = 1
            AND mr.per_ordered < 99.99""",
        {"supplier": source_name},
        as_dict=1,
    )

    # Collect excluded items for the message
    excluded_mr_items = [d.mr_item_name for d in mr_items_list if d.mr_item_name in existing_set]

    # Filter out items that already have RFQs
    mr_items_list = [d for d in mr_items_list if d.mr_item_name not in existing_set]

    material_requests = {}
    for d in mr_items_list:
        material_requests.setdefault(d.name, []).append(d.item_code)

    for mr, items in material_requests.items():
        target_doc = get_mapped_doc(
            "Material Request",
            mr,
            {
                "Material Request": {
                    "doctype": "Request for Quotation",
                    "validation": {
                        "docstatus": ["=", 1],
                        "material_request_type": ["=", "Purchase"],
                    },
                },
                "Material Request Item": {
                    "doctype": "Request for Quotation Item",
                    "condition": lambda row: (
                        row.item_code in items and row.name not in existing_set
                    ),
                    "field_map": [
                        ["name", "material_request_item"],
                        ["parent", "material_request"],
                        ["uom", "uom"],
                    ],
                },
            },
            target_doc,
        )

    _show_excluded_message(existing_map, excluded_mr_items)

    return target_doc
