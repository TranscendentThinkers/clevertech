frappe.ui.form.on('Material Request', {
        refresh(frm) {
                frm.events.make_custom_buttons(frm);
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
                            __("Request for Quotation"),
                            () => frm.events.make_request_for_quotation(frm),
                            __("Create")
                    );

                    frm.add_custom_button(
                            __("Supplier Quotation"),
                            () => frm.events.make_supplier_quotation(frm),
                            __("Create")
                    );
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
                        reqd: 1,
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
                            $.each(r.message, function (i, item) {
                                var d = frappe.model.add_child(cur_frm.doc, "Material Request Item", "items");
                                d.item_code = item.item_code;
                                d.item_name = item.item_name;
                                d.description = item.description;
                                d.warehouse = values.warehouse;
                               d.uom = item.stock_uom;
                                d.stock_uom = item.stock_uom;
                                d.conversion_factor = 1;
                                d.qty = item.qty;
                                d.project = item.project;
                                d.bom_no = values.bom;
                                d.custom_bom_qty = item.qty;
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
       // Skip if already confirmed once
        if (frm.skip_bom_qty_check) return;

        let items_exceeding = frm.doc.items.filter(i => i.bom_no && i.custom_bom_qty && i.qty > i.custom_bom_qty);

        if (items_exceeding.length > 0) {
            frappe.validated = false; // stop normal validation temporarily

            let msg = "Following items have Qty greater than BOM Qty:<br><br>";
            items_exceeding.forEach(row => {
                msg += `<b>${row.item_code}</b>: Qty = ${row.qty}, BOM Qty = ${row.custom_bom_qty}<br>`;
            });

	   frappe.msgprint(msg);
	   frappe.validated = false;

        }
    },
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
