frappe.ui.form.on('BOM Upload', {
    refresh(frm) {
        // Hide the Phase 2 button (not ready for use)
        frm.toggle_display('create_boms_with_validation', false);

        if (!frm.is_new()) {
            // Phase 1 button — simple upload, no procurement blocking
            frm.add_custom_button(__('Create BOM - Phase 1'), function() {
                if (!frm.doc.bom_file) {
                    frappe.msgprint(__('Please attach a BOM Excel file first.'));
                    return;
                }
                if (!frm.doc.project) {
                    frappe.msgprint(__('Please select a Project first.'));
                    return;
                }
                _run_phase1_upload(frm, false);
            }).addClass('btn-primary');
        }

        frm.add_custom_button(__('Debug bom_qty_required'), function() {
            _run_debug_bom_qty_recalc(frm);
        }, __('Debug'));
    },

    create_boms(frm) {
        if (!frm.doc.bom_file) {
            frappe.msgprint("Please attach a BOM Excel file first.");
            return;
        }

        frappe.call({
            method: 'clevertech.clevertech.doctype.bom_upload.bom_upload.create_boms',
            args: {
                docname: frm.doc.name
            },
            freeze: true,
            freeze_message: __('Creating BOMs...'),
            callback(r) {
                if (!r.message) {
                    frappe.msgprint({
                        title: __('Error'),
                        message: __('No response from server'),
                        indicator: 'red'
                    });
                    return;
                }

                const msg = r.message;
                let error_html = '';

                if (msg.errors && msg.errors.length > 0) {
                    error_html = '<br><br><strong>Errors:</strong><br>' + msg.errors.join('<br>');
                }

                frappe.msgprint({
                    title: __('BOM Import Result'),
                    message: `
                        <strong>BOMs Created:</strong> ${msg.created}<br>
                        <strong>BOMs Skipped:</strong> ${msg.skipped}<br>
                        <strong>Failed:</strong> ${msg.failed}
                        ${error_html}
                    `,
                    indicator: msg.failed > 0 ? 'orange' : 'green'
                });

                frm.reload_doc();
            },
            error(r) {
                frappe.msgprint({
                    title: __('Error'),
                    message: __('Failed to create BOMs. Please check the error log.'),
                    indicator: 'red'
                });
            }
        });
    },

    create_boms_with_validation(frm) {
        if (!frm.doc.bom_file) {
            frappe.msgprint("Please attach a BOM Excel file first.");
            return;
        }

        if (!frm.doc.project) {
            frappe.msgprint("Please select a Project first.");
            return;
        }

        frappe.call({
            method: 'clevertech.clevertech.doctype.bom_upload.bom_upload_enhanced.create_boms_with_validation',
            args: {
                docname: frm.doc.name
            },
            freeze: true,
            freeze_message: __('Analyzing BOM upload...'),
            callback(r) {
                if (!r.message) {
                    frappe.msgprint({
                        title: __('Error'),
                        message: __('No response from server'),
                        indicator: 'red'
                    });
                    return;
                }

                const result = r.message;
                console.log("BOM Upload Result:", JSON.stringify(result, null, 2));

                if (result.status === 'blocked') {
                    _show_loose_items_blocked_dialog(result);
                }
                else if (result.status === 'procurement_blocked') {
                    _show_procurement_block_dialog(result, frm);
                }
                else if (result.status === 'manager_required') {
                    _show_manager_required_dialog(result);
                }
                else if (result.status === 'requires_confirmation') {
                    _show_confirmation_dialog(result, frm);
                }
                else if (result.status === 'requires_resolution') {
                    // Legacy fallback - should not hit this with new logic
                    _show_change_resolution_dialog(result.analysis, frm);
                }
                else if (result.status === 'success') {
                    _show_upload_success(result);
                    frm.reload_doc();
                }
            },
            error(r) {
                frappe.msgprint({
                    title: __('Error'),
                    message: __('Failed to process BOM upload. Check error log.'),
                    indicator: 'red'
                });
            }
        });
    },

    debug_bom_quantities(frm) {
        if (!frm.doc.bom_file) {
            frappe.msgprint("Please attach a BOM Excel file first.");
            return;
        }

        // Prompt for target item code
        frappe.prompt(
            {
                label: 'Target Item Code',
                fieldname: 'target_item',
                fieldtype: 'Data',
                description: 'Leave empty to auto-select most frequent item'
            },
            function(values) {
                frappe.call({
                    method: 'clevertech.clevertech.doctype.bom_upload.bom_upload_enhanced.debug_bom_quantities',
                    args: {
                        docname: frm.doc.name,
                        target_item_code: values.target_item || null
                    },
                    freeze: true,
                    freeze_message: __('Analyzing BOM quantities...'),
                    callback(r) {
                        if (!r.message) {
                            frappe.msgprint({
                                title: __('Error'),
                                message: __('No response from server'),
                                indicator: 'red'
                            });
                            return;
                        }

                        _show_debug_results(r.message);
                    },
                    error(r) {
                        frappe.msgprint({
                            title: __('Error'),
                            message: __('Failed to analyze quantities. Check error log.'),
                            indicator: 'red'
                        });
                    }
                });
            },
            __('Debug BOM Quantities'),
            __('Analyze')
        );
    }
});


