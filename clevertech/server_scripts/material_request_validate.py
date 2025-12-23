import frappe
def validate(doc,method):
    if doc.material_request_type != "Material Transfer":
        return
    frappe.log_error("Validations trigger")
    over_requested = []
    from_wh = doc.set_from_warehouse
    for row in doc.items:
        if not row.item_code or not row.qty:
            continue
        if row.qty > row.actual_qty:
            over_requested.append(f"{row.item_code} (requested {row.qty}, available {row.actual_qty})")
    if over_requested:
        frappe.throw(
                f"Cannot save Material Transfer from {from_wh}: insufficient stock for {', '.join(over_requested)}",
                frappe.ValidationError
        )
