frappe.ui.form.on('Material Request', {
        refresh(frm) {
                frm.events.make_custom_buttons(frm);
                frm.events.toggle_warehouses(frm);
        },
        material_request_type(frm) {
                frm.events.toggle_warehouses(frm);
        },
        toggle_warehouses(frm) {
                const hide = frm.doc.material_request_type === "Purchase";
                frm.set_df_property("set_from_warehouse", "hidden", hide);
                frm.set_df_property("set_warehouse", "hidden", hide);
        },
        make_custom_buttons: function (frm) {
        if (frm.doc.docstatus == 0) {
            frm.add_custom_button(
                    __("Bill of Materials"),
                    () => frm.events.get_items_from_bom(frm),
                    __("Get Items From")
            );
        }

        if (frm.doc.docstatus == 1 && frm.doc.status != "Stopped") {
            let precision = frappe.defaults.get_default("float_precision");

            if (flt(frm.doc.per_received, precision) < 100) {
                frm.add_custom_button(__("Stop"), () => frm.events.update_status(frm, "Stopped"));
            }

            if (flt(frm.doc.per_ordered, precision) < 100) {
                let add_create_pick_list_button = () => {
                    frm.add_custom_button(
                            __("Pick List"),
                            () => frm.events.create_pick_list(frm),
                            __("Create")
                    );
                };

                if (frm.doc.material_request_type === "Material Transfer") {
                    add_create_pick_list_button();
                    frm.add_custom_button(
                        __("Material Transfer"),
                        () => frm.events.make_stock_entry(frm),
                        __("Create")
                    );
                    frm.add_custom_button(
                        __("Material Transfer (In Transit)"),
                        () => frm.events.make_in_transit_stock_entry(frm),
                        __("Create")
                    );
                }

                if (frm.doc.material_request_type === "Material Issue") {
                    frm.add_custom_button(
                        __("Issue Material"),
                        () => frm.events.make_stock_entry(frm),
                        __("Create")
                    );
                }

                if (frm.doc.material_request_type === "Customer Provided") {
                    frm.add_custom_button(
                            __("Material Receipt"),
                            () => frm.events.make_stock_entry(frm),
                            __("Create")
                    );
                }

                if (frm.doc.material_request_type === "Purchase") {
                    frm.add_custom_button(
                            __("Purchase Order"),
                            () => frm.events.make_purchase_order(frm),
                            __("Create")
                    );
                    frm.add_custom_button(
                            __("Supplier Quotation"),
                            () => frm.events.make_supplier_quotation(frm),
                            __("Create")
                    );
                    // Standalone button (not in dropdown) — our custom RFQ flow
                    frm.add_custom_button(
                        __("Create RFQ"),
                        () => clevertech_mr.create_rfq(frm)
                    ).addClass("btn-primary");
                }

                if (frm.doc.material_request_type === "Manufacture") {
                    frm.add_custom_button(
                            __("Work Order"),
                            () => frm.events.raise_work_orders(frm),
                            __("Create")
                    );
                }

                if (frm.doc.material_request_type === "Subcontracting") {
                    frm.add_custom_button(
                            __("Subcontracted Purchase Order"),
                            () => frm.events.make_purchase_order(frm),
                            __("Create")
                    );
                }

                frm.page.set_inner_btn_group_as_primary(__("Create"));
                }
        }

        if (frm.doc.docstatus === 0) {
                frm.add_custom_button(
                        __("Sales Order"),
                        () => frm.events.get_items_from_sales_order(frm),
                        __("Get Items From")
                );
        }

        if (frm.doc.docstatus == 1 && frm.doc.status == "Stopped") {
                frm.add_custom_button(__("Re-open"), () => frm.events.update_status(frm, "Submitted"));
        }
    },
        get_items_from_bom: function (frm) {
        var d = new frappe.ui.Dialog({
            title: __("Get Items from BOM"),
            fields: [
                {
                        fieldname: "bom",
                        fieldtype: "Link",
                        label: __("BOM"),
                        options: "BOM",
                        reqd: 1,
                        get_query: function () {
                                return { filters: { docstatus: 1, is_active: 1 } };
                        },
                },
                {
                        fieldname: "warehouse",
                        fieldtype: "Link",
                        label: __("For Warehouse"),
                        options: "Warehouse",
                        reqd: 0,
                        hidden: 1,
                },
                { fieldname: "qty", fieldtype: "Float", label: __("Quantity"), reqd: 1, default: 1 },
                {
                        fieldname: "fetch_exploded",
                        fieldtype: "Check",
                        label: __("Fetch exploded BOM (including sub-assemblies)"),
                        default: 1,
                },
            ],
            primary_action_label: __("Get Items"),
            primary_action(values) {
                if (!values) return;
                values["company"] = frm.doc.company;
                if (!frm.doc.company) frappe.throw(__("Company field is required"));
                frappe.call({
                    method: "erpnext.manufacturing.doctype.bom.bom.get_bom_items",
                    args: values,
                    callback: function (r) {
                        if (!r.message) {
                                frappe.throw(__("BOM does not contain any stock item"));
                        } else {
                            erpnext.utils.remove_empty_first_row(frm, "items");
                            let new_rows = [];
                            $.each(r.message, function (_i, item) {
                                var row = frappe.model.add_child(cur_frm.doc, "Material Request Item", "items");
                                row.item_code = item.item_code;
                                row.item_name = item.item_name;
                                row.description = item.description;
                                row.uom = item.stock_uom;
                                row.stock_uom = item.stock_uom;
                                row.conversion_factor = 1;
                                row.qty = item.qty;
                                row.project = frm.doc.custom_project_;
                                row.bom_no = values.bom;
                                row.custom_bom_qty = item.qty;
                                new_rows.push(row);
                            });
                            frm.set_value('custom_procurement_bom', values.bom);

                            // Fill warehouses immediately from item defaults
                            let item_codes = [...new Set(new_rows.map(row => row.item_code).filter(Boolean))];
                            frappe.call({
                                method: "clevertech.server_scripts.material_request.get_default_warehouses_for_items",
                                args: { item_codes: item_codes, company: frm.doc.company },
                                callback(wh_res) {
                                    let wh_map = wh_res.message || {};
                                    new_rows.forEach(row => {
                                        if (wh_map[row.item_code]) {
                                            frappe.model.set_value(row.doctype, row.name, "warehouse", wh_map[row.item_code]);
                                        }
                                    });
                                    refresh_field("items");
                                }
                            });
                        }
                        d.hide();
                        refresh_field("items");
                    },
                });
            },
        });

        d.show();
    },
    validate: function(frm) {
        if (frm.skip_bom_qty_check) return;

        let items_exceeding = frm.doc.items.filter(i => i.bom_no && i.custom_bom_qty && i.qty > i.custom_bom_qty);

        if (items_exceeding.length > 0 && !frm._bom_qty_warning_shown) {
            frm._bom_qty_warning_shown = true;
            frappe.validated = false;

            let msg = "Following items have MR Qty greater than Budgeted Qty:<br><br>";
            items_exceeding.forEach(row => {
                msg += `<b>${row.item_code}</b>: MR Qty = ${row.qty}, Budgeted Qty = ${row.custom_bom_qty}<br>`;
            });

            frappe.msgprint(msg);
        }
        frm.trigger("check_bom_qty");
    },
        check_bom_qty(frm) {
        if (frm._extra_items_checked) return;

        if (
            frm.doc.material_request_type !== "Purchase" ||
            !frm.doc.custom_project_
        ) {
            return;
        }

        frappe.validated = false;

        frappe.call({
            method: "clevertech.server_scripts.material_request.check_over_requested_items",
            args: { doc: frm.doc },
            callback(r) {
                if (!r.message || !r.message.length) {
                    frm._extra_items_checked = true;
                    frm.save();
                    return;
                }

                show_extra_items_dialog(frm, r.message);
            }
        });
    },
        custom_required_by_in_days(frm) {
                set_required_by_date(frm);
    },
        transaction_date(frm){
                set_required_by_date(frm);
    },
        onload(frm){
                set_required_by_date(frm);
    },
        schedule_date(frm) {
                sync_schedule_date_to_items(frm);
        }
});



