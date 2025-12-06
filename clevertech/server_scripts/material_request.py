import frappe
@frappe.whitelist()
def check_item_stock(parent_doc, child_row):
    import json
    doc = frappe._dict(json.loads(parent_doc))
    row = frappe._dict(json.loads(child_row))

    if doc.get("material_request_type") != "Material Transfer":
        return

    from_wh = doc.get("set_from_warehouse")
    item_code = row.get("item_code")
    if not (from_wh and item_code):
        return

    # Detect if selected warehouse is a group
    is_group = frappe.db.get_value("Warehouse", from_wh, "is_group")

    # Determine which warehouses to include
    wh_list = [from_wh]
    if is_group:
        lft, rgt = frappe.db.get_value("Warehouse", from_wh, ["lft", "rgt"])
        child_whs = frappe.get_all(
            "Warehouse",
            filters={"lft": (">", lft), "rgt": ("<", rgt)},
            pluck="name"
        )
        if child_whs:
            wh_list = child_whs

    # Fetch Bin entries
    bins = frappe.get_all(
        "Bin",
        filters={"warehouse": ["in", wh_list], "item_code": item_code},
        fields=["item_code", "actual_qty"],
    )

    total_available = sum(b.get("actual_qty") or 0 for b in bins)

    required_qty = float(row.get("qty") or 0)

    return {"available_qty": total_available}

import frappe
from frappe.utils import getdate
from frappe import _
def before_validate(doc, method):
    if doc.transaction_date and doc.schedule_date:
        td = getdate(doc.transaction_date)
        sd = getdate(doc.schedule_date)
        diff = (sd - td).days
        doc.custom_required_by_in_days = diff
    if doc.material_request_type == "Purchase":
        settings = frappe.get_cached_doc("Quality Warehouse Settings")
        qc_accepted = settings.qc_accepted_warehouse
        default_store = settings.default_store_warehouse

        for row in doc.items:
            if not row.item_code:
                continue

            # Fetch only the required field
            requires_inspection = frappe.db.get_value(
                "Item",
                row.item_code,
                "inspection_required_before_purchase"
            )

            # Apply logic
            if requires_inspection:
                row.warehouse = qc_accepted
            else:
                row.warehouse = default_store


@frappe.whitelist()
def check_over_requested_items(doc):
    doc = frappe.parse_json(doc)

    result = []

    for row in doc.get("items", []):
        if not row.get("item_code"):
            continue

        already_requested = frappe.db.sql("""
            SELECT IFNULL(SUM(mri.qty), 0)
            FROM `tabMaterial Request Item` mri
            JOIN `tabMaterial Request` mr ON mr.name = mri.parent
            WHERE
                mr.docstatus = 1
                AND mr.material_request_type = 'Purchase'
                AND mr.custom_project_ = %s
                AND mri.item_code = %s
        """, (doc.get("custom_project_"), row["item_code"]))[0][0]

        if already_requested > 0:
            result.append({
                "item_code": row["item_code"],
                "already_requested": already_requested,
                "current_qty": row["qty"]
            })

    return result