// ==================== Phase 1 Upload ====================

function _run_phase1_upload(frm, confirmed, state_confirmed) {
    frappe.call({
        method: 'clevertech.clevertech.doctype.bom_upload.bom_upload_phase1.create_boms_phase1',
        args: {
            docname: frm.doc.name,
            confirmed: confirmed ? 1 : 0,
            state_confirmed: state_confirmed ? 1 : 0
        },
        freeze: true,
        freeze_message: confirmed ? __('Creating BOMs...') : __('Analyzing BOM upload...'),
        callback(r) {
            if (!r.message) {
                frappe.msgprint({ title: __('Error'), message: __('No response from server'), indicator: 'red' });
                return;
            }

            const result = r.message;

            if (result.status === 'needs_state_confirmation') {
                const w = result.warnings || {};
                let html = '<div class="alert alert-warning" style="margin-bottom:12px">'
                    + '<b>The following items have non-Released design status.</b><br>'
                    + 'Component Masters and BOMs will still be created for them.<br>'
                    + 'However, these items <b>cannot be procured</b> until their status is Released.'
                    + '</div>';

                if (w.obsolete && w.obsolete.length) {
                    html += '<p><b>Obsolete items (' + w.obsolete.length + '):</b></p><ul>';
                    w.obsolete.forEach(function(item) {
                        html += '<li><b>' + item.item_code + '</b>'
                            + (item.description ? ' — ' + item.description : '') + '</li>';
                    });
                    html += '</ul>';
                }
                if (w.other && w.other.length) {
                    html += '<p><b>Non-Released items (' + w.other.length + '):</b></p><ul>';
                    w.other.forEach(function(item) {
                        html += '<li><b>' + item.item_code + '</b> — STATE: ' + item.state
                            + (item.description ? ' — ' + item.description : '') + '</li>';
                    });
                    html += '</ul>';
                }
                html += '<p style="margin-top:12px">Proceed with upload?</p>';

                frappe.confirm(
                    html,
                    function() {
                        // Yes — re-call with state_confirmed=true
                        _run_phase1_upload(frm, false, true);
                    },
                    function() {
                        // No — cancel cleanly
                        frappe.msgprint({
                            title: __('Upload Cancelled'),
                            message: __('No changes were made.'),
                            indicator: 'blue'
                        });
                    }
                );
                return;
            }

            if (result.status === 'needs_confirmation') {
                const changes = result.version_changes || [];
                const items_html = changes.map(function(c) {
                    return '<li><b>' + c.item_code + '</b>'
                        + (c.description ? ' — ' + c.description : '')
                        + '<br><small>Current BOM: <a href="/app/bom/' + c.existing_bom + '">'
                        + c.existing_bom + '</a></small></li>';
                }).join('');

                frappe.confirm(
                    '<p>The following BOMs will be updated to a new version:</p>'
                    + '<ul style="margin-top:8px">' + items_html + '</ul>'
                    + '<p style="margin-top:12px">Proceed with version update?</p>',
                    function() {
                        // Yes — re-call with confirmed=true, preserving state_confirmed
                        _run_phase1_upload(frm, true, state_confirmed);
                    },
                    function() {
                        // No — cancel cleanly
                        frappe.msgprint({
                            title: __('Upload Cancelled'),
                            message: __('No BOMs were created or modified. Items and Component Masters created earlier are retained.'),
                            indicator: 'blue'
                        });
                    }
                );
                return;
            }

            if (result.status === 'success') {
                _show_upload_success(result);
                frm.reload_doc();
            }
        },
        error() {
            frappe.msgprint({
                title: __('Error'),
                message: __('Failed to process BOM upload. Check error log.'),
                indicator: 'red'
            });
        }
    });
}


// ==================== Dialog Functions ====================

