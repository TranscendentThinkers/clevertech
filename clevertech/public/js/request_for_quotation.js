frappe.ui.form.on('Request for Quotation', {
    custom_required_by_in_days(frm) {
        if (frm.doc.custom_required_by_in_days && frm.doc.transaction_date) {
            let new_date = frappe.datetime.add_days(
                frm.doc.transaction_date,
                frm.doc.custom_required_by_in_days
            );

            frm.set_value('schedule_date', new_date);
        }
    }
});

