frappe.ui.form.on("Purchase Receipt", {
    custom_get_items_from_bulk_quality_inspection(frm) {
        if (!frm.doc.custom_bulk_quality_inspection_for_grn) {
            frappe.msgprint(__('Please select a document first'));
            return;
        }
        frappe.call({
            method: "clevertech.server_scripts.purchase_receipt.get_items_from_bulk_quality_inspection",
            args: {
                bqi_doc: frm.doc.custom_bulk_quality_inspection_for_grn
            },
            callback: function (r) {
                if (!r.message) return;
                const qty_map = {};
                const rejected_qty_map = {};
                const warehouse_map = {};
                const rejected_warehouse_map = {};
                r.message.forEach(row => {
                    qty_map[row.item_code] = row.qty;
                    rejected_qty_map[row.item_code] = row.rejected_qty || 0;
                    warehouse_map[row.item_code] = row.warehouse;
                    rejected_warehouse_map[row.item_code] = row.rejected_warehouse;
                });
                frm.doc.items.forEach(item => {
                    if (qty_map[item.item_code] !== undefined) {
                        item.qty = qty_map[item.item_code];
                        frappe.model.set_value(item.doctype, item.name, 'received_qty', qty_map[item.item_code]);
                //      frappe.model.set_value(item.doctype, item.name, 'rejected_qty', rejected_qty_map[item.item_code]);
                        frappe.model.set_value(item.doctype, item.name, 'warehouse', warehouse_map[item.item_code]);
                        frappe.model.set_value(item.doctype, item.name, 'rejected_warehouse', rejected_warehouse_map[item.item_code]);
                    }
                });
                frm.refresh_field("items");

                // Save the document after populating items from BQI
                frm.save();
            }
        });
    },
    custom_submit_bulk_quality_inspection(frm) {
        if (!frm.doc.custom_bulk_quality_inspection_for_grn) {
            frappe.msgprint(__('Please select a document first'));
            return;
        }

        const do_submit = () => {
            frappe.call({
                method: "clevertech.server_scripts.purchase_receipt.submit_bqi",
                args: {
                    bqi_doc: frm.doc.custom_bulk_quality_inspection_for_grn,
                    pr_name: frm.doc.name
                },
                callback: function (r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({
                            message: __(r.message.message),
                            indicator: 'green'
                        });
                        frm.refresh_field('custom_bulk_quality_inspection_for_grn');
                        frm.reload_doc();
                    }
                },
                error: function(r) {
                    frappe.msgprint(__('Failed to submit BQI document'));
                }
            });
        };

        // If form is dirty, save first then submit; otherwise submit directly
        if (frm.is_dirty()) {
            frm.save().then(() => {
                do_submit();
            });
        } else {
            do_submit();
        }
    },
    before_submit(frm) {
        // Check if any items require inspection but BQI field is empty
        const has_inspection_items = (frm.doc.items || []).some(item => item.custom_inspection_requires);

        if (has_inspection_items && !frm.doc.custom_bulk_quality_inspection_for_grn) {
            // Show a confirmation dialog with the warning before allowing submit
            return new Promise((resolve, reject) => {
                frappe.confirm(
                    __('<strong>Warning:</strong> Check Quality Clearance reports before submitting GRN.<br><br>Some items require inspection but no Quality Clearance document is linked. Do you still want to proceed?'),
                    () => resolve(),   // User clicked "Yes" — proceed with submit
                    () => reject()     // User clicked "No" — cancel submit
                );
            });
        }
    },
    refresh(frm) {
        frm.set_query('custom_bulk_quality_inspection_for_grn', function() {
            const purchase_orders = [...new Set(
                (frm.doc.items || [])
                    .map(item => item.purchase_order)
                    .filter(po => po)
            )];

            if (purchase_orders.length > 0) {
                return {
                    filters: {
                        po_no: ['in', purchase_orders]
                    }
                };
            }
            return {};
        });

        if (frm.doc.custom_bulk_quality_inspection_for_grn) {
            frappe.call({
                method: "frappe.client.get_value",
                args: {
                    doctype: "Quality Clearance",
                    filters: { name: frm.doc.custom_bulk_quality_inspection_for_grn },
                    fieldname: "docstatus"
                },
                callback: function(r) {
                    if (r.message && r.message.docstatus === 1) {
                        frm.refresh_field('custom_bulk_quality_inspection_for_grn');
                    }
                }
            });
        }

        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Quality Clearance'), function() {
                frappe.new_doc('Quality Clearance', {
                    type: 'GRN Based',
                    grn_name: frm.doc.name
                });
            }, __('Create'));
        }
    }
});
