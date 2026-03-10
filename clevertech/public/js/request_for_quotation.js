frappe.ui.form.on('Request for Quotation', {
    custom_required_by_in_days(frm) {
        set_required_by_date(frm);
    },
    refresh(frm) {
        set_required_by_date(frm);
        if (!frm.is_new()) {
            frm.add_custom_button(__('Supplier Quotation Comparison'), function() {
                frappe.new_doc('Supplier Quotation Comparison', {
                    request_for_quotation: frm.doc.name
                });
            }, __('Create'));
        }
    },
    transaction_date(frm) {
        set_required_by_date(frm);
    },
    schedule_date(frm) {
        sync_schedule_date_to_items(frm);
    }
});

function set_required_by_date(frm) {
    if (frm.doc.custom_required_by_in_days && frm.doc.transaction_date) {
        let new_date = frappe.datetime.add_days(
            frm.doc.transaction_date,
            frm.doc.custom_required_by_in_days
        );
        frm.set_value('schedule_date', new_date);
    }
}

function sync_schedule_date_to_items(frm) {
    if (!frm.doc.schedule_date) return;

    (frm.doc.items || []).forEach(row => {
        frappe.model.set_value(row.doctype, row.name, 'schedule_date', frm.doc.schedule_date);
    });
}
