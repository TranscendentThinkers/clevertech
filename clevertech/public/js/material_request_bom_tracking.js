/**
 * Material Request: Track BOM used for procurement
 * 
 * Populates custom_procurement_bom field when "Get Items from BOM" is used
 */

frappe.ui.form.on('Material Request', {
    refresh: function(frm) {
        // Override the default "Get Items from BOM" button behavior
        // This ensures we capture which BOM was used
    },
    
    // When items are fetched from BOM via the "Get Items from BOM" dialog
    // The BOM name is available in the args passed to get_items_from_bom
    custom_bom_id: function(frm) {
        // When custom_bom_id changes (used for material transfer),
        // don't populate custom_procurement_bom
        // (they serve different purposes)
    }
});

// Hook into the "Get Items from BOM" functionality
// This runs when user selects a BOM in the dialog
frappe.ui.form.on('Material Request', 'get_items_from_bom', {
    onload: function(frm) {
        // Override to capture BOM name
        const original_get_items = frm.trigger_link;
        
        frm.trigger_link = function() {
            const result = original_get_items.apply(this, arguments);
            
            // After items are fetched, store the BOM name
            if (result && result.bom) {
                frm.set_value('custom_procurement_bom', result.bom);
            }
            
            return result;
        };
    }
});

