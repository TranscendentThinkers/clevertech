# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

# import frappe



import frappe

def execute(filters=None):
    if not filters:
        filters = {}

    columns = [
            {"label": "Project No", "fieldname": "project_no", "fieldtype": "Link","options":"Project", "width": 150},
            {"label": "Project Name", "fieldname": "project_name", "fieldtype": "Data", "width": 150},
            {"label": "G Code", "fieldname": "g_code", "fieldtype": "Data", "width": 150},
            {"label": "GRN Name", "fieldname": "grn_name", "fieldtype": "Link","options":"Purchase Receipt", "width": 150},
            {"label": "GRN Date", "fieldname": "grn_date", "fieldtype": "Date", "width": 150},
            {"label": "Supplier Code", "fieldname": "supplier_code", "fieldtype": "Link","options":"Supplier", "width": 150},
            {"label": "Supplier Name", "fieldname": "supplier_name", "fieldtype": "Data", "width": 150},
            {"label": "Item Code", "fieldname": "item_code", "fieldtype": "Data", "width": 150},
            {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 180},
            {"label": "Description", "fieldname": "description", "fieldtype": "Data", "width": 200},
            {"label": "Qty", "fieldname": "qty", "fieldtype": "Float", "width": 120},
            {"label": "Accepted Qty", "fieldname": "accepted_qty", "fieldtype": "Float", "width": 120},
            {"label": "Rejected Qty", "fieldname": "rejected_qty", "fieldtype": "Float", "width": 120},
            {"label": "Rejection Reasons", "fieldname": "rejection_reasons", "fieldtype": "Data", "width": 180},
            {"label": "Remarks", "fieldname": "remarks", "fieldtype": "Data", "width": 180},
            {"label": "Acceptance %", "fieldname": "acceptance_percent", "fieldtype": "Percent", "width": 120},
            {"label": "Rejection %", "fieldname": "rejection_percent", "fieldtype": "Percent", "width": 120},
    ]

    data = []

    # Step 1: Fetch all Quality Inspection docs of type Purchase Receipt
    qi_list = frappe.get_all(
        "Quality Inspection",
        filters={"reference_type": "Purchase Receipt","docstatus":1},
        fields=["name", "reference_name", "item_code", "item_name", "description", "remarks" ]
    )

    for qi in qi_list:
        # Step 2: Include only those items whose Item Group = "Drawing Items"
        if not (qi.item_code.startswith("D") or qi.item_code.startswith("IM")):
            continue

        # Step 3: Get Purchase Receipt Details
        pr = frappe.db.get_value(
            "Purchase Receipt",
            qi.reference_name,
            ["supplier", "project","posting_date"],
            as_dict=True
        )

        pr_item = frappe.db.get_value(
            "Purchase Receipt Item",
            {"parent": qi.reference_name, "item_code": qi.item_code},
            ["qty", "rejected_qty"],
            as_dict=True
        )

        rejected_qty = pr_item.rejected_qty if pr_item else 0
        accepted_qty =  pr_item.qty
        qty = accepted_qty + rejected_qty

        # Step 4: Calculate Acceptance % and Rejection %
        acceptance_percent = (accepted_qty / qty * 100) if qty else 0
        rejection_percent = (rejected_qty / qty * 100) if qty else 0

        # Step 5: Find G Code
        # (Find BOM where this item is used in BOM Item)
        bom_item = frappe.db.get_value(
            "BOM Item",
            {"item_code": qi.item_code},
            "parent"
        )
        g_code = None
        if bom_item:
            g_code = frappe.db.get_value("BOM", {"name": bom_item, "project": pr.project}, "item")  # BOM's main item = G Code
        project_name = frappe.db.get_value("Project",pr.project,"project_name")

        data.append({
            "item_code": qi.item_code,
            "item_name": qi.item_name,
            "description": qi.description,
            "qty": qty,
            "accepted_qty": accepted_qty,
            "rejected_qty": rejected_qty,
            "acceptance_percent": acceptance_percent,
            "rejection_percent": rejection_percent,
            "rejection_reasons": qi.rejected_readings or "",
            "project_no": pr.project if pr else "",
            "project_name":project_name,
            "supplier_code": pr.supplier if pr else "",
            "supplier_name":frappe.db.get_value("Supplier",pr.supplier,"supplier_name"),
            "g_code": g_code or "",
            "remarks": qi.remarks,
            "grn_name":qi.reference_name,
            "grn_date":pr.posting_date
        })

    return columns, data

