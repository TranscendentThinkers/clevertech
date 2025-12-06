import frappe

def before_validate(doc, method):
    # Fetch settings once
    settings = frappe.get_cached_doc("Quality Warehouse Settings")
    qc_accepted = settings.qc_accepted_warehouse
    default_store = settings.default_store_warehouse

    for row in doc.items:
        if not row.item_code:
            continue

        # Fetch only the required field
        requires_inspection = frappe.db.get_value(
            "Item",
            row.item_code,
            "inspection_required_before_purchase"
        )

        # Apply logic
        if requires_inspection:
            row.warehouse = qc_accepted
        else:
            row.warehouse = default_store
#    fetch_payment_terms(doc)

def fetch_payment_terms(doc):

    supplier_quotation_name = None

    # 1️⃣ Loop through PO Items and pick the first Supplier Quotation value
    for row in doc.items:
        if row.supplier_quotation:
            supplier_quotation_name = row.supplier_quotation
            break

    if not supplier_quotation_name:
        return  # No supplier quotation found, exit

    # 2️⃣ Fetch Supplier Quotation document
    sq = frappe.get_doc("Supplier Quotation", supplier_quotation_name)

    # 3️⃣ Set Payment Terms Template from Supplier Quotation
    if sq.custom_payment_terms_template:
        doc.payment_terms_template = sq.custom_payment_terms_template

    # 4️⃣ Copy child table data (custom_payment_schedule → payment_schedule)
    doc.payment_schedule.clear()

    for schedule in sq.custom_payment_schedule:
        doc.append("payment_schedule", {
            "payment_term": schedule.payment_term,
            "description": schedule.description,
            "due_date": schedule.due_date,
            "invoice_portion": schedule.invoice_portion,
            "payment_amount": schedule.payment_amount,
            "discount": schedule.discount
        })
