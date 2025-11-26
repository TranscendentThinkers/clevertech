import frappe

def before_validate(doc, method):
    # Fetch settings once
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

    

