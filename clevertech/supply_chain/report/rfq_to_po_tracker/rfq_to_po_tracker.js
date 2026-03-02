frappe.query_reports["RFQ to PO Tracker"] = {
    filters: [
        {
            fieldname: "show_all_projects",
            label: "Show All Projects",
            fieldtype: "Check",
            default: 0,
            on_change: function() {
                if (frappe.query_report.get_filter_value("show_all_projects")) {
                    frappe.query_report.set_filter_value("project", "");
                }
                frappe.query_report.refresh();
            }
        },
        {
            fieldname: "project",
            label: "Project",
            fieldtype: "Link",
            options: "Project",
            on_change: function() {
                if (frappe.query_report.get_filter_value("project")) {
                    frappe.query_report.set_filter_value("show_all_projects", 0);
                }
                frappe.query_report.refresh();
            }
        },
        {
            fieldname: "rfq_no",
            label: "RFQ No",
            fieldtype: "Link",
            options: "Request for Quotation"
        }
    ],

    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        // ── Group by: hide repeated values in Project No, Project Name, RFQ No, Date ──
        // We use frappe.query_report.data.indexOf(data) to reliably get the current row index,
        // because row._rowIndex is not always trustworthy in Frappe query reports.
        const grouping_fields = ["project", "project_name", "rfq_no", "rfq_date"];
        if (grouping_fields.includes(column.fieldname)) {
            let all_data = frappe.query_report.data || [];
            let current_idx = all_data.indexOf(data);
            if (current_idx > 0) {
                let prev = all_data[current_idx - 1];
                let curr_val = (data[column.fieldname] !== null && data[column.fieldname] !== undefined)
                    ? String(data[column.fieldname]) : "";
                let prev_val = (prev[column.fieldname] !== null && prev[column.fieldname] !== undefined)
                    ? String(prev[column.fieldname]) : "";
                if (curr_val && curr_val === prev_val) {
                    return "";
                }
            }
        }

        // ── Color code Supplier Quotation Status ──
        if (column.fieldname === "sq_status" && data.sq_status) {
            let color = {
                "Pending": "red",
                "Draft": "orange",
                "Submitted": "green"
            }[data.sq_status];
            if (color) {
                value = `<span style="font-weight:600;color:${color}">${data.sq_status}</span>`;
            }
        }

        // ── Color code SQ Comparison Status ──
        if (column.fieldname === "sqc_status" && data.sqc_status) {
            let color = "orange";
            if (data.sqc_status === "Approved") color = "green";
            else if (data.sqc_status === "Rejected") color = "red";
            value = `<span style="font-weight:600;color:${color}">${data.sqc_status}</span>`;
        }

        // ── Make Supplier Quotation No clickable (comma-separated) ──
        if (column.fieldname === "sq_no" && data.sq_no) {
            let links = data.sq_no.split(", ").map(sq => {
                let s = sq.trim();
                return `<a href="/app/supplier-quotation/${s}" target="_blank">${s}</a>`;
            });
            value = links.join(", ");
        }

        // ── Make SQ Comparison No clickable ──
        if (column.fieldname === "sqc_no" && data.sqc_no) {
            value = `<a href="/app/supplier-quotation-comparison/${data.sqc_no}" target="_blank">${data.sqc_no}</a>`;
        }

        return value;
    }
};
