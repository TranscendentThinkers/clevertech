let last_docname = null;

frappe.ui.form.on("Supplier Quotation Comparison", {
    refresh: function(frm) {
        if (last_docname && last_docname !== frm.doc.name) {
            frm.fields_dict.comparison_report.$wrapper.empty();
        }
        last_docname = frm.doc.name;

        calculate_grand_total(frm);

        if (frm.doc.comparison_table && frm.doc.comparison_table.length > 0) {
            render_comparison_from_table(frm);
        }
    },

    request_for_quotation: function(frm) {
        if (frm.fields_dict.comparison_report) {
            frm.fields_dict.comparison_report.$wrapper.empty();
        }
    },

    fetch_report: function(frm) {
        if (!frm.doc.request_for_quotation) {
            frappe.msgprint("Please select Request for Quotation first");
            return;
        }
        if (frm.is_new() || frm.is_dirty()) {
            frm.save().then(() => {
                generate_comparison_report(frm);
            });
        } else {
            generate_comparison_report(frm);
        }
    },

    validate: function(frm) {
        validate_supplier_reason(frm);
    }
});

function validate_supplier_reason(frm) {
    if (!frm.doc.supplier_selection_table) {
        return;
    }

    let errors = [];

    frm.doc.supplier_selection_table.forEach(function(row, index) {
        if (row.suggested_supplier && row.supplier) {
            if (row.suggested_supplier.trim() !== row.supplier.trim()) {
                if (!row.reason || row.reason.trim() === '') {
                    errors.push(`Row ${index + 1} (${row.item_code || 'Item'}): Reason is mandatory when changing supplier from "${row.suggested_supplier}" to "${row.supplier}"`);
                }
            }
        }
    });

    if (errors.length > 0) {
        frappe.msgprint({
            title: __('Validation Error'),
            message: __('Please provide reason for supplier changes:') + '<br><br>' + errors.join('<br>'),
            indicator: 'red'
        });
        frappe.validated = false;
    }
}

frappe.ui.form.on("Supplier Selection Item", {
    supplier: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        
        if (row.suggested_supplier && row.supplier) {
            if (row.suggested_supplier.trim() !== row.supplier.trim()) {
                frappe.show_alert({
                    message: __('Please provide a reason for changing the supplier'),
                    indicator: 'orange'
                }, 5);
            }
        }
        
        fetch_supplier_data(frm, cdt, cdn);
    },
    item_code: function(frm, cdt, cdn) {
        fetch_supplier_data(frm, cdt, cdn);
    },
    qty: function(frm, cdt, cdn) {
        calculate_amount(frm, cdt, cdn);
        calculate_grand_total(frm);
    },
    rate: function(frm, cdt, cdn) {
        calculate_amount(frm, cdt, cdn);
        calculate_grand_total(frm);
    },
    amount: function(frm, cdt, cdn) {
        calculate_grand_total(frm);
    },
    total_tax: function(frm, cdt, cdn) {
        calculate_grand_total(frm);
    },
    supplier_selection_table_remove: function(frm) {
        calculate_grand_total(frm);
    }
});

function fetch_supplier_data(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    let rfq = frm.doc.request_for_quotation;

    if (rfq && row.supplier && row.item_code) {
        frappe.call({
            method: "clevertech.clevertech.doctype.supplier_quotation_comparison.supplier_quotation_comparison.get_supplier_quotation",
            args: {
                rfq: rfq,
                supplier: row.supplier,
                item_code: row.item_code
            },
            callback: function(r) {
                if (r.message) {
                    frappe.model.set_value(cdt, cdn, "supplier_quotation", r.message.name);
                    frappe.model.set_value(cdt, cdn, "rate", r.message.rate || 0);
                    frappe.model.set_value(cdt, cdn, "qty", r.message.qty || 0);
                    frappe.model.set_value(cdt, cdn, "amount", r.message.amount || 0);
                    frappe.model.set_value(cdt, cdn, "total_tax", r.message.total_tax || 0);

                    calculate_grand_total(frm);
                } else {
                    clear_supplier_data(cdt, cdn);
                    calculate_grand_total(frm);
                }
            },
            error: function(r) {
                console.error("Error fetching supplier quotation:", r);
                clear_supplier_data(cdt, cdn);
                calculate_grand_total(frm);
            }
        });
    } else {
        clear_supplier_data(cdt, cdn);
        calculate_grand_total(frm);
    }
}

function calculate_amount(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    let amount = (row.qty || 0) * (row.rate || 0);
    frappe.model.set_value(cdt, cdn, "amount", amount);
}

function calculate_grand_total(frm) {
    if (!frm.doc.supplier_selection_table) {
        frm.set_value('grand_total', 0);
        return;
    }

    let grand_total = 0;

    frm.doc.supplier_selection_table.forEach(function(row) {
        let row_total = (row.amount || 0) + (row.total_tax || 0);
        grand_total += row_total;
    });

    frm.set_value('grand_total', grand_total);
}

