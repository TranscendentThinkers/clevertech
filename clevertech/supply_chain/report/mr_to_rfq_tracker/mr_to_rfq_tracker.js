frappe.query_reports["MR to RFQ Tracker"] = {
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
            fieldname: "mr_no",
            label: "Material Request No",
            fieldtype: "Link",
            options: "Material Request"
        },
        {
            fieldname: "status_filter",
            label: "Status",
            fieldtype: "Select",
            options: "\nComplete\nIncomplete",
            default: "Incomplete"
        }
    ],

    onload: function(report) {
        // On first load, if neither show_all_projects nor project is set,
        // show a warning instead of letting the report run empty
        report.page.set_indicator(__("Select a Project or enable Show All Projects"), "orange");
    },

    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        // Render item image as thumbnail
        if (column.fieldname === "item_image" && data.item_image) {
            let img_url = data.item_image;
            let item_code = data.item_code || 'Item Image';
            return `<img src="${img_url}"
                         alt="${item_code}"
                         style="max-width:60px;max-height:60px;object-fit:contain;cursor:pointer;"
                         onclick="(function() {
                             let d = new frappe.ui.Dialog({
                                 title: '${item_code}',
                                 fields: [{
                                     fieldtype: 'HTML',
                                     fieldname: 'image_html'
                                 }]
                             });
                             d.fields_dict.image_html.$wrapper.html('<img src=\\'${img_url}\\' style=\\'max-width:100%;height:auto;\\' />');
                             d.show();
                         })()" />`;
        }

        // Color coding for Status
        if (column.fieldname === "status") {
            let color = {
                "Pending": "red",
                "Partial": "orange",
                "Complete": "green"
            }[data.status];
            if (color) {
                value = `<span style="font-weight:600;color:${color}">${value}</span>`;
            }
        }

        // Color coding for Balance Qty (negative = over-requested)
        if (column.fieldname === "balance_qty") {
            if (data.balance_qty < 0) {
                value = `<span style="color:purple;font-weight:600">${value}</span>`;
            } else if (data.balance_qty > 0) {
                value = `<span style="color:red;font-weight:600">${value}</span>`;
            }
        }

        // Make RFQ numbers clickable links
        if (column.fieldname === "rfq_no" && value) {
            let rfq_nos = value.split(', ');
            let links = rfq_nos.map(rfq_no => {
                return `<a href="/app/request-for-quotation/${rfq_no.trim()}" target="_blank">${rfq_no.trim()}</a>`;
            });
            value = links.join(', ');
        }

        // Hierarchical duplicate blanking: project → project_name → mr_no → mr_date
        const hierarchy = ["project", "project_name", "mr_no", "mr_date"];
        const field_index = hierarchy.indexOf(column.fieldname);
        if (field_index !== -1) {
            let all_data = frappe.query_report.data || [];
            let curr_idx = all_data.indexOf(data);
            if (curr_idx > 0) {
                let prev = all_data[curr_idx - 1];
                let curr_val = (data[column.fieldname] !== null && data[column.fieldname] !== undefined)
                    ? String(data[column.fieldname]) : "";
                let prev_val = (prev[column.fieldname] !== null && prev[column.fieldname] !== undefined)
                    ? String(prev[column.fieldname]) : "";
                if (curr_val && curr_val === prev_val) {
                    return "";
                }
            }
        }

        return value;
    }
};
