// Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Purchase Order Quality Report"] = {
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
			"label": __("Purchase Receipt"),
			"fieldtype": "Link",
			"options": "Purchase Receipt",
			"get_query": function() {
				return {
					"filters": {
						"docstatus": 1
					}
				};
			}
		},
		{
			"fieldname": "inspection_status",
			"label": __("Inspection Status"),
			"fieldtype": "Select",
			"options": [
				"",
				"Inspection Pending",
				"Inspection Complete",
				"No Inspection Required"
			],
			"default": "Inspection Pending"
		}
	],
	
	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		
		if (column.fieldname == "inspection_status") {
			if (value && value.includes("Complete")) {
				value = "<span style='color: green; font-weight: bold;'>" + value + "</span>";
			} else if (value && value.includes("Pending")) {
				value = "<span style='color: orange; font-weight: bold;'>" + value + "</span>";
			}
		}
		
		return value;
	}
};