frappe.ui.form.on("Material Request Item", {
    item_code: function(frm, cdt, cdn) {
            update_actual_qty(frm,cdt,cdn)
    },
    qty: function(frm, cdt, cdn) {
            update_actual_qty(frm,cdt,cdn)
    },
    refresh: function(frm, cdt, cdn) {
            update_actual_qty(frm,cdt,cdn)
    },
    set_from_warehouse:function(frm, cdt, cdn) {
            update_actual_qty(frm,cdt,cdn)
    },
});

function update_actual_qty(frm,cdt,cdn){
        frappe.call({
            method: "clevertech.server_scripts.material_request.check_item_stock",
            args: {
                parent_doc: frm.doc,
                child_row: locals[cdt][cdn]
            },
            callback: function(r) {
                if (r.message) {
                    frappe.model.set_value(cdt, cdn, "actual_qty", r.message.available_qty);
                }
            }
        });
}

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

function show_extra_items_dialog(frm, items) {

    let html = `
        <p style="color:#b45309">
            The following items were already requested earlier for this project.
        </p>

        <div style="margin-bottom:8px">
            <button class="btn btn-xs btn-default" id="select_all">Select All</button>
            <button class="btn btn-xs btn-default" id="unselect_all">Unselect All</button>
        </div>
    `;

    items.forEach(d => {
        html += `
            <div style="margin:4px 0">
                <input type="checkbox"
                       class="extra-item"
                       value="${d.item_code}">
                <b>${d.item_code}</b>
                <span style="color:#92400e">
                    (Already ordered: ${d.already_requested})
                </span>
            </div>
        `;
    });

    let dialog = new frappe.ui.Dialog({
        title: "Previously Ordered Items",
        fields: [{ fieldtype: "HTML", options: html }],
        secondary_action_label: "Delete Selected Items"
    });

    dialog.$body.on("click", "#select_all", () => {
        dialog.$body.find(".extra-item").prop("checked", true);
    });

    dialog.$body.on("click", "#unselect_all", () => {
        dialog.$body.find(".extra-item").prop("checked", false);
    });

    dialog.set_primary_action("Confirm", () => {
        frm._extra_items_checked = true;
        dialog.hide();
    });

    dialog.set_secondary_action(() => {
        let selected = dialog.$body
            .find(".extra-item:checked")
            .map((_, el) => el.value)
            .get();

        frm.doc.items = frm.doc.items.filter(
            row => !selected.includes(row.item_code)
        );

        frm.refresh_field("items");
        frm._extra_items_checked = true;
        dialog.hide();
    });

    dialog.show();
}


