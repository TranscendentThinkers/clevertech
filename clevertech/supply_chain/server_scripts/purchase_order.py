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

    active_sqc_wf = frappe.db.get_value(
        "Workflow", {"document_type": "Supplier Quotation Comparison", "is_active": 1}, "name"
    )
    for row in sqc_names:
        sqc = frappe.get_doc("Supplier Quotation Comparison", row.parent)
        if sqc.docstatus == 1:
            if active_sqc_wf:
                from frappe.model.workflow import apply_workflow
                sqc.flags.ignore_permissions = True
                apply_workflow(sqc, "Cancel")
            else:
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
    # Collect all SQs linked in PO Items
    sq_list = list({d.supplier_quotation for d in doc.items if d.supplier_quotation})
    if not sq_list:
        return
    # Build map keyed by SQ item row ID
    sq_items = frappe.get_all(
        "Supplier Quotation Item",
        filters={"parent": ("in", sq_list)},
        fields=["name", "item_code", "qty", "parent"]
    )
    sq_item_map = {i.name: i for i in sq_items}

    # Validate each PO row against its linked SQ row
    for row in doc.items:
        if not row.supplier_quotation:
            frappe.throw(
                f"Extra item found in Purchase Order. "
                f"Item {row.item_code} does not belong to any selected Supplier Quotation."
            )
        if not row.supplier_quotation_item or row.supplier_quotation_item not in sq_item_map:
            frappe.throw(
                f"Item {row.item_code} (row {row.idx}) is not linked to a valid "
                f"Supplier Quotation {row.supplier_quotation} row."
            )
        sq_row = sq_item_map[row.supplier_quotation_item]
        if float(row.qty or 0) > float(sq_row.qty or 0):
            frappe.throw(
                f"Quantity mismatch for item {row.item_code} (row {row.idx}). "
                f"Supplier Quotation {row.supplier_quotation} allows {sq_row.qty} "
                f"but PO has {row.qty}."
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
