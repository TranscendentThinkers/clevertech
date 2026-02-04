# Copyright (c) 2025, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe import _

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {
            "fieldname": "bqi_name",
            "label": _("BQI Document"),
            "fieldtype": "Link",
            "options": "Bulk Quality Inspection",
            "width": 150
        },
        {
            "fieldname": "po_no",
            "label": _("Purchase Order"),
            "fieldtype": "Link",
            "options": "Purchase Order",
            "width": 150
        },
        {
            "fieldname": "grn_name",
            "label": _("Purchase Receipt (GRN)"),
            "fieldtype": "Link",
            "options": "Purchase Receipt",
            "width": 150
        },
        {
            "fieldname": "item_code",
            "label": _("Item Code"),
            "fieldtype": "Link",
            "options": "Item",
            "width": 150
        },
        {
            "fieldname": "item_name",
            "label": _("Item Name"),
            "fieldtype": "Data",
            "width": 180
        },
        {
            "fieldname": "po_qty",
            "label": _("PO Qty"),
            "fieldtype": "Float",
            "width": 100
        },
        {
            "fieldname": "grn_qty",
            "label": _("GRN Qty"),
            "fieldtype": "Float",
            "width": 100
        },
        {
            "fieldname": "qty_to_inspect",
            "label": _("Qty to Inspect"),
            "fieldtype": "Float",
            "width": 120
        },
        {
            "fieldname": "inspected_qty",
            "label": _("Inspected Qty"),
            "fieldtype": "Float",
            "width": 120
        },
        {
            "fieldname": "accepted_qty",
            "label": _("Accepted Qty"),
            "fieldtype": "Float",
            "width": 120
        },
        {
            "fieldname": "rejected_qty",
            "label": _("Rejected Qty"),
            "fieldtype": "Float",
            "width": 120
        },
        {
            "fieldname": "qty_yet_to_inspect",
            "label": _("Qty Yet to Inspect"),
            "fieldtype": "Float",
            "width": 140
        },
        {
            "fieldname": "inspection_status",
            "label": _("Inspection Status"),
            "fieldtype": "Data",
            "width": 140
        },
        {
            "fieldname": "quality_inspection_id",
            "label": _("Quality Inspection"),
            "fieldtype": "Link",
            "options": "Quality Inspection",
            "width": 150
        },
        {
            "fieldname": "type_of_issue",
            "label": _("Type of Issue"),
            "fieldtype": "Data",
            "width": 150
        },
        {
            "fieldname": "reason",
            "label": _("Reason"),
            "fieldtype": "Data",
            "width": 200
        }
    ]

def get_data(filters):
    # Build conditions based on filters
    conditions = []
    
    if filters.get("purchase_order") and filters.get("purchase_receipt"):
        # Both filters: Get BQI with specific GRN that belongs to the PO
        return get_combined_data(filters)
    elif filters.get("purchase_order"):
        # Only PO: Get BQI directly with PO OR BQI with GRNs linked to the PO
        return get_purchase_order_data(filters)
    elif filters.get("purchase_receipt"):
        # Only GRN: Get BQI with specific GRN
        return get_purchase_receipt_data(filters)
    else:
        frappe.msgprint(_("Please select either Purchase Order or Purchase Receipt"))
        return []

def get_inspection_status(inspected_qty, qty_to_inspect, qi_id):
    """Determine inspection status based on quantities"""
    
    if not qi_id:
        return "Not Created"
    
    if inspected_qty == 0:
        return "Pending"
    elif inspected_qty >= qty_to_inspect:
        return "Complete"
    else:
        return f"Partial ({inspected_qty}/{qty_to_inspect})"

def get_purchase_receipt_data(filters):
    """Get BQI data for a specific Purchase Receipt"""
    
    bqi_data = frappe.db.sql("""
        SELECT 
            bqi.name as bqi_name,
            bqi.po_no,
            bqi.grn_name,
            bqii.item_code,
            bqii.qty_to_inspect,
            bqii.accepted_qty,
            bqii.rejected_qty,
            bqii.quality_inspection_id,
            bqii.type_of_issue,
            bqii.reason
        FROM `tabBulk Quality Inspection` bqi
        INNER JOIN `tabGRN Item` bqii ON bqi.name = bqii.parent
        INNER JOIN `tabItem` i ON bqii.item_code = i.name
        WHERE i.inspection_required_before_purchase = 1
            AND bqi.grn_name = %(purchase_receipt)s
        ORDER BY bqi.creation DESC
    """, filters, as_dict=1)
    
    return process_bqi_data(bqi_data)

