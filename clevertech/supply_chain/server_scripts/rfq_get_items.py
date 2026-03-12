"""
Custom RFQ creation from Material Request with smart item filtering.

Functions:
1. check_mr_rfq_status       — returns item counts by RFQ/PO status (used by client dialog)
2. make_request_for_quotation — creates RFQ from MR with fetch_mode support
3. get_item_from_material_requests_based_on_supplier — "Get Items From" → "Possible Supplier"

fetch_mode values:
  "remaining" — only items with no active RFQ (default)
  "all"       — all items except those with a submitted PO
"""

import frappe
from frappe import _
from frappe.model.mapper import get_mapped_doc


def _get_mr_item_buckets(mr_name):
    """
    For a given MR, return three sets of MR item names:
      - has_po      : items with a submitted PO (always excluded)
      - has_rfq_no_po : items with active RFQ but no submitted PO (user choice)
      - no_rfq      : items with no active RFQ and no PO (always included)
    Also returns rfq_nos: list of RFQ numbers for items in has_rfq_no_po.
    """
    all_items = frappe.get_all(
        "Material Request Item",
        filters={"parent": mr_name},
        fields=["name", "item_code"]
    )
    all_item_names = [i.name for i in all_items]

    if not all_item_names:
        return {
            "all_items": [],
            "has_po": set(),
            "has_rfq_no_po": set(),
            "no_rfq": set(),
            "rfq_nos": []
        }

    # Items with submitted PO
    po_rows = frappe.db.sql("""
        SELECT DISTINCT poi.material_request_item
        FROM `tabPurchase Order Item` poi
        INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
        WHERE poi.material_request_item IN %(names)s
        AND po.docstatus = 1
    """, {"names": all_item_names}, as_dict=True)
    has_po = {r.material_request_item for r in po_rows}

    # Items with active RFQ (docstatus < 2)
    rfq_rows = frappe.db.sql("""
        SELECT DISTINCT rfqi.material_request_item, rfqi.parent as rfq_no
        FROM `tabRequest for Quotation Item` rfqi
        INNER JOIN `tabRequest for Quotation` rfq ON rfq.name = rfqi.parent
        WHERE rfqi.material_request_item IN %(names)s
        AND rfq.docstatus < 2
    """, {"names": all_item_names}, as_dict=True)
    has_rfq = {r.material_request_item for r in rfq_rows}
    rfq_nos = list({r.rfq_no for r in rfq_rows if r.material_request_item not in has_po})

    has_rfq_no_po = has_rfq - has_po
    no_rfq = {i.name for i in all_items} - has_rfq - has_po

    return {
        "all_items": all_items,
        "has_po": has_po,
        "has_rfq_no_po": has_rfq_no_po,
        "no_rfq": no_rfq,
        "rfq_nos": rfq_nos
    }


@frappe.whitelist()
def check_mr_rfq_status(mr_name):
    """
    Returns item counts bucketed by RFQ/PO status.
    Called by the client before showing the Create RFQ dialog.
    """
    buckets = _get_mr_item_buckets(mr_name)
    return {
        "total": len(buckets["all_items"]),
        "has_po": len(buckets["has_po"]),
        "has_rfq_no_po": len(buckets["has_rfq_no_po"]),
        "no_rfq": len(buckets["no_rfq"]),
        "rfq_nos": buckets["rfq_nos"]
    }


@frappe.whitelist()
def make_request_for_quotation(source_name, target_doc=None, fetch_mode="remaining"):
    """
    Create RFQ from Material Request.

    fetch_mode="remaining" : only items with no active RFQ
    fetch_mode="all"       : all items except those with a submitted PO
    """
    buckets = _get_mr_item_buckets(source_name)

    if fetch_mode == "all":
        excluded_set = buckets["has_po"]
    else:
        # "remaining" — exclude items with active RFQ or submitted PO
        excluded_set = buckets["has_po"] | buckets["has_rfq_no_po"]

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
                "condition": lambda row: row.name not in excluded_set,
                "field_map": [
                    ["name", "material_request_item"],
                    ["parent", "material_request"],
                    ["project", "project_name"],
                ],
            },
        },
        target_doc,
    )

    return doclist


@frappe.whitelist()
def get_item_from_material_requests_based_on_supplier(source_name, target_doc=None):
    """
    Override of erpnext.buying.doctype.request_for_quotation.request_for_quotation
        .get_item_from_material_requests_based_on_supplier

    Excludes MR items that already have non-cancelled RFQs and shows a message.
    """
    # Build global exclusion map (all MRs, not just one) — used for "Possible Supplier" flow
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
        AND EXISTS (
            SELECT 1 FROM `tabPurchase Order Item` poi
            INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
            WHERE poi.material_request_item = rfqi.material_request_item
            AND po.docstatus = 1
        )
    """, as_dict=True)

    existing_map = {}
    for r in rows:
        existing_map.setdefault(r.material_request_item, []).append({
            "rfq_no": r.rfq_no,
            "rfq_status": r.rfq_status,
            "item_code": r.item_code
        })
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

    # Filter out items that already have RFQs with PO
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

    return target_doc
