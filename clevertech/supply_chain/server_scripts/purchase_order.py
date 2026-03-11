import frappe

def on_cancel(doc, method=None):
    """Cancel linked SQ Comparison and SQ docs before Frappe's back-link check runs.
    - SQC: custom doctype, PO link is in a child row — not discoverable by ERPNext Cancel All
    - SQ: has purchase_order on its items — Frappe blocks PO cancel if SQ is still submitted
    Both must be cancelled here (on_cancel fires before check_no_back_links_exist).
    """
    cancelled = []

    # Step 1: cancel SQ Comparisons linked to this PO
    sqc_names = frappe.db.sql("""
        SELECT DISTINCT parent
        FROM `tabSupplier Selection Item`
        WHERE purchase_order = %s
    """, doc.name, as_dict=True)

    for row in sqc_names:
        sqc = frappe.get_doc("Supplier Quotation Comparison", row.parent)
        if sqc.docstatus == 1:
            sqc.cancel()
            cancelled.append(f"Supplier Quotation Comparison: {sqc.name}")

    # Step 2: cancel Supplier Quotations linked to this PO via PO items
    sq_names = list({i.supplier_quotation for i in doc.items if i.get("supplier_quotation")})
    for sq_name in sq_names:
        sq = frappe.get_doc("Supplier Quotation", sq_name)
        if sq.docstatus == 1:
            sq.cancel()
            cancelled.append(f"Supplier Quotation: {sq.name}")

    if cancelled:
        frappe.msgprint(
            "The following linked documents were also cancelled:<br>" + "<br>".join(cancelled),
            title="Linked Documents Cancelled",
            alert=True
        )


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
        if rfq_qty > mr_qty:
            frappe.throw(
                f"Quantity mismatch for item {row.item_code}. "
                f"Supplier Quotation  quantity is {mr_qty} but PO quantity is {rfq_qty}."
            )
    if doc.payment_schedule:
        return  # don't override if already set
    sq_name = None
    for item in doc.items:
        if item.supplier_quotation:
            sq_name = item.supplier_quotation
            break
    if not sq_name:
        return
    sq = frappe.get_doc("Supplier Quotation", sq_name)
    # Set Payment Terms Template
    if sq.custom_payment_terms_template:
        doc.payment_terms_template = sq.custom_payment_terms_template
    # Copy Payment Schedule
    if sq.custom_payment_schedule:
        doc.payment_schedule = []
        for row in sq.custom_payment_schedule:
            doc.append("payment_schedule", {
                "payment_term": row.payment_term,
                "description": row.description,
                "due_date": row.due_date,
                "invoice_portion": row.invoice_portion,
                "payment_amount": row.payment_amount,
                "discount_type": row.discount_type,
                "discount": row.discount,
            })
    # Check if RFQ is missing any MR items
#    rfq_keys = {f"{row.supplier_quotation}_{row.item_code}" for row in doc.items}
#    missing_items = set(mr_map.keys()) - rfq_keys
#    if missing_items:
#        missing_list = ", ".join(missing_items)
#        frappe.throw(
#            f"The following Supplier Quotation items are missing in the PO: {missing_list}"
#        )
