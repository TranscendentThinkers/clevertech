frappe.ui.form.on('Purchase Order', {
	 custom_required_by_in_days(frm) {
                set_required_by_date(frm);

    },
        transaction_date(frm){
                set_required_by_date(frm);

    },
        onload(frm){
                set_required_by_date(frm);

    }
});
function set_required_by_date(frm){
        if (frm.doc.custom_required_by_in_days && frm.doc.transaction_date) {
            let new_date = frappe.datetime.add_days(
                frm.doc.transaction_date,
                frm.doc.custom_required_by_in_days
            );

            frm.set_value('schedule_date', new_date);
        }

}
