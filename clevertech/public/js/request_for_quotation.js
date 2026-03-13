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
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Get Items from MR'), function() {
                clevertech_rfq.get_items_from_mr(frm);
            }).addClass('btn-primary');
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


// ── Get Items from MR (Smart) — custom flow ───────────────────────────────────
const clevertech_rfq = {
    get_items_from_mr(frm) {
        let mr_dialog;
        mr_dialog = new frappe.ui.form.MultiSelectDialog({
            doctype: "Material Request",
            target: frm,
            setters: {
                schedule_date: undefined,
                status: undefined,
            },
            get_query() {
                return {
                    filters: {
                        material_request_type: "Purchase",
                        docstatus: 1,
                        status: ["!=", "Stopped"],
                        per_ordered: ["<", 100],
                        company: frm.doc.company,
                    }
                };
            },
            action(selections) {
                if (!selections || !selections.length) return;
                mr_dialog.dialog.hide();
                frappe.call({
                    method: "clevertech.supply_chain.server_scripts.rfq_get_items.check_multi_mr_rfq_status",
                    args: { mr_names: selections },
                    callback(r) {
                        if (!r.message) return;
                        clevertech_rfq._show_fetch_dialog(frm, selections, r.message);
                    }
                });
            }
        });
    },

    _show_fetch_dialog(frm, selections, status) {
        const { has_rfq_no_po, no_rfq, rfq_nos } = status;

        if (no_rfq === 0 && has_rfq_no_po === 0) {
            frappe.msgprint({
                title: __("No Items to Fetch"),
                message: __("All items in the selected MRs already have Purchase Orders."),
                indicator: "orange"
            });
            return;
        }

        if (has_rfq_no_po === 0) {
            clevertech_rfq._do_append(frm, selections, "remaining");
            return;
        }

        if (no_rfq === 0) {
            const rfq_list = rfq_nos.slice(0, 5).join(", ")
                + (rfq_nos.length > 5 ? ` and ${rfq_nos.length - 5} more` : "");
            frappe.confirm(
                __("All fetchable items already have pending RFQ(s) ({0}) but no Purchase Order yet.<br><br>Fetch them anyway?",
                    [rfq_list]),
                () => clevertech_rfq._do_append(frm, selections, "all")
            );
            return;
        }

        const rfq_list = rfq_nos.slice(0, 5).join(", ")
            + (rfq_nos.length > 5 ? ` and ${rfq_nos.length - 5} more` : "");

        const d = new frappe.ui.Dialog({
            title: __("Items with Pending RFQs"),
            fields: [{
                fieldtype: "HTML",
                options: `<p>
                    <b>${has_rfq_no_po}</b> item(s) already have pending RFQ(s)
                    (<i>${rfq_list}</i>) but no Purchase Order yet.
                    <br><br>What would you like to fetch?
                </p>`
            }],
            primary_action_label: __("Only {0} Remaining Items (no RFQ yet)", [no_rfq]),
            primary_action() {
                d.hide();
                clevertech_rfq._do_append(frm, selections, "remaining");
            },
            secondary_action_label: __("All {0} Items (excluding those with PO)", [no_rfq + has_rfq_no_po]),
            secondary_action() {
                d.hide();
                clevertech_rfq._do_append(frm, selections, "all");
            }
        });
        d.show();
    },

    _do_append(frm, selections, fetch_mode) {
        frappe.call({
            method: "clevertech.supply_chain.server_scripts.rfq_get_items.get_items_for_rfq_append",
            args: { mr_names: selections, fetch_mode },
            freeze: true,
            freeze_message: __("Fetching items..."),
            callback(r) {
                if (!r.message || !r.message.length) {
                    frappe.msgprint(__("No items to add."));
                    return;
                }
                r.message.forEach(item => {
                    const row = frappe.model.add_child(frm.doc, "Request for Quotation Item", "items");
                    Object.keys(item).forEach(key => {
                        if (!["name", "parent", "parenttype", "parentfield", "doctype", "docstatus", "idx"].includes(key)) {
                            row[key] = item[key];
                        }
                    });
                });
                frm.refresh_field("items");
            }
        });
    }
};