function _show_loose_items_blocked_dialog(data) {
    let items_html = '';
    if (data.analysis && data.analysis.loose_blocked) {
        items_html = data.analysis.loose_blocked.map(function(item) {
            return '<li><b>' + (item.node ? item.node.item_code : 'Unknown') + '</b>'
                + ' - ' + (item.details ? item.details.message : 'Conversion not enabled')
                + '<br><small>Go to Project Component Master to enable conversion</small></li>';
        }).join('');
    }

    let html = '<div class="alert alert-danger">'
        + '<h5><i class="fa fa-lock"></i> Loose Items Blocking BOM Creation</h5>'
        + '<p>The following loose items must have "Can be converted to BOM" enabled first:</p>'
        + '<ul>' + items_html + '</ul>'
        + '</div>';

    frappe.msgprint({
        title: __('Upload Blocked'),
        message: html,
        indicator: 'red',
        primary_action: {
            label: __('Open Component Master List'),
            action: function() {
                frappe.set_route('List', 'Project Component Master', {
                    'is_loose_item': 1
                });
            }
        }
    });
}

function _show_change_resolution_dialog(analysis, frm) {
    let changed_components = analysis.changed_components || [];
    let blocked_components = analysis.blocked_by_dependencies || {};
    let summary = analysis.summary || {};

    let changed_html = '';
    if (changed_components.length > 0) {
        changed_html = '<div class="changed-components" style="margin-bottom:20px">'
            + '<h6 class="text-warning"><i class="fa fa-exclamation-triangle"></i> Changed Components Requiring Resolution:</h6>';

        changed_components.forEach(function(comp, idx) {
            let node = comp.node || {};
            let details = comp.details || {};
            let procurement_html = '';

            if (details.procurement_status && details.procurement_status.length > 0) {
                procurement_html = '<div class="alert alert-warning">'
                    + '<b><i class="fa fa-warning"></i> Active Procurement:</b>'
                    + '<ul style="margin:5px 0 0 20px">'
                    + details.procurement_status.map(function(doc) {
                        return '<li>' + doc.doctype + ': ' + doc.name + ' (' + doc.status + ')</li>';
                    }).join('')
                    + '</ul></div>';
            }

            changed_html += '<div class="card mb-3" style="border-left:3px solid #ffa00a;padding:10px;margin-bottom:10px">'
                + '<h6>[' + (idx + 1) + '/' + changed_components.length + '] ' + node.item_code + '</h6>'
                + '<p><b>Change Type:</b> ' + (details.change_type || 'Unknown') + '</p>'
                + '<p><b>Old BOM:</b> '
                + (details.old_bom
                    ? '<a href="/app/bom/' + details.old_bom + '">' + details.old_bom + '</a>'
                    : 'None')
                + '</p>'
                + procurement_html
                + '<p class="text-muted"><small><i class="fa fa-info-circle"></i> '
                + 'Action: Deactivate old BOM manually, then re-run upload</small></p>'
                + '</div>';
        });

        changed_html += '</div>';
    }

    let blocked_html = '';
    let blocked_keys = Object.keys(blocked_components);
    if (blocked_keys.length > 0) {
        blocked_html = '<div class="blocked-components">'
            + '<h6 class="text-danger"><i class="fa fa-ban"></i> Components Blocked by Dependencies:</h6>'
            + '<ul>';

        blocked_keys.forEach(function(item) {
            let reasons = blocked_components[item] || [];
            blocked_html += '<li><b>' + item + '</b><ul style="margin-left:20px">';
            reasons.forEach(function(r) {
                blocked_html += '<li>' + r.item + ': ' + r.reason + '</li>';
            });
            blocked_html += '</ul></li>';
        });

        blocked_html += '</ul></div>';
    }

    let html = '<div class="bom-change-resolution">'
        + '<h5><i class="fa fa-warning"></i> BOM Upload Analysis</h5>'
        + '<div class="summary" style="margin:15px 0">'
        + '<table class="table table-bordered table-sm">'
        + '<tr class="text-success"><td><i class="fa fa-check"></i> Can Create Immediately:</td>'
        + '<td><b>' + (summary.can_create || 0) + '</b> components</td></tr>'
        + '<tr class="text-warning"><td><i class="fa fa-exclamation-triangle"></i> Changed Components:</td>'
        + '<td><b>' + (summary.changed || 0) + '</b> components</td></tr>'
        + '<tr class="text-danger"><td><i class="fa fa-ban"></i> Blocked by Dependencies:</td>'
        + '<td><b>' + (summary.blocked || 0) + '</b> components</td></tr>'
        + '</table></div>'
        + changed_html
        + blocked_html
        + '<hr>'
        + '<div class="alert alert-info">'
        + '<h6><i class="fa fa-lightbulb-o"></i> Next Steps:</h6>'
        + '<ol style="margin:10px 0 0 20px">'
        + '<li>Review changed components above</li>'
        + '<li>Deactivate old BOMs in BOM List</li>'
        + '<li>Re-run "Create BOMs with Validation" to complete upload</li>'
        + '</ol></div>'
        + '</div>';

    let d = new frappe.ui.Dialog({
        title: __('BOM Changes Detected - Resolution Required'),
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'analysis_html',
                options: html
            }
        ],
        size: 'large',
        primary_action_label: __('Open BOM List'),
        primary_action: function() {
            let item_codes = changed_components.map(function(c) {
                return c.node ? c.node.item_code : '';
            }).filter(function(c) { return c; });

            frappe.set_route('List', 'BOM', {
                'item': ['in', item_codes],
                'is_active': 1
            });
            d.hide();
        }
    });

    d.show();
}

