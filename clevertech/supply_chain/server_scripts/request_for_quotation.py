import frappe

def validate(doc, method):

    # Collect all Material Requests linked in RFQ Items
    mr_list = list({d.material_request for d in doc.items if d.material_request})

    if not mr_list:
        return

    # Get all MR items
    mr_items = frappe.get_all(
        "Material Request Item",
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
        if not row.material_request:
            frappe.throw(
                f"Extra item found in Request for Quotation. "
                f"Item {row.item_code} does not belong to any selected Material Request."
            )

        key = f"{row.material_request}_{row.item_code}"

        # Check if item exists in MR
        if key not in mr_map:
            frappe.throw(
                f"Item {row.item_code} is not part of Material Request {row.material_request}."
            )

        # Check quantity match
        mr_qty = float(mr_map[key] or 0)
        rfq_qty = float(row.qty or 0)

        if rfq_qty > mr_qty:
            frappe.throw(
                f"Quantity mismatch for item {row.item_code}. "
                f"Material Request quantity is {mr_qty} but RFQ quantity is {rfq_qty}."
            )

    # Check if RFQ is missing any MR items
#    rfq_keys = {f"{row.material_request}_{row.item_code}" for row in doc.items}

#    missing_items = set(mr_map.keys()) - rfq_keys

#    if missing_items:
#        missing_list = ", ".join(missing_items)
#        frappe.throw(
#            f"The following Material Request items are missing in the RFQ: {missing_list}"
#        )

