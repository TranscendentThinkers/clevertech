frappe.ui.form.on('Quality Clearance', {
    refresh: function(frm) {
        toggle_fields_based_on_type(frm);
        apply_supplier_filters(frm);

        // Make supplier read-only once the document has been saved
        if (!frm.is_new()) {
            frm.set_df_property('supplier', 'read_only', 1);

            frm.add_custom_button('Print QC', function() {
                frappe.call({
                    method: 'clevertech.clevertech.doctype.quality_clearance.quality_clearance.get_qc_print_html',
                    args: { doc_name: frm.doc.name },
                    callback: function(r) {
                        if (r.message) {
                            const blob = new Blob([r.message], { type: 'text/html' });
                            const url = URL.createObjectURL(blob);
                            const w = window.open(url, '_blank');
                            setTimeout(() => URL.revokeObjectURL(url), 10000);
                        }
                    }
                });
            });
        }
    },
    type: function(frm) {
        toggle_fields_based_on_type(frm);
    },
    supplier: function(frm) {
        apply_supplier_filters(frm);
        frm.set_value('grn_name', '');
        frm.set_value('po_no', '');
    }
});

function toggle_fields_based_on_type(frm) {
    if (frm.doc.type === 'GRN Based') {
        frm.set_df_property('grn_name', 'hidden', 0);
        frm.set_df_property('po_no', 'hidden', 1);
    } else if (frm.doc.type === 'Purchase Order Based') {
        frm.set_df_property('grn_name', 'hidden', 1);
        frm.set_df_property('po_no', 'hidden', 0);
    } else {
        frm.set_df_property('grn_name', 'hidden', 1);
        frm.set_df_property('po_no', 'hidden', 1);
    }

    // Make qty_to_inspect read-only in child table when type is GRN Based
    const is_grn_based = frm.doc.type === 'GRN Based';
    frm.fields_dict['grn_items_quality_reqd'].grid.toggle_enable('qty_to_inspect', !is_grn_based);
}

function apply_supplier_filters(frm) {
    frm.set_query('grn_name', function() {
        let filters = { docstatus: 1, custom_quality_status: 'Pending' };
        if (frm.doc.supplier) {
            filters['supplier'] = frm.doc.supplier;
        }
        return { filters: filters };
    });

    frm.set_query('po_no', function() {
        let filters = { docstatus: 1, per_received: ['<', 100] };
        if (frm.doc.supplier) {
            filters['supplier'] = frm.doc.supplier;
        }
        return { filters: filters };
    });
}

frappe.ui.form.on('GRN Item', {
    accepted_qty: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.accepted_qty !== undefined && row.qty_to_inspect !== undefined) {
            frappe.model.set_value(cdt, cdn, 'rejected_qty', row.qty_to_inspect - row.accepted_qty);
        }
    },
    qty_to_inspect: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.accepted_qty !== undefined && row.qty_to_inspect !== undefined) {
            frappe.model.set_value(cdt, cdn, 'rejected_qty', row.qty_to_inspect - row.accepted_qty);
        }
    },
    rejected_qty: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.qty_to_inspect !== undefined && row.rejected_qty !== undefined) {
            frappe.model.set_value(cdt, cdn, 'accepted_qty', row.qty_to_inspect - row.rejected_qty);
        }
    }
});
