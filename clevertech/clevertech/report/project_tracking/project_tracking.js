// Copyright (c) 2026, Bharatbodh and contributors
// For license information, please see license.txt

frappe.query_reports["Project Tracking"] = {
    filters: [
        {
            fieldname: "project",
            label: "Project",
            fieldtype: "Link",
            options: "Project",
            reqd: 1
        },
        {
            fieldname: "show_mr",
            label: "Show Material Request",
            fieldtype: "Check",
            default: 1
        },
        {
            fieldname: "show_rfq",
            label: "Show RFQ & Quotations",
            fieldtype: "Check",
            default: 0
        },
        {
            fieldname: "show_po",
            label: "Show PO & Delivery",
            fieldtype: "Check",
            default: 0
        }
    ],

    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (!data) return value;

        // Render images with click to enlarge
        if (column.fieldname === "component_image" && data.component_image) {
            let img_url = data.component_image;
            let item_code = data.item_code || 'Component Image';
            return `<img src="${img_url}"
                         alt="Component"
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

        // Color coding for Make/Buy status
        if (column.fieldname === "make_or_buy") {
            let color = data.make_or_buy === "Buy" ? "blue" : "gray";
            value = `<span style="font-weight:600;color:${color}">${value}</span>`;
        }

        // Color coding for delivery status
        if (column.fieldname === "delivery_status") {
            let color = {
                "Pending": "red",
                "Partial": "orange",
                "Completed": "green"
            }[data.delivery_status];
            if (color) {
                value = `<span style="font-weight:600;color:${color}">${value}</span>`;
            }
        }

        // Blank consecutive duplicates for grouping columns
        const grouping_fields = ["project", "machine_code", "cost_center", "m_code", "g_code"];
        if (grouping_fields.includes(column.fieldname) && row._rowIndex > 0) {
            let prev_row = frappe.query_report.data[row._rowIndex - 1];
            if (prev_row && prev_row[column.fieldname] === data[column.fieldname]) {
                return "";
            }
        }

        return value;
    }
};