function clear_supplier_data(cdt, cdn) {
    frappe.model.set_value(cdt, cdn, "supplier_quotation", "");
    frappe.model.set_value(cdt, cdn, "rate", 0);
    frappe.model.set_value(cdt, cdn, "qty", 0);
    frappe.model.set_value(cdt, cdn, "amount", 0);
    frappe.model.set_value(cdt, cdn, "total_tax", 0);
}

function render_comparison_from_table(frm) {
    const $wrapper = frm.fields_dict.comparison_report.$wrapper;

    if (!frm.doc.comparison_table || frm.doc.comparison_table.length === 0) {
        $wrapper.html("<p>No comparison data available. Click 'Fetch Report' to generate.</p>");
        return;
    }

    let columns = ["Item Code", "Description", "Qty", "UOM", "Last Purchase Rate", "Last Purchase Supplier"];
    let supplierColumns = [];

    let firstDataRow = frm.doc.comparison_table.find(r => r.item_code !== "TOTAL");
    if (firstDataRow && firstDataRow.supplier_rates) {
        try {
            let supplierRates = JSON.parse(firstDataRow.supplier_rates);
            Object.keys(supplierRates).forEach(supplierName => {
                let col = `${supplierName.trim()} - Rate`;
                columns.push(col);
                supplierColumns.push({ name: supplierName.trim(), col: col });
            });
        } catch (e) {
            console.error("Error parsing supplier rates:", e);
        }
    }

    let data = [];
    let lowestRateSuppliers = {};

    frm.doc.comparison_table.forEach(row => {
        let dataRow = {
            "Item Code": row.item_code || "",
            "Description": row.description || "",
            "Qty": row.qty || "",
            "UOM": row.uom || "",
            "Last Purchase Rate": row.last_purchase_rate || "",
            "Last Purchase Supplier": row.last_purchase_supplier || ""
        };

        if (row.item_code === "TOTAL" && row.supplier_grand_totals) {
            try {
                let grandTotals = JSON.parse(row.supplier_grand_totals);
                Object.keys(grandTotals).forEach(supplierName => {
                    dataRow[`${supplierName.trim()} - Rate`] = grandTotals[supplierName];
                });
            } catch (e) {
                console.error("Error parsing supplier grand totals for TOTAL row:", e);
            }
        } else if (row.supplier_rates) {
            try {
                let supplierRates = JSON.parse(row.supplier_rates);
                Object.keys(supplierRates).forEach(supplierName => {
                    dataRow[`${supplierName.trim()} - Rate`] = supplierRates[supplierName];
                });
            } catch (e) {
                console.error("Error parsing supplier rates for row:", e);
            }
        }

        data.push(dataRow);

        if (row.item_code && row.item_code !== "TOTAL" && row.supplier_rates) {
            try {
                let supplierRates = JSON.parse(row.supplier_rates);
                let lowestName = null;
                let lowestRate = Infinity;

                Object.keys(supplierRates).forEach(supplierName => {
                    let rate = supplierRates[supplierName];
                    if (rate !== "N/A" && rate !== null && rate !== undefined && !isNaN(Number(rate))) {
                        if (Number(rate) < lowestRate) {
                            lowestRate = Number(rate);
                            lowestName = supplierName.trim();
                        }
                    }
                });

                if (lowestName !== null) {
                    lowestRateSuppliers[row.item_code] = {
                        supplier: lowestName
                    };
                }
            } catch (e) {
                console.error("Error determining lowest rate for item:", row.item_code, e);
            }
        }
    });

    const html = build_html_table(columns, data, lowestRateSuppliers, {});
    $wrapper.html(html);
}

function generate_comparison_report(frm) {
    const current_doc = frm.doc.name;
    const $wrapper = frm.fields_dict.comparison_report.$wrapper;
    $wrapper.empty();
    $wrapper.html("<p>Loading comparison...</p>");

    frappe.call({
        method: "clevertech.clevertech.doctype.supplier_quotation_comparison.supplier_quotation_comparison.get_comparison_report_data",
        args: {
            docname: current_doc
        },
        freeze: true,
        freeze_message: "Generating comparison...",
        callback: function(r) {
            if (frm.doc.name !== current_doc) return;
            if (!r.message) {
                $wrapper.html("<p>No data available</p>");
                return;
            }

            frappe.call({
                method: 'frappe.client.get',
                args: {
                    doctype: 'Supplier Quotation Comparison',
                    name: frm.doc.name
                },
                callback: function(r) {
                    if (r.message) {
                        if (r.message.supplier_selection_table) {
                            frm.doc.supplier_selection_table = r.message.supplier_selection_table;
                            frm.fields_dict.supplier_selection_table.grid.refresh();
                        }

                        if (r.message.comparison_table) {
                            frm.doc.comparison_table = r.message.comparison_table;
                            render_comparison_from_table(frm);
                        }

                        calculate_grand_total(frm);
                    }
                }
            });
        }
    });
}

