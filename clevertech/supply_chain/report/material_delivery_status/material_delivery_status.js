// Copyright (c) 2025, Bharatbodh and contributors
// For license information, please see license.txt

frappe.query_reports["Material Delivery Status"] = {
	"filters": [
		{
            fieldname: "supplier",
            label: "Supplier",
            fieldtype: "Link",
            options: "Supplier"
        },
        {
            fieldname: "purchase_receipt",
            label: "Purchase Receipt",
            fieldtype: "Link",
            options: "Purchase Receipt"
        },
        {
            fieldname: "order_status",
            label: "Order Status",
            fieldtype: "Select",
            options: "\nPending\nPartially Completed\nCompleted"
        }

	],
	formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (!data) return value;

        const status_fields = "order_status"

        if (status_fields == column.fieldname) {
            let color = {
                "Pending": "red",
                "Partially Completed": "orange",
                "Completed": "green"
            }[data[column.fieldname]];

            if (color) {
                value = `<span style="font-weight:600;color:${color}">${value}</span>`;
            }
        }

        return value;
    },
};
