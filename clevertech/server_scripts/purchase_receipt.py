import frappe

def on_submit(doc, method):
    pending = False

    for row in doc.items:
        # Check if item requires inspection
        requires_qi = frappe.db.get_value(
            "Item",
            row.item_code,
            "inspection_required_before_purchase"
        )

        if requires_qi:
            # Look for submitted QI for this PR + Item
            qi_exists = frappe.db.exists(
                "Quality Inspection",
                {
                    "reference_type": "Purchase Receipt",
                    "reference_name": doc.name,
                    "item_code": row.item_code,
                    "docstatus": 1
                }
            )
            if not qi_exists:
                pending = True
                break

    doc.db_set("custom_quality_status", "Pending" if pending else "Completed")


def before_validate(doc, method):
    # Fetch settings once
    settings = frappe.get_cached_doc("Quality Warehouse Settings")
    qc_accepted = settings.qc_accepted_warehouse
    qc_rejected = settings.qc_rejected_warehouse
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
            row.rejected_warehouse = qc_rejected
        else:
            row.warehouse = default_store


