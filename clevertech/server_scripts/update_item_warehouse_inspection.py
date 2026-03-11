import frappe


def update_all_items():
    """
    Bulk update all Items:
    - Set warehouse in Item Defaults
    - Set inspection_required_before_purchase
    """

    print("🚀 Starting Bulk Update...")

    items = frappe.get_all("Item", fields=["name", "item_code"])

    total = len(items)
    print(f"Total Items Found: {total}")

    count = 0

    for item in items:

        if not item.item_code:
            continue

        item_code = item.item_code.strip().upper()

        # Logic
        if item_code.startswith("IM") or item_code.startswith("D"):
            warehouse = "Quality Pending - CT"
            inspection_required = 1
        else:
            warehouse = "Material Staging - CT"
            inspection_required = 0

        # 🔹 Update main field directly (FAST)
        frappe.db.set_value(
            "Item",
            item.name,
            "inspection_required_before_purchase",
            inspection_required,
            update_modified=False
        )

        # 🔹 Update Item Defaults child table directly
        frappe.db.sql("""
            UPDATE `tabItem Default`
            SET default_warehouse = %s
            WHERE parent = %s
        """, (warehouse, item.name))

        count += 1

        # Commit every 500 records (safe for large data)
        if count % 500 == 0:
            frappe.db.commit()
            print(f"✅ Updated {count} items...")

    frappe.db.commit()

    print("🎉 Bulk Update Completed Successfully!")
    print(f"Total Updated: {count}")


