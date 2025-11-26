# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

# import frappe


import frappe

def execute(filters=None):
    if not filters:
        filters = {}

    # Define report columns
    columns = [
        {"label": "Item Code", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
        {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 150},
        {"label": "Description", "fieldname": "description", "fieldtype": "Data", "width": 200},
        {"label": "Qty", "fieldname": "qty", "fieldtype": "Float", "width": 100},
        {"label": "Accepted Qty", "fieldname": "accepted_qty", "fieldtype": "Float", "width": 120},
        {"label": "Rejected Qty", "fieldname": "rejected_qty", "fieldtype": "Float", "width": 120},
        {"label": "Rejection Reasons", "fieldname": "rejection_reasons", "fieldtype": "Data", "width": 180},
        {"label": "Remarks", "fieldname": "remarks", "fieldtype": "Data", "width": 200},
    ]

    # Fetch all Quality Inspections of type "Purchase Receipt"
    qi_list = frappe.db.sql("""
        SELECT
            qi.name as qi_name,
            qi.reference_type,
            qi.reference_name,
            qi.item_code,
            qi.item_name,
            qi.description,
            qi.remarks as remarks
        FROM `tabQuality Inspection` qi
        WHERE qi.reference_type = 'Purchase Receipt'
    """, as_dict=True)

    data = []

    for qi in qi_list:
        # Filter only items whose Item Group = "Drawing Items"
        item_group = frappe.db.get_value("Item", qi.item_code, "item_group")
        if item_group != "Drawing Items":
            continue

        # Fetch qty and rejected_qty from Purchase Receipt Item
        pr_item = frappe.db.get_value(
            "Purchase Receipt Item",
            {"parent": qi.reference_name, "item_code": qi.item_code},
            ["qty", "rejected_qty"],
            as_dict=True
        )

        # Default values
        qty = accepted_qty = rejected_qty = 0

        if pr_item:
            qty = (pr_item.qty or 0) + (pr_item.rejected_qty or 0)
            accepted_qty = pr_item.qty or 0
            rejected_qty = pr_item.rejected_qty or 0

        # Append final data row
        data.append({
            "item_code": qi.item_code,
            "item_name": qi.item_name,
            "description": qi.description,
            "qty": qty,
            "accepted_qty": accepted_qty,
            "rejected_qty": rejected_qty,
            "rejection_reasons": "",  # Optional: can fetch from child table if needed
            "remarks": qi.remarks or "",
        })

    return columns, data

