frappe.query_reports["PO to Delivery Tracker"] = {
    filters: [
        {
            fieldname: "show_all_projects",
            label: "Show All Projects",
            fieldtype: "Check",
            default: 0,
            on_change: function() {
                if (frappe.query_report.get_filter_value("show_all_projects")) {
                    // Ticked: clear project and auto-fetch all
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
                    // Project selected: untick show_all_projects and auto-reload
                    frappe.query_report.set_filter_value("show_all_projects", 0);
                }
                frappe.query_report.refresh();
            }
        },
        {
            fieldname: "po_no",
            label: "PO No",
            fieldtype: "Link",
            options: "Purchase Order"
        }
    ],

    onload: function(report) {
        // On first load, show a warning instead of letting the report run empty
        report.page.set_indicator(__("Select a Project or enable Show All Projects"), "orange");
    },

    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        // Color code Status
        if (column.fieldname === "status" && data.status) {
            let color = {
                "Pending": "red",
                "Partial": "orange",
                "Complete": "green"
            }[data.status];
            if (color) {
                value = `<span style="font-weight:600;color:${color}">${value}</span>`;
            }
        }

        // Color code Overdue Days (positive = red, zero/negative = green)
        if (column.fieldname === "overdue_days" && data.overdue_days !== null && data.overdue_days !== undefined) {
            let color = data.overdue_days > 0 ? "red" : "green";
            value = `<span style="font-weight:600;color:${color}">${value}</span>`;
        }

        // Make Purchase Receipt No clickable (comma-separated)
        if (column.fieldname === "pr_no" && data.pr_no) {
            let pr_nos = data.pr_no.split(', ');
            let links = pr_nos.map(pr => {
                return `<a href="/app/purchase-receipt/${pr.trim()}" target="_blank">${pr.trim()}</a>`;
            });
            value = links.join(', ');
        }

        // Hierarchical duplicate blanking: project_no > project_name > po_no > supplier_name > po_date
        const hierarchy = ["project_no", "project_name", "po_no", "supplier_name", "po_date"];
        const field_index = hierarchy.indexOf(column.fieldname);
        if (field_index !== -1) {
            let all_data = frappe.query_report.data || [];
            let curr_idx = all_data.indexOf(data);
            if (curr_idx > 0) {
                let prev_row = all_data[curr_idx - 1];
                let all_match = hierarchy
                    .slice(0, field_index + 1)
                    .every(f => {
                        let curr_val = (data[f] !== null && data[f] !== undefined) ? String(data[f]) : "";
                        let prev_val = (prev_row[f] !== null && prev_row[f] !== undefined) ? String(prev_row[f]) : "";
                        return curr_val === prev_val;
                    });
                if (all_match) {
                    return "";
                }
            }
        }

        return value;
    }
};
