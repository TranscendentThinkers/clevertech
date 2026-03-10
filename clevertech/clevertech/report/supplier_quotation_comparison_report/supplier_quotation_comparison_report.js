frappe.query_reports["Supplier Quotation Comparison Report"] = {
	filters: [
		{
			fieldname: "request_for_quotation",
			label: __("Request for Quotation"),
			fieldtype: "Link",
			options: "Request for Quotation",
			reqd: 1,
			get_query: function () {
				return { filters: { docstatus: 1 } };
			}
		}
	],

	onload: function(report) {
		// Inject CSS to allow rows to grow based on content
		if (!document.getElementById("sqc-report-style")) {
			const style = document.createElement("style");
			style.id = "sqc-report-style";
			style.innerHTML = `
				.dt-scrollable .dt-row .dt-cell__content {
					white-space: normal !important;
					word-break: break-word !important;
					overflow: visible !important;
				}
				.dt-scrollable .dt-row {
					height: auto !important;
				}
				.dt-scrollable .dt-cell {
					height: auto !important;
				}
				.dt-scrollable {
					height: auto !important;
					overflow: visible !important;
				}
				.datatable .dt-body {
					height: auto !important;
					overflow: visible !important;
				}
				.report-wrapper .datatable {
					height: auto !important;
					overflow: visible !important;
				}
			`;
			document.head.appendChild(style);
		}
	},

	formatter: function (value, row, column, data, default_formatter) {
		// 1. Handle Footer Rows
		if (data && data.is_footer) {
			if (column.fieldname.startsWith("rate_")) {
				const is_notes_row = (data["item_code"] || "").indexOf("Notes") !== -1;
				const padding = is_notes_row ? "10px 6px" : "8px 6px";
				return (
					'<div style="' +
						'white-space: normal;' +
						'word-break: break-word;' +
						'color: #333;' +
						'font-size: 13px;' +
						'font-weight: normal;' +
						'line-height: 1.6;' +
						'padding: ' + padding + ';' +
					'">' + (value || "-") + '</div>'
				);
			}
			if (column.fieldname === "item_code") {
				return '<div style="font-size: 13px; font-weight: 700; padding: 8px 4px; white-space: normal;">' + (value || "") + '</div>';
			}
			return (value === null || value === undefined) ? "" : value;
		}

		// 2. Standard Item Row Logic
		let formatted_value = default_formatter(value, row, column, data);

		if (!data || !column.fieldname.startsWith("rate_")) return formatted_value;

		const raw = data[column.fieldname];

		// No rate — red N/A
		if (!raw || raw === 0) {
			return '<span style="display:block; background-color:#f8d7da; color:#721c24; font-weight:600; padding:2px 6px; border-radius:3px; text-align:center;">N/A</span>';
		}

		// Use Python-determined lowest supplier (handles tiebreak by grand total)
		const supplier_id = column.fieldname.replace("rate_", "");
		const is_lowest = data["_lowest_supplier_id"] && data["_lowest_supplier_id"] === supplier_id;

		if (is_lowest) {
			return '<span style="display:block; background-color:#d4edda; color:#155724; font-weight:600; padding:2px 6px; border-radius:3px; text-align:right;">' + formatted_value + '</span>';
		}

		return formatted_value;
	}
};