function _show_upload_success(result) {
    let errors_html = '';
    if (result.errors && result.errors.length > 0) {
        errors_html = '<hr><h6 class="text-danger"><i class="fa fa-exclamation-triangle"></i> Errors:</h6>'
            + '<ul>' + result.errors.map(function(e) { return '<li>' + e + '</li>'; }).join('') + '</ul>';
    }

    // Extract summary data (supports both old and new format)
    let summary = result.summary || {};
    let items = summary.items || {};
    let boms = summary.boms || {};
    let cms = summary.component_masters || {};

    // Build comprehensive summary table
    let html = '<div class="alert alert-success">'
        + '<h5><i class="fa fa-check-circle"></i> BOM Upload Complete</h5>';

    // User-friendly message if provided
    if (result.message) {
        html += '<p class="text-muted" style="margin:10px 0">' + result.message + '</p>';
    }

    html += '<div class="row" style="margin-top:15px">';

    // Items column
    if (items.total > 0) {
        html += '<div class="col-md-4">'
            + '<h6><i class="fa fa-shopping-cart"></i> Items</h6>'
            + '<table class="table table-sm table-bordered">'
            + '<tr class="table-success"><td>Created</td><td><b>' + (items.created || 0) + '</b></td></tr>'
            + '<tr class="table-secondary"><td>Already Existed</td><td><b>' + (items.existing || 0) + '</b></td></tr>';
        if (items.updated > 0) {
            html += '<tr class="table-warning"><td>Updated</td><td><b>' + items.updated + '</b></td></tr>';
        }
        if (items.failed > 0) {
            html += '<tr class="table-danger"><td>Failed</td><td><b>' + items.failed + '</b></td></tr>';
        }
        html += '<tr class="table-info"><td><b>Total</b></td><td><b>' + (items.total || 0) + '</b></td></tr>'
            + '</table></div>';
    }

    // BOMs column
    if (boms.total > 0) {
        html += '<div class="col-md-4">'
            + '<h6><i class="fa fa-sitemap"></i> BOMs</h6>'
            + '<table class="table table-sm table-bordered">'
            + '<tr class="table-success"><td>Created</td><td><b>' + (boms.created || 0) + '</b></td></tr>'
            + '<tr class="table-secondary"><td>Already Existed</td><td><b>' + (boms.existing || 0) + '</b></td></tr>';
        if (boms.failed > 0) {
            html += '<tr class="table-danger"><td>Failed</td><td><b>' + boms.failed + '</b></td></tr>';
        }
        html += '<tr class="table-info"><td><b>Total</b></td><td><b>' + (boms.total || 0) + '</b></td></tr>'
            + '</table></div>';
    }

    // Component Masters column
    if (cms.total > 0) {
        html += '<div class="col-md-4">'
            + '<h6><i class="fa fa-cube"></i> Component Masters</h6>'
            + '<table class="table table-sm table-bordered">'
            + '<tr class="table-success"><td>Created</td><td><b>' + (cms.created || 0) + '</b></td></tr>'
            + '<tr class="table-secondary"><td>Already Existed</td><td><b>' + (cms.existing || 0) + '</b></td></tr>';
        if (cms.updated > 0) {
            html += '<tr class="table-warning"><td>Updated</td><td><b>' + cms.updated + '</b></td></tr>';
        }
        if (cms.failed > 0) {
            html += '<tr class="table-danger"><td>Failed</td><td><b>' + cms.failed + '</b></td></tr>';
        }
        html += '<tr class="table-info"><td><b>Total</b></td><td><b>' + (cms.total || 0) + '</b></td></tr>'
            + '</table></div>';
    }

    html += '</div>'; // Close row

    // Show impacted parent BOMs (only if version change occurred)
    let impacted = result.impacted_parent_boms || [];
    if (impacted.length > 0) {
        html += '<hr><div class="alert alert-warning" style="margin-top:15px">'
            + '<h6><i class="fa fa-exclamation-triangle"></i> Impacted Parent BOMs</h6>'
            + '<p class="text-muted" style="font-size:12px">These parent BOMs still reference the old child BOM version. '
            + 'Review if parent BOM update is needed.</p>'
            + '<table class="table table-sm table-bordered">'
            + '<thead><tr><th>Changed Item</th><th>Old BOM</th><th>Parent Item</th><th>Parent BOM</th></tr></thead>'
            + '<tbody>';

        impacted.forEach(function(row) {
            html += '<tr>'
                + '<td>' + row.changed_item + '</td>'
                + '<td><a href="/app/bom/' + row.old_bom + '">' + row.old_bom + '</a></td>'
                + '<td>' + row.parent_item + '</td>'
                + '<td><a href="/app/bom/' + row.parent_bom + '">' + row.parent_bom + '</a></td>'
                + '</tr>';
        });

        html += '</tbody></table></div>';
    }

    html += errors_html + '</div>';

    frappe.msgprint({
        title: __('Success'),
        message: html,
        indicator: 'green',
        wide: true
    });
}


