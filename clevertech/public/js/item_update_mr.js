// ============================================================
// Material Request – Client Script (with debug)
// ============================================================

frappe.ui.form.on('Material Request', {

    material_request_type(frm) {
        apply_purchase_warehouse_logic(frm);
    },

    refresh(frm) {
        apply_purchase_warehouse_logic(frm);
    },

    before_save(frm) {
        apply_purchase_warehouse_logic(frm);
    }

});

frappe.ui.form.on('Material Request Item', {

    items_add(frm, cdt, cdn) {
        setTimeout(() => apply_purchase_warehouse_logic(frm), 500);
    },

    item_code(frm, cdt, cdn) {
        apply_single_row_logic(frm, cdt, cdn);
    }

});

// ============================================================
// All Rows Logic
// ============================================================
function apply_purchase_warehouse_logic(frm) {

    if (frm.doc.material_request_type !== 'Purchase') return;
    if (!frm.doc.items || !frm.doc.items.length) return;

    console.log("=== apply_purchase_warehouse_logic called ===");
    console.log("Company:", frm.doc.company);

    let item_codes = [...new Set(frm.doc.items.map(r => r.item_code).filter(Boolean))];
    if (!item_codes.length) return;

    let promises = item_codes.map(item_code =>
        frappe.call({
            method: 'frappe.client.get',
            args: { doctype: 'Item', name: item_code }
        })
    );

    Promise.all(promises).then(results => {

        let item_warehouse_map = {};

        results.forEach(r => {
            if (!r.message) return;
            let item = r.message;
            let default_warehouse = null;

            console.log(`--- Item: ${item.name} ---`);
            console.log("item_defaults:", JSON.stringify(item.item_defaults));

            if (item.item_defaults && item.item_defaults.length) {
                item.item_defaults.forEach(def => {
                    console.log(
                        `  def.company="${def.company}" | frm.company="${frm.doc.company}" | match=${def.company === frm.doc.company} | def.default_warehouse="${def.default_warehouse}"`
                    );
                    if (def.company === frm.doc.company && def.default_warehouse) {
                        default_warehouse = def.default_warehouse;
                    }
                });
            }

            console.log(`  → Resolved warehouse for ${item.name}: "${default_warehouse}"`);
            item_warehouse_map[item.name] = default_warehouse;
        });

        frm.doc.items.forEach(row => {
            if (!row.item_code) return;
            let default_warehouse = item_warehouse_map[row.item_code];

            console.log(`Row item_code=${row.item_code} → setting warehouse to: "${default_warehouse || 'Material Staging - CT'}"`);

            if (default_warehouse) {
                frappe.model.set_value(row.doctype, row.name, 'warehouse', default_warehouse);
            } else {
                frappe.model.set_value(row.doctype, row.name, 'warehouse', 'Material Staging - CT');
            }
        });

        frm.refresh_field('items');
    });
}

// ============================================================
// Single Row Logic
// ============================================================
function apply_single_row_logic(frm, cdt, cdn) {

    if (frm.doc.material_request_type !== 'Purchase') return;

    let row = frappe.get_doc(cdt, cdn);
    if (!row.item_code) return;

    console.log("=== apply_single_row_logic called ===");
    console.log("item_code:", row.item_code, "| company:", frm.doc.company);

    frappe.call({
        method: 'frappe.client.get',
        args: { doctype: 'Item', name: row.item_code },
        callback(r) {
            if (!r.message) return;
            let item = r.message;
            let default_warehouse = null;

            console.log("item_defaults:", JSON.stringify(item.item_defaults));

            if (item.item_defaults && item.item_defaults.length) {
                item.item_defaults.forEach(def => {
                    console.log(
                        `  def.company="${def.company}" | frm.company="${frm.doc.company}" | match=${def.company === frm.doc.company} | def.default_warehouse="${def.default_warehouse}"`
                    );
                    if (def.company === frm.doc.company && def.default_warehouse) {
                        default_warehouse = def.default_warehouse;
                    }
                });
            }

            console.log(`→ Setting warehouse to: "${default_warehouse || 'Material Staging - CT'}"`);

            if (default_warehouse) {
                frappe.model.set_value(cdt, cdn, 'warehouse', default_warehouse);
            } else {
                frappe.model.set_value(cdt, cdn, 'warehouse', 'Material Staging - CT');
            }

            frm.refresh_field('items');
        }
    });
}



