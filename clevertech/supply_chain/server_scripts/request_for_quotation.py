import frappe

def validate(doc, method):
    # ── Duplicate MR-item check ──────────────────────────────────────────────
    seen = {}
    duplicates = []
    for row in doc.items:
        if not row.material_request_item:
            continue
        key = row.material_request_item
        if key in seen:
            duplicates.append(
                f"Row {row.idx}: <b>{row.item_code}</b> (MR {row.material_request}) — duplicate of row {seen[key]}"
            )
        else:
            seen[key] = row.idx
    if duplicates:
        frappe.throw(
            "Duplicate items found in RFQ. Remove the duplicates before saving:<br><br>"
            + "<br>".join(duplicates)
        )

    # Collect all Material Requests linked in RFQ Items
    mr_list = list({d.material_request for d in doc.items if d.material_request})
    if not mr_list:
        return
    # Build map keyed by MR item row ID
    mr_items = frappe.get_all(
        "Material Request Item",
        filters={"parent": ("in", mr_list)},
        fields=["name", "item_code", "qty", "parent"]
    )
    mr_item_map = {i.name: i for i in mr_items}
    # Validate each RFQ row against its linked MR row
    for row in doc.items:
        if not row.material_request:
            frappe.throw(
                f"Extra item found in Request for Quotation. "
                f"Item {row.item_code} does not belong to any selected Material Request."
            )
        if not row.material_request_item or row.material_request_item not in mr_item_map:
            frappe.throw(
                f"Item {row.item_code} (row {row.idx}) is not linked to a valid "
                f"Material Request {row.material_request} row."
            )
        mr_row = mr_item_map[row.material_request_item]
        if float(row.qty or 0) > float(mr_row.qty or 0):
            frappe.throw(
                f"Quantity mismatch for item {row.item_code} (row {row.idx}). "
                f"Material Request {row.material_request} allows {mr_row.qty} "
                f"but RFQ has {row.qty}."
            )
    # Check if RFQ is missing any MR items
#    rfq_keys = {f"{row.material_request}_{row.item_code}" for row in doc.items}
#    missing_items = set(mr_map.keys()) - rfq_keys
#    if missing_items:
#        missing_list = ", ".join(missing_items)
#        frappe.throw(
#            f"The following Material Request items are missing in the RFQ: {missing_list}"
#        )
