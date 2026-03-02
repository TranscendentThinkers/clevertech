frappe.ui.form.on('Bulk Quality Inspection', {
    refresh: function(frm) {
        // Set initial visibility based on type field
        toggle_fields_based_on_type(frm);
    },
    
    type: function(frm) {
        // Toggle fields when type changes
        toggle_fields_based_on_type(frm);
    }
});

// Function to toggle field visibility based on type
function toggle_fields_based_on_type(frm) {
    if (frm.doc.type === 'GRN Based') {
        frm.set_df_property('grn_name', 'hidden', 0);
        frm.set_df_property('po_no', 'hidden', 1);
    } else if (frm.doc.type === 'Purchase Order Based') {
        frm.set_df_property('grn_name', 'hidden', 1);
        frm.set_df_property('po_no', 'hidden', 0);
    } else {
        // If no type is selected, hide both
        frm.set_df_property('grn_name', 'hidden', 1);
        frm.set_df_property('po_no', 'hidden', 1);
    }
}

// For grn_items_quality_reqd child table
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
    }
});

// For grn_items_quality_not_reqd child table (if it uses a different child doctype)
frappe.ui.form.on('GRN Item without Quality', {
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
    }
});
