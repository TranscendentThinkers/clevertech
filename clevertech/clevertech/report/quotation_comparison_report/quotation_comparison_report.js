frappe.query_reports["Quotation Comparison Report"] = {
    filters: [
        {
            fieldname: "comparison",
            label: "Supplier Quotation Comparison",
            fieldtype: "Link",
            options: "Supplier Quotation Comparison",
            reqd: 1
        }
    ]
};