def get_purchase_order_data(filters):
    """Get BQI data for a Purchase Order - includes BQI with direct PO link AND BQI with GRNs linked to the PO"""
    
    # First, get all GRNs linked to this PO
    grn_list = frappe.db.sql("""
        SELECT DISTINCT pri.parent as grn_name
        FROM `tabPurchase Receipt Item` pri
        INNER JOIN `tabPurchase Receipt` pr ON pri.parent = pr.name
        WHERE pri.purchase_order = %(purchase_order)s
    """, filters, as_dict=1)
    
    grn_names = [grn.grn_name for grn in grn_list]
    
    # Get BQI data where:
    # 1. po_no is directly populated with the selected PO
    # 2. OR grn_name is in the list of GRNs linked to this PO
    
    if grn_names:
        bqi_data = frappe.db.sql("""
            SELECT 
                bqi.name as bqi_name,
                bqi.po_no,
                bqi.grn_name,
                bqii.item_code,
                bqii.qty_to_inspect,
                bqii.accepted_qty,
                bqii.rejected_qty,
                bqii.quality_inspection_id,
                bqii.type_of_issue,
                bqii.reason
            FROM `tabBulk Quality Inspection` bqi
            INNER JOIN `tabGRN Item` bqii ON bqi.name = bqii.parent
            INNER JOIN `tabItem` i ON bqii.item_code = i.name
            WHERE i.inspection_required_before_purchase = 1
                AND (bqi.po_no = %(purchase_order)s OR bqi.grn_name IN %(grn_names)s)
            ORDER BY bqi.creation DESC
        """, {"purchase_order": filters.get("purchase_order"), "grn_names": grn_names}, as_dict=1)
    else:
        # If no GRNs found, just check for direct PO link
        bqi_data = frappe.db.sql("""
            SELECT 
                bqi.name as bqi_name,
                bqi.po_no,
                bqi.grn_name,
                bqii.item_code,
                bqii.qty_to_inspect,
                bqii.accepted_qty,
                bqii.rejected_qty,
                bqii.quality_inspection_id,
                bqii.type_of_issue,
                bqii.reason
            FROM `tabBulk Quality Inspection` bqi
            INNER JOIN `tabGRN Item` bqii ON bqi.name = bqii.parent
            INNER JOIN `tabItem` i ON bqii.item_code = i.name
            WHERE i.inspection_required_before_purchase = 1
                AND bqi.po_no = %(purchase_order)s
            ORDER BY bqi.creation DESC
        """, filters, as_dict=1)
    
    # Fill in PO number for BQI records that don't have it but have GRN linked to the PO
    for row in bqi_data:
        if not row.po_no and row.grn_name:
            # Get the PO from the GRN
            po_from_grn = frappe.db.get_value("Purchase Receipt Item", 
                {"parent": row.grn_name, "item_code": row.item_code}, 
                "purchase_order"
            )
            if po_from_grn:
                row.po_no = po_from_grn
    
    return process_bqi_data(bqi_data)

def get_combined_data(filters):
    """Get BQI data when both PO and GRN are filtered"""
    
    bqi_data = frappe.db.sql("""
        SELECT 
            bqi.name as bqi_name,
            bqi.po_no,
            bqi.grn_name,
            bqii.item_code,
            bqii.qty_to_inspect,
            bqii.accepted_qty,
            bqii.rejected_qty,
            bqii.quality_inspection_id,
            bqii.type_of_issue,
            bqii.reason
        FROM `tabBulk Quality Inspection` bqi
        INNER JOIN `tabGRN Item` bqii ON bqi.name = bqii.parent
        INNER JOIN `tabItem` i ON bqii.item_code = i.name
        WHERE i.inspection_required_before_purchase = 1
            AND bqi.grn_name = %(purchase_receipt)s
        ORDER BY bqi.creation DESC
    """, filters, as_dict=1)
    
    # Filter to only include items that belong to the specified PO
    filtered_data = []
    for row in bqi_data:
        # Check if this GRN item is linked to the specified PO
        po_link = frappe.db.get_value("Purchase Receipt Item", 
            {"parent": row.grn_name, "item_code": row.item_code}, 
            "purchase_order"
        )
        
        if po_link == filters.get("purchase_order"):
            if not row.po_no:
                row.po_no = po_link
            filtered_data.append(row)
    
    if not filtered_data:
        frappe.msgprint(_("No matching data found for Purchase Receipt {0} and Purchase Order {1}").format(
            filters.get("purchase_receipt"), filters.get("purchase_order")
        ))
    
    return process_bqi_data(filtered_data)

def process_bqi_data(bqi_data):
    """Process BQI data and calculate quantities and status"""
    
    result = []
    for row in bqi_data:
        # Get item name
        item_name = frappe.db.get_value("Item", row.item_code, "item_name")
        
        # Get PO quantity
        po_qty = 0
        if row.po_no:
            po_qty_data = frappe.db.get_value("Purchase Order Item", 
                {"parent": row.po_no, "item_code": row.item_code}, 
                "qty"
            )
            po_qty = po_qty_data or 0
        
        # Get GRN quantity
        grn_qty = 0
        if row.grn_name:
            grn_qty_data = frappe.db.get_value("Purchase Receipt Item", 
                {"parent": row.grn_name, "item_code": row.item_code}, 
                "qty"
            )
            grn_qty = grn_qty_data or 0
        
        # Calculate inspected quantity (accepted + rejected)
        inspected_qty = (row.accepted_qty or 0) + (row.rejected_qty or 0)
        
        # Determine qty to inspect (use GRN qty if available, otherwise PO qty)
        expected_qty = grn_qty if grn_qty > 0 else po_qty
        
        # If qty_to_inspect is not set in BQI, use expected_qty
        qty_to_inspect = row.qty_to_inspect if row.qty_to_inspect else expected_qty
        
        # Calculate qty yet to inspect
        qty_yet_to_inspect = qty_to_inspect - inspected_qty
        
        # Determine inspection status
        inspection_status = get_inspection_status(inspected_qty, qty_to_inspect, row.quality_inspection_id)
        
        result.append({
            "bqi_name": row.bqi_name,
            "po_no": row.po_no,
            "grn_name": row.grn_name,
            "item_code": row.item_code,
            "item_name": item_name,
            "po_qty": po_qty,
            "grn_qty": grn_qty,
            "qty_to_inspect": qty_to_inspect,
            "inspected_qty": inspected_qty,
            "accepted_qty": row.accepted_qty or 0,
            "rejected_qty": row.rejected_qty or 0,
            "qty_yet_to_inspect": qty_yet_to_inspect,
            "inspection_status": inspection_status,
            "quality_inspection_id": row.quality_inspection_id,
            "type_of_issue": row.type_of_issue,
            "reason": row.reason
        })
    
    return result
