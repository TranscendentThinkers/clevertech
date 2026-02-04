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
            fieldtype: "Check",
            // fieldtype: "Check"  // Original code - Saket
            // Fixed: Added default: 1 to auto-check Show MR by default
            // Reason: Prevents TypeError when downstream stages (SQ, PO, PR) are checked without MR
            // Since downstream stages depend on mr_qty, MR must be checked - Saket
            default: 1
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
	// Original code - Saket
	// onload: function() {
    //     frappe.form.link_formatters['Item'] = function(value, doc) {
    //         return doc.item_code;
    //     };
    // },

	// Fixed: Added auto-check logic for Show MR when downstream stages are checked
	// Reason: Ensures MR is always checked when RFQ, SQ, PO, or PR are checked
	// This prevents TypeError since downstream stages depend on mr_qty - Saket
	onload: function(report) {
        // Auto-check Show MR when any downstream stage is checked
        report.page.fields_dict.show_rfq.df.onchange = () => {
            if (frappe.query_report.get_filter_value('show_rfq')) {
                frappe.query_report.set_filter_value('show_mr', 1);
            }
        };
        report.page.fields_dict.show_sq.df.onchange = () => {
            if (frappe.query_report.get_filter_value('show_sq')) {
                frappe.query_report.set_filter_value('show_mr', 1);
            }
        };
        report.page.fields_dict.show_po.df.onchange = () => {
            if (frappe.query_report.get_filter_value('show_po')) {
                frappe.query_report.set_filter_value('show_mr', 1);
            }
        };
        report.page.fields_dict.show_pr.df.onchange = () => {
            if (frappe.query_report.get_filter_value('show_pr')) {
                frappe.query_report.set_filter_value('show_mr', 1);
            }
        };

        frappe.form.link_formatters['Item'] = function(value, doc) {
            return doc.item_code;
        };
    },

//    formatter: function(value, row, column, data, default_formatter) {
//        return default_formatter(value, row, column, data);
//    }
};

