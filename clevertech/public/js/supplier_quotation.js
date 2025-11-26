frappe.ui.form.on("Supplier Quotation", {
    custom_payment_terms_template(frm) {

        // Clear old rows before adding new ones
        frm.clear_table("custom_payment_schedule");

        if (frm.doc.custom_payment_terms_template) {
            frappe.db.get_doc("Payment Terms Template", frm.doc.custom_payment_terms_template)
                .then(template => {

                    template.terms.forEach(row => {
                        let new_row = frm.add_child("custom_payment_schedule");

                        new_row.payment_term = row.payment_term;
                        new_row.description = row.description;
                        new_row.due_date = row.due_date;
                        new_row.invoice_portion = row.invoice_portion;
                        new_row.payment_amount = row.payment_amount;
                        new_row.discount = row.discount;
                    });

                    frm.refresh_field("custom_payment_schedule");
                    
                });
        }
    }
});

