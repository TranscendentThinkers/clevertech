// Copyright (c) 2025, Your Company and contributors
// For license information, please see license.txt

frappe.query_reports["Quality Inspection Status"] = {
	"filters": [
		{
			"fieldname": "purchase_order",
			"label": __("Purchase Order"),
			"fieldtype": "Link",
			"options": "Purchase Order",
			"get_query": function() {
				return {
					"filters": {
						"docstatus": 1
					}
				};
			}
		},
		{
			"fieldname": "purchase_receipt",
			"label": __("Purchase Receipt (GRN)"),
			"fieldtype": "Link",
			"options": "Purchase Receipt"
		}
	],
	
	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		
		// Color code the inspection status column
		if (column.fieldname == "inspection_status" && data) {
			if (data.inspection_status == "Not Created") {
				value = `<span style="color: red; font-weight: bold;">Not Created</span>`;
			} else if (data.inspection_status == "Pending") {
				value = `<span style="color: red; font-weight: bold;">Pending</span>`;
			} else if (data.inspection_status == "Complete") {
				value = `<span style="color: green; font-weight: bold;">Complete</span>`;
			} else if (data.inspection_status && data.inspection_status.startsWith("Partial")) {
				value = `<span style="color: orange; font-weight: bold;">${data.inspection_status}</span>`;
			}
		}
		
		// Highlight rejected quantity
		if (column.fieldname == "rejected_qty" && data && data.rejected_qty > 0) {
			value = `<span style="color: red; font-weight: bold;">${data.rejected_qty}</span>`;
		}
		
		// Highlight qty yet to inspect
		if (column.fieldname == "qty_yet_to_inspect" && data && data.qty_yet_to_inspect > 0) {
			value = `<span style="color: red; font-weight: bold;">${data.qty_yet_to_inspect}</span>`;
		}
		
		// Highlight items without QI
		if (column.fieldname == "quality_inspection_id" && data && !data.quality_inspection_id) {
			value = `<span style="color: red;">-</span>`;
		}
		
		return value;
	}
};
