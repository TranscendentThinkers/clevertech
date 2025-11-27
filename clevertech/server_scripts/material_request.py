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

    # If insufficient, throw message
#    if required_qty > total_available:
#        frappe.throw(
#            f"Insufficient stock for {item_code} in {from_wh}: Requested {required_qty}, Available {total_available}"
#        )

    return {"available_qty": total_available}

import frappe
from frappe.utils import getdate

def before_validate(doc, method):
    if doc.transaction_date and doc.schedule_date:
        td = getdate(doc.transaction_date)
        sd = getdate(doc.schedule_date)
        diff = (sd - td).days
        doc.custom_required_by_in_days = diff


def validate(doc,method):
    frappe.log_error("Validate called")
    for d in doc.items:
        if d.actual_qty is not None and d.qty > d.actual_qty:
            frappe.throw(
                _("Row #{0}: Request Qty {1} is greater than Available Qty {2}")
                .format(d.idx, d.qty, d.actual_qty)
            )
