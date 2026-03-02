# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
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
			"fieldname": "purchase_order",
			"label": _("Purchase Order"),
			"fieldtype": "Link",
			"options": "Purchase Order",
			"width": 150
		},
		{
			"fieldname": "po_date",
			"label": _("PO Date"),
			"fieldtype": "Date",
			"width": 100
		},
		{
			"fieldname": "supplier",
			"label": _("Supplier"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 150
		},
		{
			"fieldname": "supplier_name",
			"label": _("Supplier Name"),
			"fieldtype": "Data",
			"width": 180
		},
		{
			"fieldname": "item_code",
			"label": _("Item Code"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 130
		},
		{
			"fieldname": "item_name",
			"label": _("Item Name"),
			"fieldtype": "Data",
			"width": 150
		},
		{
			"fieldname": "qty_ordered",
			"label": _("Qty Ordered"),
			"fieldtype": "Float",
			"width": 100
		},
		{
			"fieldname": "purchase_receipt",
			"label": _("Purchase Receipt"),
			"fieldtype": "Link",
			"options": "Purchase Receipt",
			"width": 150
		},
		{
			"fieldname": "receipt_date",
			"label": _("Receipt Date"),
			"fieldtype": "Date",
			"width": 100
		},
		{
			"fieldname": "qty_received",
			"label": _("Qty Received"),
			"fieldtype": "Float",
			"width": 100
		},
		{
			"fieldname": "inspection_required",
			"label": _("Inspection Required"),
			"fieldtype": "Data",
			"width": 130
		},
		{
			"fieldname": "quality_inspection",
			"label": _("Quality Inspection"),
			"fieldtype": "Link",
			"options": "Quality Inspection",
			"width": 150
		},
		{
			"fieldname": "inspection_status",
			"label": _("Inspection Status"),
			"fieldtype": "Data",
			"width": 150
		}
	]


def get_data(filters):
	conditions = get_conditions(filters)
	
	query = """
		SELECT
			po.name as purchase_order,
			po.transaction_date as po_date,
			po.supplier as supplier,
			po.supplier_name as supplier_name,
			poi.item_code as item_code,
			poi.item_name as item_name,
			poi.qty as qty_ordered,
			pr.name as purchase_receipt,
			pr.posting_date as receipt_date,
			pri.qty as qty_received,
			item.inspection_required_before_purchase as inspection_required,
			pri.quality_inspection as quality_inspection
		FROM
			`tabPurchase Order` po
		INNER JOIN
			`tabPurchase Order Item` poi ON poi.parent = po.name
		LEFT JOIN
			`tabPurchase Receipt Item` pri ON pri.purchase_order = po.name 
			AND pri.item_code = poi.item_code
			AND pri.docstatus = 1
		LEFT JOIN
			`tabPurchase Receipt` pr ON pr.name = pri.parent
			AND pr.docstatus = 1
		LEFT JOIN
			`tabItem` item ON item.name = poi.item_code
		WHERE
			po.docstatus = 1
			{conditions}
		ORDER BY
			po.transaction_date DESC, po.name, poi.idx
	""".format(conditions=conditions)
	
	data = frappe.db.sql(query, filters, as_dict=1)
	
	# Process data to add inspection status
	processed_data = []
	for row in data:
		# Check if inspection is required (this is a boolean/int from database)
		inspection_required = row.get('inspection_required')
		
		# Set inspection required display
		row['inspection_required'] = "Yes" if inspection_required else "No"
		
		# Determine inspection status ONLY if inspection is required
		if not inspection_required:
			# If inspection not required, leave status blank
			row['inspection_status'] = ""
		elif not row.get('purchase_receipt'):
			# No GRN yet
			row['inspection_status'] = "Inspection Pending"
		elif not row.get('quality_inspection'):
			# GRN exists but no QI
			row['inspection_status'] = "Inspection Pending"
		else:
			# GRN exists and QI is populated
			row['inspection_status'] = "Inspection Complete"
		
		# Apply inspection status filter if provided
		if filters.get("inspection_status"):
			status_filter = filters.get("inspection_status")
			# Handle "No Inspection Required" filter
			if status_filter == "No Inspection Required" and row['inspection_status'] == "":
				processed_data.append(row)
			# Handle other status filters
			elif row['inspection_status'] == status_filter:
				processed_data.append(row)
		else:
			# No status filter, include all rows
			processed_data.append(row)
	
	return processed_data


def get_conditions(filters):
	conditions = []
	
	if filters.get("purchase_order"):
		conditions.append("po.name = %(purchase_order)s")
	
	if filters.get("purchase_receipt"):
		conditions.append("pr.name = %(purchase_receipt)s")
	
	return " AND " + " AND ".join(conditions) if conditions else ""
