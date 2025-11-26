// Copyright (c) 2025, Bharatbodh and contributors
// For license information, please see license.txt

frappe.query_reports["Quality Status"] = {
	"filters": [
		{
            fieldname: "purchase_receipt",
            label: "Purchase Receipt",
            fieldtype: "Link",
            options: "Purchase Receipt",
            reqd: 0,
        },
        {
            fieldname: "quality_inspection",
            label: "Quality Inspection",
            fieldtype: "Link",
            options: "Quality Inspection",
            reqd: 0,
        },
        {
            fieldname: "item_code",
            label: "Item Code",
            fieldtype: "Link",
            options: "Item",
            reqd: 0,
        }

	],
	after_datatable_render: function (datatable) {

        	const $wrapper = $(datatable.wrapper);

        	// Remove old handlers
        	$wrapper.off("click", ".show-item-popup");
        	$wrapper.off("click", ".dt-cell");
		$wrapper.on("click", ".dt-cell", function (e) {
            		const rowIndex = $(this).closest(".dt-row").data("row-index");

            		if (rowIndex !== undefined) {
                		highlight_row_by_index(datatable, rowIndex);
            		}
        	});
	},
	onload: function() {
        // override ONLY for this report
        frappe.form.link_formatters['Item'] = function(value, doc) {
            // doc here is actually the row data
            return doc.item_code;   // show ONLY item code
        };
    },

    formatter: function(value, row, column, data, default_formatter) {
        return default_formatter(value, row, column, data);
    }

};

// ⭐ Highlight using rowIndex directly
function highlight_row_by_index(datatable, rowIndex) {

    const $wrapper = $(datatable.wrapper);

    // Remove previous highlights
    $wrapper.find(".dt-row--highlight").removeClass("dt-row--highlight");

    // Try native API (works in newer versions)
    if (datatable.rowmanager?.highlightRow) {
        datatable.rowmanager.highlightRow(rowIndex, true);
    }

    // Fallback for versions lacking highlightRow()
    const rowEl = $wrapper.find(`.dt-row[data-row-index="${rowIndex}"]`)[0];
    if (rowEl) {
        rowEl.classList.add("dt-row--highlight");
    }
}

// ⭐ Styling (once)
frappe.dom.set_style(`
    .dt-row--highlight {
        background-color: #EDC0E8 !important;   /* soft yellow */
       transition: background-color 0.2s ease;
    }

    /* Remove default cell border highlight */
    .dt-cell--focus {
       box-shadow: none !important;
       border: none !important;
    }
`);
