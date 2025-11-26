import frappe
def before_validate(doc,method):
    if (doc.item_code.startswith("D") or doc.item_code.startswith("IM")) and doc.item_group == "Drawing Items":
        doc.inspection_required_before_purchase = 1
