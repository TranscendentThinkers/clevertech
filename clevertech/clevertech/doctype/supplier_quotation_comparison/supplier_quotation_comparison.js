let last_docname = null;

frappe.ui.form.on("Supplier Quotation Comparison", {
    refresh: function(frm) {
        if (last_docname && last_docname !== frm.doc.name) {
            frm.fields_dict.comparison_report.$wrapper.empty();
        }
        last_docname = frm.doc.name;

        // Hide comparison_table visually — must NOT be hidden at doctype level
        frm.toggle_display('comparison_table', false);

        calculate_grand_total(frm);
        set_supplier_filter(frm);

        if (frm.doc.__islocal) return;

        // Show clear_links button only after submit
        //if (frm.doc.docstatus === 1) {
        //    frm.toggle_display('clear_links', true);
        //} else {
        //    frm.toggle_display('clear_links', false);
        //}

        if (frm.doc.comparison_table && frm.doc.comparison_table.length > 0) {
            render_comparison_from_table(frm);
        }
    },

    request_for_quotation: function(frm) {
        if (frm.fields_dict.comparison_report) {
            frm.fields_dict.comparison_report.$wrapper.empty();
        }
        set_supplier_filter(frm);
    },

    required_by_in_days: function(frm) {
        if (frm.doc.required_by_in_days && frm.doc.required_by_in_days > 0) {
            let required_by_date = frappe.datetime.add_days(frappe.datetime.get_today(), frm.doc.required_by_in_days);
            frm.set_value('required_by_date', required_by_date);
        }
    },

    fetch_report: function(frm) {
        if (!frm.doc.request_for_quotation) {
            frappe.msgprint("Please select Request for Quotation first");
            return;
        }
        if (frm.is_dirty()) {
            frm.save().then(() => {
                generate_comparison_report(frm);
            }).catch((error) => {
                console.log("Validation failed, not generating report");
            });
        } else {
            generate_comparison_report(frm);
        }
    },

    validate: function(frm) {
        validate_supplier_reason(frm);
    },

    clear_links: function(frm) {
        frappe.confirm(
            __('This will clear all Purchase Order and Supplier Quotation references from the selection table. Are you sure?'),
            function() {
                frappe.call({
                    method: "clevertech.clevertech.doctype.supplier_quotation_comparison.supplier_quotation_comparison.clear_selection_table_links",
                    args: { docname: frm.doc.name },
                    freeze: true,
                    freeze_message: __("Clearing links..."),
                    callback: function(r) {
                        if (!r.exc) {
                            frappe.show_alert({
                                message: __("Purchase Order and Supplier Quotation links cleared successfully"),
                                indicator: "green"
                            }, 4);
                            frm.reload_doc();
                        }
                    }
                });
            }
        );
    },

});

function validate_supplier_reason(frm) {
    if (!frm.doc.supplier_selection_table) {
        return;
    }

    let reason_errors = [];

    frm.doc.supplier_selection_table.forEach(function(row, index) {
        if (row.suggested_supplier && row.supplier) {
            if (row.suggested_supplier.trim() !== row.supplier.trim()) {
                if (!row.reason || row.reason.trim() === '') {
                    reason_errors.push(`Row ${index + 1} (${row.item_code || 'Item'}): Reason is mandatory when changing supplier from "${row.suggested_supplier}" to "${row.supplier}"`);
                }
            }
        }
    });

    if (reason_errors.length > 0) {
        frappe.msgprint({
            title: __('Validation Error'),
            message: __('Please provide reason for supplier changes:') + '<br><br>' + reason_errors.join('<br>'),
            indicator: 'red'
        });
        frappe.validated = false;
    }

    // Only check rates when submitting
    if (cur_frm.is_submitting) {
        validate_rates_before_submit(frm);
    }
}

function validate_rates_before_submit(frm) {
    if (!frm.doc.supplier_selection_table) {
        return;
    }

    let rate_errors = [];

    frm.doc.supplier_selection_table.forEach(function(row, index) {
        if (!row.supplier || !row.supplier_quotation || !row.rate || row.rate === 0) {
            rate_errors.push(`Row ${index + 1} (${row.item_code || 'Item'}): No valid supplier or rate selected`);
        }
    });

    if (rate_errors.length > 0) {
        frappe.msgprint({
            title: __('Cannot Submit'),
            message: __('The following items have no valid supplier/rate and cannot be used to create Purchase Orders:<br><br>') + rate_errors.join('<br>'),
            indicator: 'red'
        });
        frappe.validated = false;
    }
}