// ==================== Phase 4E: Tiered Blocking Dialogs ====================

function _show_procurement_block_dialog(result, frm) {
    // Hard block - MR/RFQ exists, user must deactivate old BOM manually
    let blocked = result.blocked_components || [];

    let docs_html = '';
    blocked.forEach(function(comp) {
        let details = comp.details || {};
        let procurement_docs = details.procurement_docs || [];

        docs_html += '<div class="card mb-3" style="border-left:3px solid #dc3545;padding:10px;margin-bottom:10px">'
            + '<h6><i class="fa fa-ban text-danger"></i> ' + comp.item_code + '</h6>'
            + '<p class="text-muted">' + (details.blocking_message || 'Has active procurement') + '</p>';

        if (procurement_docs.length > 0) {
            docs_html += '<table class="table table-sm table-bordered">'
                + '<thead><tr><th>Document</th><th>Item</th><th>Qty</th><th>Status</th></tr></thead>'
                + '<tbody>';
            procurement_docs.forEach(function(doc) {
                docs_html += '<tr>'
                    + '<td><a href="/app/' + frappe.router.slug(doc.doctype) + '/' + doc.name + '">'
                    + doc.doctype + ': ' + doc.name + '</a></td>'
                    + '<td>' + (doc.item_code || '-') + '</td>'
                    + '<td>' + (doc.quantity || '-') + '</td>'
                    + '<td>' + (doc.status || '-') + '</td>'
                    + '</tr>';
            });
            docs_html += '</tbody></table>';
        }

        docs_html += '</div>';
    });

    let html = '<div class="bom-procurement-block">'
        + '<div class="alert alert-danger">'
        + '<h5><i class="fa fa-lock"></i> BOM Change Blocked</h5>'
        + '<p>Cannot change BOM structure because child items have active Material Requests or RFQs.</p>'
        + '</div>'
        + docs_html
        + '<hr>'
        + '<div class="alert alert-info">'
        + '<h6><i class="fa fa-lightbulb-o"></i> To Proceed:</h6>'
        + '<ol style="margin:10px 0 0 20px">'
        + '<li>Go to BOM List</li>'
        + '<li>Deactivate the old BOM(s) listed above</li>'
        + '<li>Re-run "Create BOMs with Validation"</li>'
        + '</ol></div>'
        + '</div>';

    let d = new frappe.ui.Dialog({
        title: __('BOM Change Blocked - Active Procurement'),
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'block_html',
                options: html
            }
        ],
        size: 'large',
        primary_action_label: __('Open BOM List'),
        primary_action: function() {
            let item_codes = blocked.map(function(c) { return c.item_code; });
            frappe.set_route('List', 'BOM', {
                'item': ['in', item_codes],
                'is_active': 1
            });
            d.hide();
        }
    });

    d.show();
}


function _show_manager_required_dialog(result) {
    // PO exists but user lacks manager role
    let blocked = result.blocked_components || [];

    let docs_html = '';
    blocked.forEach(function(comp) {
        let details = comp.details || {};
        let procurement_docs = details.procurement_docs || [];

        // Filter to only show POs
        let pos = procurement_docs.filter(function(d) {
            return d.doctype === 'Purchase Order';
        });

        docs_html += '<div class="card mb-3" style="border-left:3px solid #dc3545;padding:10px;margin-bottom:10px">'
            + '<h6><i class="fa fa-ban text-danger"></i> ' + comp.item_code + '</h6>';

        if (pos.length > 0) {
            docs_html += '<p><b>Active Purchase Orders:</b></p>'
                + '<ul>';
            pos.forEach(function(doc) {
                docs_html += '<li><a href="/app/purchase-order/' + doc.name + '">'
                    + doc.name + '</a> - ' + (doc.item_code || '') + ' (Qty: ' + (doc.quantity || 0) + ')</li>';
            });
            docs_html += '</ul>';
        }

        docs_html += '</div>';
    });

    let html = '<div class="bom-manager-required">'
        + '<div class="alert alert-danger">'
        + '<h5><i class="fa fa-user-times"></i> Manager Role Required</h5>'
        + '<p>Cannot change BOM structure because child items have active <b>Purchase Orders</b>.</p>'
        + '<p>Only users with <b>Component Master Manager</b> or <b>System Manager</b> role can override this.</p>'
        + '</div>'
        + docs_html
        + '<hr>'
        + '<div class="alert alert-warning">'
        + '<h6><i class="fa fa-info-circle"></i> Options:</h6>'
        + '<ol style="margin:10px 0 0 20px">'
        + '<li>Contact a manager to perform the upload</li>'
        + '<li>Or manually deactivate the old BOM(s), then re-run upload</li>'
        + '</ol></div>'
        + '</div>';

    frappe.msgprint({
        title: __('Manager Role Required'),
        message: html,
        indicator: 'red'
    });
}


