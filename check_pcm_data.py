#!/usr/bin/env python3
import frappe

frappe.init(site='clevertech-uat.bharatbodh.com')
frappe.connect()

data = frappe.db.sql("""
    SELECT name, item_code, cost_center, machine_code, component_image
    FROM `tabProject Component Master`
    WHERE project = 'BOM-Hash test-1'
    LIMIT 5
""", as_dict=True)

print("\n=== Project Component Master Data ===")
for row in data:
    print(f"\nName: {row.name}")
    print(f"  Item: {row.item_code}")
    print(f"  Cost Center: '{row.cost_center}' (NULL: {row.cost_center is None})")
    print(f"  Machine Code: '{row.machine_code}' (NULL: {row.machine_code is None})")
    print(f"  Image: '{row.component_image}' (NULL: {row.component_image is None})")

frappe.destroy()
