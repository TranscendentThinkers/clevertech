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
		//	frappe.model.set_value(item.doctype, item.name, 'rejected_qty', rejected_qty_map[item.item_code]);
			frappe.model.set_value(item.doctype, item.name, 'warehouse', warehouse_map[item.item_code]);
                        frappe.model.set_value(item.doctype, item.name, 'rejected_warehouse', rejected_warehouse_map[item.item_code]);
                    }
                });
                frm.refresh_field("items");
            }
        });
    },

    custom_submit_bulk_quality_inspection(frm) {
        if (!frm.doc.custom_bulk_quality_inspection_for_grn) {
            frappe.msgprint(__('Please select a document first'));
            return;
        }
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
                }
            },
            error: function(r) {
                frappe.msgprint(__('Failed to submit BQI document'));
            }
        });
    }
});
