frappe.ui.form.on('Item', {
    item_code: function(frm) {
        set_default_values(frm);
    },
    onload: function(frm) {
        if (frm.doc.item_code) {
            set_default_values(frm);
        }
    }
});

function set_default_values(frm) {
    if (!frm.doc.item_code) return;

    var item_code = frm.doc.item_code.trim().toUpperCase();
    var warehouse = '';
    var inspection_flag = 0;

    // ✅ Condition for D and IM
    if (item_code.startsWith("D") || item_code.startsWith("IM")) {
        warehouse = 'Quality Pending - CT';
        inspection_flag = 1;
    } else {
        warehouse = 'Material Staging - CT';
        inspection_flag = 0;
    }

    // ✅ Set inspection_required_before_purchase field
    frm.set_value('inspection_required_before_purchase', inspection_flag);

    // ✅ Update item_defaults child table
    if (frm.doc.item_defaults && frm.doc.item_defaults.length > 0) {
        frm.doc.item_defaults.forEach(function(row) {
            frappe.model.set_value(row.doctype, row.name, 'default_warehouse', warehouse);
        });
    } else {
        var child = frm.add_child('item_defaults');
        frappe.model.set_value(child.doctype, child.name, 'default_warehouse', warehouse);
    }

    frm.refresh_field('item_defaults');
}
