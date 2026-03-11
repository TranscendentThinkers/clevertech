frappe.ui.form.on('Purchase Order', {
    custom_required_by_in_days(frm) {
        set_required_by_date(frm);
    },
    transaction_date(frm) {
        set_required_by_date(frm);
    },
    onload(frm) {
        // Skip SQ and SQC from Frappe's "Cancel All" linked-doc flow.
        // Our server-side on_cancel hook cancels them in the correct order
        // (PO cancelled first, then cascade to SQ Comparison and SQ).
        frm.ignore_doctypes_on_cancel_all = [
            "Supplier Quotation",
            "Supplier Quotation Comparison"
        ];
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
