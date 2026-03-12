import frappe
from frappe import _
from frappe.utils import strip_html_tags


def get_incoterm_title(code):
    """Fetch the title of an Incoterm given its code/name"""
    if not code:
        return ""
    return frappe.db.get_value("Incoterm", code, "title") or code


def execute(filters=None):
    if not filters or not filters.get("request_for_quotation"):
        return [], []

    rfq = filters["request_for_quotation"]
    rfq_doc = frappe.get_doc("Request for Quotation", rfq)

    # ── 1. Identify Suppliers ────────────────────────────────────────────────
    suppliers = []
    for row in rfq_doc.suppliers:
        sid = row.supplier
        display_name = frappe.db.get_value("Supplier", sid, "supplier_name") or sid
        suppliers.append({"id": sid, "name": display_name})

    # ── 2. Fetch Latest Quotations & Custom Terms ────────────────────────────
    all_sqs = frappe.get_all(
        "Supplier Quotation",
        filters={"request_for_quotation": rfq, "docstatus": ["!=", 2]},
        fields=[
            "name",
            "supplier",
            "custom_payment_terms_template",
            "custom_delivery_terms",
            "custom_note"
        ],
        order_by="`tabSupplier Quotation`.modified desc"
    )

    processed_sqs = {}
    supplier_metadata = {}
    for sq in all_sqs:
        if sq.supplier not in processed_sqs:
            processed_sqs[sq.supplier] = sq.name
            supplier_metadata[sq.supplier] = {
                "payment_terms": sq.custom_payment_terms_template or "-",
                "delivery_terms": get_incoterm_title(sq.custom_delivery_terms) or "-",
                "notes": strip_html_tags(sq.custom_note or "-")
            }

    # ── 3. Define Columns ────────────────────────────────────────────────────
    columns = [
        {"fieldname": "item_code",              "label": _("Item Code"),              "fieldtype": "Link", "options": "Item", "width": 150},
        {"fieldname": "material_request",       "label": _("Material Request"),       "fieldtype": "Data", "width": 130},
        {"fieldname": "description",            "label": _("Description"),            "fieldtype": "Data", "width": 200},
        {"fieldname": "qty",                    "label": _("Qty"),                    "fieldtype": "Float", "width": 80},
        {"fieldname": "uom",                    "label": _("UOM"),                    "fieldtype": "Data", "width": 70},
        {"fieldname": "last_purchase_rate",     "label": _("Last Purchase Rate"),     "fieldtype": "Currency", "width": 140},
        {"fieldname": "last_purchase_supplier", "label": _("Last Purchase Supplier"), "fieldtype": "Data", "width": 150},
    ]

    for s in suppliers:
        columns.append({
            "fieldname": f"rate_{s['id']}",
            "label": s["name"],
            "fieldtype": "Currency",
            "width": 220
        })

    # ── 4. Process RFQ Items ─────────────────────────────────────────────────
    # Key by rfq_item.name (row ID) — handles duplicate item codes from same MR
    items_data = {}
    item_order = []

    for rfq_item in rfq_doc.items:
        mr = rfq_item.get("material_request") or ""
        key = rfq_item.name  # unique row ID
        last = get_last_purchase_details(rfq_item.item_code)
        description = strip_html_tags(rfq_item.description or rfq_item.item_name or rfq_item.item_code)

        items_data[key] = {
            "item_code": rfq_item.item_code,
            "material_request": mr,
            "description": description,
            "qty": rfq_item.qty,
            "uom": rfq_item.uom or rfq_item.stock_uom or "",
            "last_purchase_rate": last.get("rate") or 0,
            "last_purchase_supplier": last.get("supplier") or "",
            "rates": {}
        }
        item_order.append(key)

    # ── 5. Fill Rates ────────────────────────────────────────────────────────
    for sid, sq_name in processed_sqs.items():
        sq_items = frappe.get_all(
            "Supplier Quotation Item",
            filters={"parent": sq_name},
            fields=["item_code", "request_for_quotation_item", "rate"]
        )
        for item in sq_items:
            key = item.get("request_for_quotation_item") or ""
            if key in items_data and item.rate > 0:
                items_data[key]["rates"][sid] = item.rate

    # ── 6. Build Item Rows ───────────────────────────────────────────────────
    data = []
    for key in item_order:
        item = items_data[key]
        row = {
            "item_code": item["item_code"],
            "material_request": item["material_request"],
            "description": item["description"],
            "qty": item["qty"],
            "uom": item["uom"],
            "last_purchase_rate": item["last_purchase_rate"],
            "last_purchase_supplier": item["last_purchase_supplier"],
        }
        for s in suppliers:
            row[f"rate_{s['id']}"] = item["rates"].get(s["id"])

        # Pass the lowest supplier id so JS uses Python's tiebreak logic
        rates = item["rates"]
        valid_rates = {sid: r for sid, r in rates.items() if r and r > 0}
        if valid_rates:
            min_rate = min(valid_rates.values())
            tied = [sid for sid, r in valid_rates.items() if r == min_rate]
            if len(tied) == 1:
                row["_lowest_supplier_id"] = tied[0]
            else:
                # Tiebreak by supplier grand total
                sq_grand_totals = {}
                for sq in all_sqs:
                    if sq.supplier not in sq_grand_totals:
                        sq_grand_totals[sq.supplier] = frappe.db.get_value(
                            "Supplier Quotation", processed_sqs[sq.supplier], "grand_total"
                        ) or 0
                row["_lowest_supplier_id"] = min(tied, key=lambda sid: sq_grand_totals.get(sid, 0))
        else:
            row["_lowest_supplier_id"] = None

        data.append(row)

    # ── 7. Build Footer Rows ─────────────────────────────────────────────────
    footer_config = [
        {"label": "Payment Terms",    "key": "payment_terms"},
        {"label": "Delivery Terms",   "key": "delivery_terms"},
        {"label": "Additional Notes", "key": "notes"}
    ]

    for f in footer_config:
        f_row = {
            "item_code": f"<strong>{_(f['label'])}</strong>",
            "material_request": "",
            "description": "",
            "qty": None,
            "uom": "",
            "last_purchase_rate": None,
            "last_purchase_supplier": "",
            "is_footer": 1
        }
        for s in suppliers:
            sid = s["id"]
            meta = supplier_metadata.get(sid, {})
            f_row[f"rate_{sid}"] = meta.get(f["key"]) or "-"
        data.append(f_row)

    return columns, data


def get_last_purchase_details(item_code):
    result = frappe.db.sql("""
        SELECT pii.rate, pi.supplier
        FROM `tabPurchase Invoice Item` pii
        INNER JOIN `tabPurchase Invoice` pi ON pii.parent = pi.name
        WHERE pii.item_code = %(item_code)s AND pi.docstatus = 1
        ORDER BY pi.posting_date DESC, pi.creation DESC
        LIMIT 1
    """, {"item_code": item_code}, as_dict=True)

    if result:
        supplier_name = frappe.db.get_value("Supplier", result[0].supplier, "supplier_name")
        return {"rate": result[0].rate, "supplier": supplier_name or result[0].supplier}
    return {"rate": None, "supplier": ""}
