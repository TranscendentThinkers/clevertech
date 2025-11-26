// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Rack wise Stock"] = {
	tree: true,
    name_field: "name",
    parent_field: "parent",
    filters: [
        {
            fieldname: "item_code",
            label: __("Item Code"),
            fieldtype: "Link",
            options: "Item",
            reqd: 0
        },
        {
            fieldname: "warehouse",
            label: __("Warehouse (Group)"),
            fieldtype: "Link",
            options: "Warehouse",
            get_query: function() {
                return {
                    filters: {
                        "is_group": 1
                    }
                };
            }
        }
    ]
};

