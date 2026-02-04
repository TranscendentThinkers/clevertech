frappe.ui.form.on("Project", {
    refresh(frm) {
        // Button hidden - use "Create BOMs with Validation" on BOM Upload instead
        // Cutover functionality kept in bulk_generation.py if needed for edge cases
        if (false && !frm.is_new()) {
            frm.add_custom_button(
                __("Generate Component Masters"),
                function () {
                    frappe.confirm(
                        __(
                            "This will create Project Component Master records for all active BOMs in project <b>{0}</b>.<br><br>" +
                            "Existing Component Masters will be skipped (no duplicates).<br><br>" +
                            "Proceed?",
                            [frm.doc.name]
                        ),
                        function () {
                            frappe.call({
                                method: "clevertech.project_component_master.bulk_generation.generate_component_masters_from_boms",
                                args: {
                                    project: frm.doc.name,
                                },
                                freeze: true,
                                freeze_message: __(
                                    "Generating Component Masters..."
                                ),
                                callback(r) {
                                    if (r.message) {
                                        let result = r.message;
                                        show_generation_result(
                                            frm,
                                            result
                                        );
                                    }
                                },
                            });
                        }
                    );
                },
                __("Component Master")
            );
        }

        // Phase 5: Update Component Data button (Machine Code Cascade)
        if (!frm.is_new()) {
            frm.add_custom_button(
                __("Update Component Data"),
                function () {
                    frappe.confirm(
                        __(
                            "This will:<br>" +
                            "1. Backfill parent_component links from BOM structure<br>" +
                            "2. Cascade machine codes from root Component Masters to all children<br>" +
                            "3. Rebuild BOM Usage tables<br>" +
                            "4. Backfill procurement records<br><br>" +
                            "<b>Prerequisites:</b><br>" +
                            "• Manually set machine_code on all root Component Masters first<br>" +
                            "• This will overwrite any existing machine_code values on child components<br><br>" +
                            "Continue?"
                        ),
                        function () {
                            frappe.call({
                                method: "clevertech.project_component_master.utils.update_component_data",
                                args: { project: frm.doc.name },
                                freeze: true,
                                freeze_message: __("Updating Component Data..."),
                                callback: function (r) {
                                    if (r.message) {
                                        frappe.msgprint({
                                            title: __("Update Complete"),
                                            message: r.message.summary,
                                            indicator: r.message.has_errors ? "orange" : "green"
                                        });
                                    }
                                }
                            });
                        }
                    );
                },
                __("Component Master")
            );
        }
    },
});

function show_generation_result(frm, result) {
    if (result.created_count === 0 && result.skipped_count === 0) {
        // No BOMs found - msgprint already shown by server
        return;
    }

    let details_html = "";
    if (result.details && result.details.length > 0) {
        let rows = result.details
            .map(function (d) {
                let status_class =
                    d.status === "Created" ? "text-success" : "text-muted";
                let link = d.component_master
                    ? '<a href="/app/project-component-master/' +
                      d.component_master +
                      '">' +
                      d.component_master +
                      "</a>"
                    : "-";
                return (
                    "<tr>" +
                    "<td>" + d.item_code + "</td>" +
                    "<td>" + d.bom + "</td>" +
                    '<td class="' + status_class + '">' + d.status + "</td>" +
                    "<td>" + link + "</td>" +
                    "</tr>"
                );
            })
            .join("");

        details_html =
            '<table class="table table-bordered table-sm" style="margin-top: 15px;">' +
            "<thead><tr>" +
            "<th>Item Code</th>" +
            "<th>BOM</th>" +
            "<th>Status</th>" +
            "<th>Component Master</th>" +
            "</tr></thead>" +
            "<tbody>" + rows + "</tbody>" +
            "</table>";
    }

    let d = new frappe.ui.Dialog({
        title: __("Component Masters Generated"),
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "result_html",
                options:
                    '<div class="alert alert-success">' +
                    "<b>Created:</b> " + result.created_count +
                    " &nbsp;|&nbsp; <b>Skipped:</b> " + result.skipped_count +
                    " &nbsp;|&nbsp; <b>Total BOMs:</b> " +
                    (result.created_count + result.skipped_count) +
                    "</div>" +
                    details_html,
            },
        ],
        size: "large",
        primary_action_label: __("View Component Masters"),
        primary_action: function () {
            frappe.set_route("List", "Project Component Master", {
                project: frm.doc.name,
            });
            d.hide();
        },
    });

    d.show();
}
