// Copyright (c) 2025, Bharatbodh and contributors
// For license information, please see license.txt
frappe.query_reports["Purchase Lifecycle Tracker"] = {
    filters: [
	{
            fieldname: "material_request",
            label: "Material Request",
            fieldtype: "Link",
	    options: "Material Request"
        },
        {
            fieldname: "from_date",
            label: "From Date",
            fieldtype: "Date"
        },
        {
            fieldname: "to_date",
            label: "To Date",
            fieldtype: "Date"
        },
        {
            fieldname: "project",
            label: "Project",
            fieldtype: "Link",
            options: "Project"
        },
	{
    	    fieldname: "show_mr",
            label: "Show MR",
            fieldtype: "Check"
        },
        {
            fieldname: "show_rfq",
            label: "Show RFQ",
            fieldtype: "Check"
        },
        {
            fieldname: "show_sq",
            label: "Show Supplier Quotation",
            fieldtype: "Check"
        },
        {
            fieldname: "show_po",
            label: "Show Purchase Order",
            fieldtype: "Check"
        },
        {
            fieldname: "show_pr",
            label: "Show Purchase Receipt",
            fieldtype: "Check"
        }
    ],

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (!data) return value;

        const status_fields = [
	    "mr_status",
            "rfq_status",
            "sq_status",
            "po_status",
            "pr_status"
        ];

        if (status_fields.includes(column.fieldname)) {
            let color = {
                "Pending": "red",
                "Partial": "orange",
		"Excess Requested": "purple",
                "Completed": "green"
            }[data[column.fieldname]];

            if (color) {
                value = `<span style="font-weight:600;color:${color}">${value}</span>`;
            }
        }

        return value;
    },
	onload: function() {

        frappe.form.link_formatters['Item'] = function(value, doc) {

            return doc.item_code;
        };
    },

//    formatter: function(value, row, column, data, default_formatter) {
//        return default_formatter(value, row, column, data);
//    }
};