// ── Create RFQ from MR — custom flow ─────────────────────────────────────────
const clevertech_mr = {
    create_rfq(frm) {
        frappe.call({
            method: "clevertech.supply_chain.server_scripts.rfq_get_items.check_mr_rfq_status",
            args: { mr_name: frm.doc.name },
            callback(r) {
                if (!r.message) return;
                const { total, has_rfq_no_po, no_rfq, rfq_nos } = r.message;

                if (no_rfq === 0 && has_rfq_no_po === 0) {
                    frappe.msgprint({
                        title: __("No Items to Fetch"),
                        message: __("All {0} items already have Purchase Orders.", [total]),
                        indicator: "orange"
                    });
                    return;
                }

                if (has_rfq_no_po === 0) {
                    // No pending RFQs — fetch remaining directly, no dialog needed
                    clevertech_mr._do_create_rfq(frm, "remaining");
                    return;
                }

                if (no_rfq === 0) {
                    // All fetchable items already have pending RFQs — confirm before creating
                    const rfq_list = rfq_nos.slice(0, 5).join(", ")
                        + (rfq_nos.length > 5 ? ` and ${rfq_nos.length - 5} more` : "");
                    frappe.confirm(
                        __("All {0} items already have pending RFQ(s) ({1}) but no Purchase Order yet.<br><br>Create a new RFQ anyway?",
                            [has_rfq_no_po, rfq_list]),
                        () => clevertech_mr._do_create_rfq(frm, "all")
                    );
                    return;
                }

                // Mix of pending RFQ and no-RFQ items — ask user
                const rfq_list = rfq_nos.slice(0, 5).join(", ")
                    + (rfq_nos.length > 5 ? ` and ${rfq_nos.length - 5} more` : "");

                const d = new frappe.ui.Dialog({
                    title: __("Items with Pending RFQs"),
                    fields: [{
                        fieldtype: "HTML",
                        options: `<p>
                            <b>${has_rfq_no_po}</b> item(s) already have RFQ(s) pending
                            (<i>${rfq_list}</i>) but no Purchase Order yet.
                            <br><br>What would you like to fetch?
                        </p>`
                    }],
                    primary_action_label: __("Only {0} Remaining Items (no RFQ yet)", [no_rfq]),
                    primary_action() {
                        d.hide();
                        clevertech_mr._do_create_rfq(frm, "remaining");
                    },
                    secondary_action_label: __("All {0} Items (excluding those with PO)", [no_rfq + has_rfq_no_po]),
                    secondary_action() {
                        d.hide();
                        clevertech_mr._do_create_rfq(frm, "all");
                    }
                });
                d.show();
            }
        });
    },

    _do_create_rfq(frm, fetch_mode) {
        frappe.call({
            method: "clevertech.supply_chain.server_scripts.rfq_get_items.make_request_for_quotation",
            args: { source_name: frm.doc.name, fetch_mode },
            freeze: true,
            freeze_message: __("Creating RFQ..."),
            callback(r) {
                if (r.message) {
                    frappe.model.sync(r.message);
                    frappe.set_route("Form", "Request for Quotation", r.message.name);
                }
            }
        });
    }
};