function build_html_table(columns, data, lowest_rate_suppliers, supplier_name_to_id) {
    const tableId = `comparison-table-${Math.random().toString(36).substr(2, 9)}`;

    let html = `
        <style>
            .table-scroll-wrapper {
                position: relative;
                overflow-x: auto;
                max-width: 100%;
                margin-top: 10px;
                border: 1px solid #d1d8dd;
                border-radius: 4px;
            }
            .table-scroll-wrapper table {
                margin-bottom: 0;
                width: auto;
            }
            .table-scroll-wrapper th {
                position: sticky;
                top: 0;
                background-color: #f5f7fa;
                z-index: 1;
                min-width: 80px;
                max-width: 150px;
                padding: 8px;
                font-weight: 600;
                white-space: normal;
                word-wrap: break-word;
                vertical-align: top;
            }
            .table-scroll-wrapper td {
                padding: 8px;
                min-width: 80px;
                max-width: 150px;
                white-space: normal;
                word-wrap: break-word;
                vertical-align: top;
            }
            .table-scroll-wrapper td.item-code {
                font-weight: 600;
                background-color: #f9fafb;
            }
            .table-scroll-wrapper td.lowest-rate {
                background-color: #d4edda;
                font-weight: 600;
                color: #155724;
            }
            .table-scroll-wrapper tr.total-row {
                font-weight: 700;
                background-color: #f0f4f7;
                border-top: 2px solid #d1d8dd;
            }
            .table-scroll-wrapper tr.total-row td {
                font-weight: 700;
            }
            .table-scroll-wrapper::before,
            .table-scroll-wrapper::after {
                content: '';
                position: absolute;
                top: 0;
                bottom: 0;
                width: 20px;
                pointer-events: none;
                z-index: 2;
                transition: opacity 0.3s;
            }
            .table-scroll-wrapper::before {
                left: 0;
                background: linear-gradient(to right, rgba(255,255,255,0.9), transparent);
                opacity: 0;
            }
            .table-scroll-wrapper::after {
                right: 0;
                background: linear-gradient(to left, rgba(255,255,255,0.9), transparent);
            }
            .table-scroll-wrapper.scrolled-left::before {
                opacity: 1;
            }
            .table-scroll-wrapper.scrolled-right::after {
                opacity: 0;
            }
        </style>
        <div class="table-scroll-wrapper" id="${tableId}">
        <table class="table table-bordered table-sm">
            <thead>
                <tr>
    `;
    columns.forEach(col => {
        html += `<th>${frappe.utils.escape_html(col)}</th>`;
    });
    html += `</tr></thead><tbody>`;

    data.forEach((row, rowIndex) => {
        const isTotalRow = rowIndex === data.length - 1 && row["Item Code"] === "TOTAL";
        const rowClass = isTotalRow ? ' class="total-row"' : '';
        const itemCode = (row["Item Code"] || "").trim();

        html += `<tr${rowClass}>`;
        columns.forEach((col, idx) => {
            let val = row[col] ?? "";
            if (typeof val === 'number') {
                val = val.toFixed(2);
            }

            let tdClass = '';
            if (idx === 0) {
                tdClass = 'item-code';
            } else if (!isTotalRow && col.includes(' - Rate') && lowest_rate_suppliers[itemCode]) {
                const supplierName = col.replace(' - Rate', '').trim();
                const lowestSupplier = (lowest_rate_suppliers[itemCode].supplier || '').trim();

                if (supplierName === lowestSupplier && String(val).trim() !== "N/A") {
                    tdClass = 'lowest-rate';
                }
            }

            const tdClassAttr = tdClass ? ` class="${tdClass}"` : '';
            html += `<td${tdClassAttr}>${frappe.utils.escape_html(String(val))}</td>`;
        });
        html += `</tr>`;
    });

    html += `</tbody></table></div>
        <script>
            (function() {
                const wrapper = document.getElementById('${tableId}');
                if (!wrapper) return;
                function updateScrollIndicators() {
                    const scrollLeft = wrapper.scrollLeft;
                    const maxScroll = wrapper.scrollWidth - wrapper.clientWidth;
                    if (scrollLeft > 10) {
                        wrapper.classList.add('scrolled-left');
                    } else {
                        wrapper.classList.remove('scrolled-left');
                    }
                    if (scrollLeft < maxScroll - 10) {
                        wrapper.classList.add('scrolled-right');
                    } else {
                        wrapper.classList.remove('scrolled-right');
                    }
                }
                wrapper.addEventListener('scroll', updateScrollIndicators);
                updateScrollIndicators();
            })();
        </script>
    `;
    return html;
}