function _show_confirmation_dialog(result, frm) {
    // No hard block - just need confirmation with remarks
    let confirmable = result.confirmable_components || [];

    // Build fields for each component requiring confirmation
    let fields = [
        {
            fieldtype: 'HTML',
            fieldname: 'intro_html',
            options: '<div class="alert alert-warning">'
                + '<h5><i class="fa fa-exclamation-triangle"></i> BOM Structure Changed</h5>'
                + '<p>The following components have changed BOM structure. '
                + 'Enter remarks to confirm each change.</p></div>'
        }
    ];

    confirmable.forEach(function(comp, idx) {
        let details = comp.details || {};
        let has_po = details.blocking_level === 'manager_required';

        let section_html = '<div class="card mb-3" style="border-left:3px solid '
            + (has_po ? '#dc3545' : '#ffa00a') + ';padding:10px;margin-bottom:10px">'
            + '<h6>[' + (idx + 1) + '/' + confirmable.length + '] ' + comp.item_code + '</h6>'
            + '<p><b>Old BOM:</b> '
            + (details.old_bom
                ? '<a href="/app/bom/' + details.old_bom + '">' + details.old_bom + '</a>'
                : 'None')
            + '</p>';

        // Show BOM diff (what changed)
        let bom_diff = details.bom_diff || {};
        let has_changes = (bom_diff.added && bom_diff.added.length > 0)
            || (bom_diff.removed && bom_diff.removed.length > 0)
            || (bom_diff.qty_changed && bom_diff.qty_changed.length > 0);

        if (has_changes) {
            section_html += '<div style="background:#f8f9fa;padding:8px;border-radius:4px;margin:8px 0">'
                + '<b style="font-size:12px">Changes:</b>';

            if (bom_diff.added && bom_diff.added.length > 0) {
                section_html += '<div style="color:#28a745;font-size:11px;margin-top:4px">'
                    + '<b>+ Added:</b> ';
                section_html += bom_diff.added.map(function(i) {
                    return i.item_code + ' (qty: ' + i.qty + ')';
                }).join(', ');
                section_html += '</div>';
            }

            if (bom_diff.removed && bom_diff.removed.length > 0) {
                section_html += '<div style="color:#dc3545;font-size:11px;margin-top:4px">'
                    + '<b>- Removed:</b> ';
                section_html += bom_diff.removed.map(function(i) {
                    return i.item_code + ' (was qty: ' + i.qty + ')';
                }).join(', ');
                section_html += '</div>';
            }

            if (bom_diff.qty_changed && bom_diff.qty_changed.length > 0) {
                section_html += '<div style="color:#ffc107;font-size:11px;margin-top:4px">'
                    + '<b>~ Qty Changed:</b> ';
                section_html += bom_diff.qty_changed.map(function(i) {
                    return i.item_code + ' (' + i.old_qty + ' → ' + i.new_qty + ')';
                }).join(', ');
                section_html += '</div>';
            }

            section_html += '</div>';
        }

        if (has_po) {
            section_html += '<p class="text-danger"><i class="fa fa-warning"></i> '
                + '<b>Warning:</b> Child items have active Purchase Orders!</p>';
        }

        // Show procurement docs if any
        let procurement_docs = details.procurement_docs || [];
        if (procurement_docs.length > 0) {
            section_html += '<details><summary>View Procurement Documents (' + procurement_docs.length + ')</summary>'
                + '<table class="table table-sm table-bordered" style="margin-top:5px">'
                + '<thead><tr><th>Document</th><th>Item</th><th>Qty</th></tr></thead>'
                + '<tbody>';
            procurement_docs.forEach(function(doc) {
                section_html += '<tr>'
                    + '<td>' + doc.doctype + ': ' + doc.name + '</td>'
                    + '<td>' + (doc.item_code || '-') + '</td>'
                    + '<td>' + (doc.quantity || '-') + '</td>'
                    + '</tr>';
            });
            section_html += '</tbody></table></details>';
        }

        section_html += '</div>';

        fields.push({
            fieldtype: 'HTML',
            fieldname: 'comp_html_' + idx,
            options: section_html
        });

        fields.push({
            fieldtype: 'Small Text',
            fieldname: 'remarks_' + comp.item_code.replace(/[^a-zA-Z0-9]/g, '_'),
            label: 'Remarks for ' + comp.item_code,
            reqd: 1,
            description: 'Explain why this BOM change is being made'
        });
    });

    let d = new frappe.ui.Dialog({
        title: __('Confirm BOM Version Changes'),
        fields: fields,
        size: 'large',
        primary_action_label: __('Confirm & Proceed'),
        primary_action: function() {
            // Collect confirmations
            let confirmations = [];
            let all_valid = true;

            confirmable.forEach(function(comp) {
                let field_name = 'remarks_' + comp.item_code.replace(/[^a-zA-Z0-9]/g, '_');
                let remarks = d.get_value(field_name);

                if (!remarks || remarks.trim() === '') {
                    frappe.msgprint({
                        title: __('Missing Remarks'),
                        message: __('Please enter remarks for ' + comp.item_code),
                        indicator: 'red'
                    });
                    all_valid = false;
                    return;
                }

                confirmations.push({
                    item_code: comp.item_code,
                    remarks: remarks.trim()
                });
            });

            if (!all_valid) {
                return;
            }

            d.hide();

            // Call server to proceed with confirmation
            frappe.call({
                method: 'clevertech.clevertech.doctype.bom_upload.bom_upload_enhanced.confirm_version_change',
                args: {
                    docname: frm.doc.name,
                    confirmations: JSON.stringify(confirmations)
                },
                freeze: true,
                freeze_message: __('Processing confirmed changes...'),
                callback: function(r) {
                    if (r.message) {
                        _show_upload_success(r.message);
                        frm.reload_doc();
                    }
                },
                error: function() {
                    frappe.msgprint({
                        title: __('Error'),
                        message: __('Failed to process confirmations. Check error log.'),
                        indicator: 'red'
                    });
                }
            });
        }
    });

    d.show();
}


