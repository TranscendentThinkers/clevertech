import frappe




def update_single_item():
    warehouse = "Quality Pending - CT"

    # First get the Item document name
    item_name = frappe.db.get_value(
        "Item",
        {"item_code": "IM02599-A"},
        "name"
    )

    if not item_name:
        print("❌ Item not found")
        return

    # Update existing Item Default record
    frappe.db.sql("""
        UPDATE `tabItem Default`
        SET default_warehouse = %s
        WHERE parent = %s
    """, (warehouse, item_name))

    frappe.db.commit()

    print("✅ Warehouse Updated Successfully")
