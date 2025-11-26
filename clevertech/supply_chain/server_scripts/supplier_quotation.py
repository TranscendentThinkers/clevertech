import frappe

def validate(doc, method):

    # Collect all Material Requests linked in RFQ Items
    mr_list = list({d.request_for_quotation for d in doc.items if d.request_for_quotation})


    if not mr_list:
        return
    

    # Get all MR items
    mr_items = frappe.get_all(
        "Request for Quotation Item",
        filters={"parent": ("in", mr_list)},
        fields=["item_code", "qty", "parent"]
    )

    # Convert items to map for comparison
    mr_map = {}
    for i in mr_items:
        key = f"{i.parent}_{i.item_code}"
        mr_map[key] = i.qty
    frappe.log_error("Data",{"MR List":mr_list,"MR Items":mr_items,"MR Map":mr_map})

    # Validate RFQ items
    for row in doc.items:

        # Check for extra items
        if not row.request_for_quotation:
            frappe.throw(
                f"Extra item found in Suppier  Quotation. "
                f"Item {row.item_code} does not belong to any selected Request For Quotation."
            )

        key = f"{row.request_for_quotation}_{row.item_code}"
        frappe.log_error("Key",key)

        # Check if item exists in MR
        if key not in mr_map:
            frappe.throw(
                f"Item {row.item_code} is not part of Request For Quotation {row.request_for_quotation}."
            )

        # Check quantity match
        mr_qty = float(mr_map[key] or 0)
        rfq_qty = float(row.qty or 0)

        if rfq_qty != mr_qty:
            frappe.throw(
                f"Quantity mismatch for item {row.item_code}. "
                f"Request For Quotation quantity is {mr_qty} but Supplier Quotation quantity is {rfq_qty}."
            )

    # Check if RFQ is missing any MR items
#    rfq_keys = {f"{row.request_for_quotation}_{row.item_code}" for row in doc.items}

#    missing_items = set(mr_map.keys()) - rfq_keys

#    if missing_items:
#        missing_list = ", ".join(missing_items)
#        frappe.throw(
#            f"The following Request For Quotation items are missing in the Supplier Quotation: {missing_list}"
#        )