// ==================== Debug: bom_qty_required ====================

function _run_debug_bom_qty_recalc(frm) {
    if (!frm.doc.project) {
        frappe.msgprint("Please select a Project first.");
        return;
    }

    frappe.call({
        method: 'clevertech.clevertech.doctype.bom_upload.bom_upload_enhanced.debug_upload_flow',
        args: { docname: frm.doc.name },
        freeze: true,
        freeze_message: __('Running debug...'),
        callback: function(r) {
            if (!r.message || !r.message.length) {
                frappe.msgprint("No log returned.");
                return;
            }
            _show_debug_flow_dialog(r.message);
        }
    });
}

function _show_debug_flow_dialog(log) {
    // Color map per stage
    let stage_colors = {
        'setup':  '#6c757d',
        'parse':  '#007bff',
        'cm':     '#28a745',
        'bom':    '#fd7e14',
        'hash':   '#17a2b8',
        'usage':  '#6f42c1',
        'recalc': '#dc3545'
    };
    let stage_labels = {
        'setup':  'Setup',
        'parse':  'Parse Excel',
        'cm':     'Component Masters',
        'bom':    'BOMs',
        'hash':   'Hash Comparison',
        'usage':  'BOM Usage',
        'recalc': 'Recalculation'
    };

    let html = '<div style="font-family:monospace;font-size:12px;max-height:600px;overflow-y:auto;padding:10px">';

    let current_stage = null;
    log.forEach(function(entry) {
        // Section header when stage changes
        if (entry.stage !== current_stage) {
            current_stage = entry.stage;
            let color = stage_colors[entry.stage] || '#333';
            html += '<div style="margin-top:14px;margin-bottom:4px;padding:4px 10px;'
                + 'background:' + color + ';color:#fff;border-radius:3px;font-weight:bold;font-size:13px">'
                + (stage_labels[entry.stage] || entry.stage) + '</div>';
        }

        // Highlight keywords
        let msg = entry.message
            .replace(/PARENT LOOKUP FAILED/g, '<span style="color:#dc3545;font-weight:bold">⚠ PARENT LOOKUP FAILED</span>')
            .replace(/NOT FOUND/g, '<span style="color:#dc3545;font-weight:bold">NOT FOUND</span>')
            .replace(/RESULT:/g, '<span style="color:#dc3545;font-weight:bold">→ RESULT:</span>')
            .replace(/EXISTS/g, '<span style="color:#28a745;font-weight:bold">EXISTS</span>')
            .replace(/EMPTY/g, '<span style="color:#ffc107;font-weight:bold">EMPTY</span>')
            .replace(/is Buy/g, '<span style="color:#ffc107">is Buy</span>')
            .replace(/HASH MATCH/g, '<span style="color:#28a745;font-weight:bold">HASH MATCH</span>')
            .replace(/HASH MISMATCH/g, '<span style="color:#dc3545;font-weight:bold">HASH MISMATCH</span>');

        html += '<div style="padding:2px 0;white-space:pre-wrap">' + msg + '</div>';
    });

    html += '</div>';

    let d = new frappe.ui.Dialog({
        title: __('Debug: Upload Flow Trace'),
        fields: [{
            fieldtype: 'HTML',
            fieldname: 'flow_html',
            options: html
        }],
        size: 'extra-large'
    });
    d.show();
}


