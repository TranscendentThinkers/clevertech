import frappe

def validate(doc, method):


    # Collect all Material Requests linked in RFQ Items
    mr_list = list({d.supplier_quotation for d in doc.items if d.supplier_quotation})

    if not mr_list:
        return

    # Get all MR items
    mr_items = frappe.get_all(
        "Supplier Quotation Item",
        filters={"parent": ("in", mr_list)},
        fields=["item_code", "qty", "parent"]
    )

    # Convert items to map for comparison
    mr_map = {}
    for i in mr_items:
        key = f"{i.parent}_{i.item_code}"
        mr_map[key] = i.qty

    # Validate RFQ items
    for row in doc.items:

        # Check for extra items
        if not row.supplier_quotation:
            frappe.throw(
                f"Extra item found in Purchase Order. "
                f"Item {row.item_code} does not belong to any selected Supplier Quotation."
            )

        key = f"{row.supplier_quotation}_{row.item_code}"

        # Check if item exists in MR
        if key not in mr_map:
            frappe.throw(
                f"Item {row.item_code} is not part of Supplier Quotation {row.supplier_quotation}."
            )

        # Check quantity match
        mr_qty = float(mr_map[key] or 0)
        rfq_qty = float(row.qty or 0)

        if rfq_qty != mr_qty:
            frappe.throw(
                f"Quantity mismatch for item {row.item_code}. "
                f"Supplier Quotation  quantity is {mr_qty} but PO quantity is {rfq_qty}."
            )

    # Check if RFQ is missing any MR items
#    rfq_keys = {f"{row.supplier_quotation}_{row.item_code}" for row in doc.items}

#    missing_items = set(mr_map.keys()) - rfq_keys

#    if missing_items:
#        missing_list = ", ".join(missing_items)
#        frappe.throw(
#            f"The following Supplier Quotation items are missing in the PO: {missing_list}"
#        )