function set_supplier_filter(frm) {
    if (!frm.doc.request_for_quotation) {
        return;
    }

    frappe.call({
        method: 'frappe.client.get',
        args: {
            doctype: 'Request for Quotation',
            name: frm.doc.request_for_quotation
        },
        callback: function(r) {
            if (r.message && r.message.suppliers) {
                let supplier_list = r.message.suppliers.map(s => s.supplier);

                frm.fields_dict.supplier_selection_table.grid.get_field('supplier').get_query = function(doc, cdt, cdn) {
                    return {
                        filters: {
                            name: ['in', supplier_list]
                        }
                    };
                };

                frm.fields_dict.supplier_selection_table.grid.refresh();
            }
        }
    });
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
    material_request: function(frm, cdt, cdn) {
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
                item_code: row.item_code,
                material_request: row.material_request || "",
                rfq_item_row: row.rfq_item_row || ""
            },
            callback: function(r) {
                if (r.message) {
                    frappe.model.set_value(cdt, cdn, "supplier_quotation", r.message.name);
                    frappe.model.set_value(cdt, cdn, "rate", r.message.rate || 0);
                    frappe.model.set_value(cdt, cdn, "qty", r.message.qty || 0);
                    frappe.model.set_value(cdt, cdn, "amount", r.message.amount || 0);
                    frappe.model.set_value(cdt, cdn, "total_tax", r.message.total_tax || 0);
                    frappe.model.set_value(cdt, cdn, "delivery_term", r.message.delivery_term || "");
                    frappe.model.set_value(cdt, cdn, "payment_terms_template", r.message.payment_terms_template || "");
                    frappe.model.set_value(cdt, cdn, "notes", r.message.notes || "");

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
        grand_total += (row.amount || 0);
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

    let columns = ["Item Code", "Material Request", "Description", "Qty", "UOM", "Last Purchase Rate", "Last Purchase Supplier"];
    let supplierColumns = [];

    let firstDataRow = frm.doc.comparison_table.find(r => r.item_code !== "TOTAL");
    if (firstDataRow && firstDataRow.supplier_rates) {
        try {
            let supplierRates = JSON.parse(firstDataRow.supplier_rates);
            Object.keys(supplierRates).forEach(supplierName => {
                if (supplierName.startsWith("__")) return;
                let col = `${supplierName.trim()} - Rate`;
                columns.push(col);
                supplierColumns.push({ name: supplierName.trim(), col: col });
            });
        } catch (e) {
            console.error("Error parsing supplier rates:", e);
        }
    }

    let data = [];

    frm.doc.comparison_table.forEach(row => {
        let dataRow = {
            "Item Code": row.item_code || "",
            "Material Request": row.material_request || "",
            "Description": row.description || "",
            "Qty": row.qty || "",
            "UOM": row.uom || "",
            "Last Purchase Rate": row.last_purchase_rate || "",
            "Last Purchase Supplier": row.last_purchase_supplier || "",
            "__lowest_supplier__": null,
            "__na_suppliers__": []
        };

        if (row.item_code === "TOTAL" && row.supplier_grand_totals) {
            try {
                let grandTotals = JSON.parse(row.supplier_grand_totals);
                Object.keys(grandTotals).forEach(supplierName => {
                    // grandTotals entries are now {value, currency_symbol} objects
                    const entry = grandTotals[supplierName];
                    if (entry && typeof entry === "object") {
                        const sym = entry.currency_symbol || "";
                        const val = entry.value;
                        if (val === "No Quotation") {
                            dataRow[`${supplierName.trim()} - Rate`] = "No Quotation";
                        } else {
                            dataRow[`${supplierName.trim()} - Rate`] = sym ? `${sym}${Number(val).toFixed(2)}` : Number(val).toFixed(2);
                        }
                    } else {
                        // Fallback for old data without currency_symbol
                        dataRow[`${supplierName.trim()} - Rate`] = entry;
                    }
                });
            } catch (e) {
                console.error("Error parsing supplier grand totals for TOTAL row:", e);
            }
        } else if (row.supplier_rates) {
            try {
                let supplierRates = JSON.parse(row.supplier_rates);
                let itemNaSuppliers = [];

                Object.keys(supplierRates).forEach(supplierName => {
                    if (supplierName.startsWith("__")) return;

                    const entry = supplierRates[supplierName];
                    let rateVal, displayVal;

                    if (entry && typeof entry === "object") {
                        // New format: {rate, currency_symbol}
                        rateVal = entry.rate;
                        const sym = entry.currency_symbol || "";
                        if (rateVal === "N/A" || rateVal === null || rateVal === undefined || rateVal === 0 || rateVal === "0") {
                            displayVal = "N/A";
                        } else {
                            displayVal = sym ? `${sym}${Number(rateVal).toFixed(2)}` : Number(rateVal).toFixed(2);
                        }
                    } else {
                        // Fallback for old data stored as plain value
                        rateVal = entry;
                        displayVal = (rateVal === "N/A" || rateVal === null || rateVal === undefined || rateVal === 0 || rateVal === "0")
                            ? "N/A"
                            : rateVal;
                    }

                    dataRow[`${supplierName.trim()} - Rate`] = displayVal;

                    if (displayVal === "N/A") {
                        itemNaSuppliers.push(supplierName.trim());
                    }
                });

                // Determine lowest supplier for green highlight
                // Read from Python-embedded __lowest__ key (display name already resolved)
                const lowestFromPython = supplierRates["__lowest__"];
                if (lowestFromPython) {
                    dataRow["__lowest_supplier__"] = lowestFromPython.trim();
                } else {
                    // Fallback: find lowest by numeric rate value
                    let lowestName = null, lowestRate = Infinity;
                    Object.keys(supplierRates).forEach(supplierName => {
                        if (supplierName.startsWith("__")) return;
                        const entry = supplierRates[supplierName];
                        const rateVal = (entry && typeof entry === "object") ? entry.rate : entry;
                        if (!isNaN(Number(rateVal)) && Number(rateVal) > 0 && Number(rateVal) < lowestRate) {
                            lowestRate = Number(rateVal);
                            lowestName = supplierName.trim();
                        }
                    });
                    if (lowestName !== null) dataRow["__lowest_supplier__"] = lowestName;
                }

                dataRow["__na_suppliers__"] = itemNaSuppliers;
            } catch (e) {
                console.error("Error determining lowest/NA rates for item:", row.item_code, e);
            }
        }

        data.push(dataRow);
    });

    const html = build_html_table(columns, data);
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

            // Reload doc so frm.doc.comparison_table is fresh from DB
            frm.reload_doc();

            frappe.show_alert({
                message: __('Comparison report generated and saved successfully'),
                indicator: 'green'
            }, 3);
        },
        error: function(r) {
            $wrapper.html("<p>Error generating comparison report. Please try again.</p>");
            frappe.msgprint({
                title: __('Error'),
                message: __('Failed to generate comparison report'),
                indicator: 'red'
            });
        }
    });
}