// ==================== Debug Functions ====================

function _show_debug_results(result) {
    // Build HTML for occurrences by parent
    let parents_html = '';

    if (result.occurrences_by_parent && result.occurrences_by_parent.length > 0) {
        result.occurrences_by_parent.forEach(function(parent_data) {
            parents_html += '<div class="card mb-3" style="border-left:3px solid #007bff;padding:15px;margin-bottom:15px">';
            parents_html += '<h6><i class="fa fa-cube"></i> Parent: ' + parent_data.parent_item + '</h6>';
            parents_html += '<p class="text-muted" style="margin:5px 0">' + parent_data.parent_description + '</p>';
            parents_html += '<p style="margin:5px 0"><b>Level:</b> ' + parent_data.parent_level +
                          ' | <b>Occurrences:</b> ' + parent_data.occurrences.length +
                          ' | <b>Total Qty:</b> ' + parent_data.total_qty + '</p>';

            // Show each occurrence
            if (parent_data.occurrences.length > 0) {
                parents_html += '<table class="table table-sm table-bordered" style="margin-top:10px">';
                parents_html += '<thead><tr><th>#</th><th>Row</th><th>Position</th><th>Qty</th><th>Level</th><th>Hierarchy</th></tr></thead>';
                parents_html += '<tbody>';

                parent_data.occurrences.forEach(function(occ, idx) {
                    parents_html += '<tr>';
                    parents_html += '<td>' + (idx + 1) + '</td>';
                    parents_html += '<td>' + occ.row + '</td>';
                    parents_html += '<td>' + occ.position + '</td>';
                    parents_html += '<td><b>' + occ.qty + '</b></td>';
                    parents_html += '<td>' + occ.level + '</td>';
                    parents_html += '<td><small>' + occ.parent_chain + '</small></td>';
                    parents_html += '</tr>';
                });

                parents_html += '</tbody></table>';
            }

            // Warning if multiple BOM items would be created
            if (parent_data.bom_items_count > 1) {
                parents_html += '<div class="alert alert-warning" style="margin-top:10px">';
                parents_html += '<i class="fa fa-exclamation-triangle"></i> <b>Important:</b> ';
                parents_html += 'This will create <b>' + parent_data.bom_items_count + ' separate BOM item entries</b> ';
                parents_html += 'for ' + result.target_item + ' in this parent\'s BOM.';
                parents_html += '<br><small>Frappe may or may not consolidate these in the BOM UI - check the actual BOM to verify final quantity.</small>';
                parents_html += '</div>';
            }

            parents_html += '</div>';
        });
    }

    // Build main dialog HTML
    let html = '<div class="bom-debug-results">';
    html += '<div class="alert alert-info">';
    html += '<h5><i class="fa fa-bug"></i> BOM Quantity Debug Report</h5>';
    html += '<p><b>Target Item:</b> <code>' + result.target_item + '</code></p>';
    html += '<div class="row" style="margin-top:10px">';
    html += '<div class="col-md-4"><b>Excel Occurrences:</b> ' + result.excel_occurrences + '</div>';
    html += '<div class="col-md-4"><b>Excel Total Qty:</b> ' + result.excel_total_qty + '</div>';
    html += '<div class="col-md-4"><b>Parent Assemblies:</b> ' + result.parents_count + '</div>';
    html += '</div></div>';

    html += '<h6 style="margin-top:20px"><i class="fa fa-sitemap"></i> Occurrences by Parent Assembly:</h6>';
    html += parents_html;

    html += '<hr>';
    html += '<details><summary><b>Technical Analysis</b></summary>';
    html += '<pre style="background:#f5f5f5;padding:15px;margin-top:10px;font-size:11px;max-height:400px;overflow-y:auto">';
    html += result.tree_analysis;
    html += '</pre></details>';
    html += '</div>';

    let d = new frappe.ui.Dialog({
        title: __('BOM Quantity Debug - ' + result.target_item),
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'debug_html',
                options: html
            }
        ],
        size: 'extra-large'
    });

    d.show();
}