const SPECIAL_ROW_LABELS = {
    "TOTAL": "Total",
    "PAYMENT_TERMS": "Payment Terms",
    "DELIVERY_TERMS": "Delivery Terms",
    "NOTES": "Notes"
};

function build_html_table(columns, data) {
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
            .table-scroll-wrapper td.na-rate {
                background-color: #f8d7da;
                font-weight: 600;
                color: #721c24;
            }
            .table-scroll-wrapper tr.extra-info-row {
                background-color: #fffbf0;
                border-top: 1px solid #e0d9c8;
            }
            .table-scroll-wrapper td.special-row-label {
                font-weight: 600;
                background-color: #f5f0e8;
                color: #5a4a2a;
            }
            .table-scroll-wrapper td.extra-info-cell {
                white-space: pre-wrap;
                font-size: 12px;
                color: #4a4a4a;
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

    data.forEach((row) => {
        const itemCode = (row["Item Code"] || "").trim();
        const isSpecialRow = SPECIAL_ROW_LABELS.hasOwnProperty(itemCode);
        const isTotalRow = itemCode === "TOTAL";
        const isExtraRow = ["PAYMENT_TERMS", "DELIVERY_TERMS", "NOTES"].includes(itemCode);

        let rowClass = '';
        if (isTotalRow) rowClass = ' class="total-row"';
        else if (isExtraRow) rowClass = ' class="extra-info-row"';

        html += `<tr${rowClass}>`;
        columns.forEach((col, idx) => {
            let val = row[col] ?? "";

            // Only auto-format numbers for non-rate columns (rate cells are already
            // formatted as "₹1500.00" strings by render_comparison_from_table)
            if (typeof val === 'number') {
                val = val.toFixed(2);
            }

            let tdClass = '';

            if (idx === 0) {
                if (isSpecialRow) {
                    val = SPECIAL_ROW_LABELS[itemCode];
                    tdClass = 'special-row-label';
                } else {
                    tdClass = 'item-code';
                }
            } else if (isSpecialRow && col === "Material Request") {
                val = "";
            } else if (isSpecialRow && col === "Description") {
                val = "";
            } else if (isSpecialRow && ["Qty", "UOM", "Last Purchase Rate", "Last Purchase Supplier"].includes(col)) {
                val = "";
            } else if (!isSpecialRow && col.includes(' - Rate')) {
                const supplierName = col.replace(' - Rate', '').trim();
                const strVal = String(val).trim();

                // N/A detection: pure "N/A", empty, or a bare zero (not a formatted symbol+number)
                const isNA = strVal === "N/A" || strVal === "" || strVal === "0" || strVal === "0.00";
                const isLowest = !isNA &&
                    row["__lowest_supplier__"] &&
                    row["__lowest_supplier__"].trim() === supplierName;

                if (isNA) {
                    tdClass = 'na-rate';
                    val = "N/A";
                } else if (isLowest) {
                    tdClass = 'lowest-rate';
                }
            } else if (isExtraRow && col.includes(' - Rate')) {
                tdClass = 'extra-info-cell';
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
