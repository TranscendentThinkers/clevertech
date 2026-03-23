import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, add_days

def get_incoterm_title(code):
    """Fetch the title of an Incoterm given its code/name"""
    if not code:
        return ""
    return frappe.db.get_value("Incoterm", code, "title") or code


class SupplierQuotationComparison(Document):
    def validate(self):
        self.validate_request_for_quotations()

        # Set created_by on first save (when document is new)
        if self.is_new() and not self.created_by:
            self.created_by = frappe.session.user

        # Only populate items table on initial creation or when RFQ changes
        # Skip if supplier_selection_table already has data (workflow transition)
        if self.is_new() and self.request_for_quotation and not self.supplier_selection_table:
            self.populate_items_table()
            # fetch_file_references removed from validate — now called on every Fetch Report instead
            # self.fetch_file_references()
            self.fetch_rfq_fields()
        elif self.has_value_changed("request_for_quotation") and self.request_for_quotation:
            # Only repopulate if RFQ actually changed (not on workflow transitions)
            self.populate_items_table()
            # fetch_file_references removed from validate — now called on every Fetch Report instead
            # self.fetch_file_references()
            self.fetch_rfq_fields()

    def on_submit(self):
        """Auto-submit supplier quotations and create purchase orders on submit"""
        # Step 1: Auto-submit supplier quotations that are in draft
        self.auto_submit_supplier_quotations()

        # Step 2: Create purchase orders
        self.create_purchase_orders_on_submit()

    def before_submit(self):
        """Validate required fields before submit"""
        # Validate created_by is not empty
        if not self.created_by:
            frappe.throw(_("Created By is mandatory before submission. Please save the document first."))

        # Validate required_by_in_days is set — PO schedule_date is calculated at submit time
        # as today + required_by_in_days, so this field must be filled before submission
        if not self.required_by_in_days or self.required_by_in_days <= 0:
            frappe.throw(_("Required By (Days) is mandatory before submission. Please set the number of days."))

    def validate_request_for_quotations(self):
        rfq = self.request_for_quotation
        if not rfq:
            return

        # Check RFQ is submitted
        docstatus = frappe.db.get_value("Request for Quotation", rfq, "docstatus")
        if docstatus != 1:
            frappe.throw(_("Selected Request for Quotation is not submitted."))

        # Check no other SQC already exists for this RFQ (exclude current doc)
        existing_count = frappe.db.count(
            "Supplier Quotation Comparison",
            filters={
                "request_for_quotation": rfq,
                "name": ["!=", self.name]
            }
        )
        if existing_count > 0:
            frappe.throw(_("A Supplier Quotation Comparison already exists for this Request for Quotation."))

    def auto_submit_supplier_quotations(self):
        """Submit all supplier quotations in the selection table that are in draft status"""
        if not self.supplier_selection_table:
            return

        # Get unique supplier quotations from selection table
        supplier_quotations = set()
        for row in self.supplier_selection_table:
            if row.supplier_quotation:
                supplier_quotations.add(row.supplier_quotation)

        submitted_sqs = []
        already_submitted_sqs = []

        for sq_name in supplier_quotations:
            try:
                sq_doc = frappe.get_doc("Supplier Quotation", sq_name)

                # Only submit if it's in draft status (docstatus = 0)
                if sq_doc.docstatus == 0:
                    sq_doc.submit()
                    submitted_sqs.append(sq_name)
                    frappe.logger().info(f"Auto-submitted Supplier Quotation: {sq_name}")
                elif sq_doc.docstatus == 1:
                    already_submitted_sqs.append(sq_name)

            except Exception as e:
                frappe.logger().error(f"Error submitting Supplier Quotation {sq_name}: {str(e)}")
                frappe.throw(
                    _("Failed to submit Supplier Quotation {0}. Error: {1}").format(
                        sq_name, str(e)
                    )
                )

        # Show message about submitted quotations
        if submitted_sqs:
            frappe.msgprint(
                _("Auto-submitted {0} Supplier Quotation(s):<br>{1}").format(
                    len(submitted_sqs),
                    "<br>".join([frappe.bold(sq) for sq in submitted_sqs])
                ),
                indicator="blue",
                title=_("Supplier Quotations Submitted")
            )

    def create_purchase_orders_on_submit(self):
        """Create purchase orders on document submission"""
        if not self.supplier_selection_table:
            frappe.throw(_("No items in supplier selection table"))

        # Use project and cost_center from the comparison document
        project = self.get("project")
        cost_center = self.get("cost_center")

        # Mandatory validation for project and cost_center
        if not project:
            frappe.throw(_("Project is mandatory for creating Purchase Orders. Please set the Project field before submitting."))

        if not cost_center:
            frappe.throw(_("Cost Center is mandatory for creating Purchase Orders. Please set the Cost Center field before submitting."))

        # Calculate the PO schedule_date at submit time: today + required_by_in_days
        # required_by_in_days can be edited freely before submission
        required_by_in_days = self.get("required_by_in_days") or 0
        po_schedule_date = add_days(today(), int(required_by_in_days)) if required_by_in_days else today()

        # Validate that all items have a supplier selected (not NA / zero rate)
        items_missing_supplier = []
        for row in self.supplier_selection_table:
            if not row.item_code:
                continue
            if not row.supplier or not row.supplier_quotation or not row.rate:
                items_missing_supplier.append(row.item_code)

        if items_missing_supplier:
            frappe.throw(
                _("Cannot create Purchase Orders. The following items do not have a supplier selected "
                  "(possibly no supplier provided a valid quotation):<br><br>{0}").format(
                    "<br>".join([frappe.bold(item) for item in items_missing_supplier])
                )
            )

        # Check if POs are already created for all items
        items_with_po = []
        items_without_po = []

        for row in self.supplier_selection_table:
            if not row.supplier or not row.supplier_quotation or not row.item_code:
                continue

            if row.purchase_order:
                items_with_po.append(f"{row.item_code} (PO: {row.purchase_order})")
            else:
                items_without_po.append(row.item_code)

        # If all items have POs, just show info message
        if items_with_po and not items_without_po:
            frappe.msgprint(
                _("Purchase Orders have already been created for all items.<br><br>Items with POs:<br>{0}").format(
                    "<br>".join(items_with_po)
                ),
                indicator="blue",
                title=_("Purchase Orders Already Created")
            )
            return

        # If some items have POs, show warning
        if items_with_po:
            frappe.msgprint(
                _("Note: The following items already have Purchase Orders and will be skipped:<br><br>{0}").format(
                    "<br>".join(items_with_po)
                ),
                indicator="orange",
                title=_("Some Items Already Have POs")
            )

        supplier_quotation_map = {}

        for row in self.supplier_selection_table:
            if not row.supplier or not row.supplier_quotation or not row.item_code:
                continue

            # Skip items that already have PO created
            if row.purchase_order:
                continue

            sq_name = row.supplier_quotation

            if sq_name not in supplier_quotation_map:
                supplier_quotation_map[sq_name] = []

            supplier_quotation_map[sq_name].append({
                "item_code": row.item_code,
                "material_request": row.get("material_request") or "",
                "rfq_item_row": row.get("rfq_item_row") or "",
                "qty": row.qty or 0,
                "rate": row.rate or 0,
                "payment_terms_template": row.get("payment_terms_template"),
                "delivery_term": row.get("delivery_term"),
                "notes": row.get("notes") or ""
            })

        if not supplier_quotation_map:
            frappe.msgprint(
                _("No valid items with supplier quotations found for PO creation"),
                indicator="orange"
            )
            return

        created_pos = []

        for sq_name, items in supplier_quotation_map.items():
            # Pass po_schedule_date (calculated from today + required_by_in_days at submit time)
            po = create_po_from_supplier_quotation(sq_name, items, self, project, cost_center, po_schedule_date)
            if po:
                created_pos.append(po.name)
                # Update selection table with PO reference
                selected_rfq_item_rows = {item["rfq_item_row"] for item in items if item.get("rfq_item_row")}
                add_po_reference(self, po, selected_rfq_item_rows)

        # Save the document to persist PO references (using db_update to avoid re-triggering submit)
        for row in self.supplier_selection_table:
            if row.purchase_order:
                frappe.db.set_value(
                    "Supplier Selection Item",
                    row.name,
                    "purchase_order",
                    row.purchase_order,
                    update_modified=False
                )
        frappe.db.commit()

        # Show success message
        if created_pos:
            frappe.msgprint(
                _("Successfully created {0} Purchase Order(s):<br>{1}").format(
                    len(created_pos),
                    "<br>".join([f'<a href="/app/purchase-order/{po}" target="_blank">{po}</a>' for po in created_pos])
                ),
                indicator="green",
                title=_("Purchase Orders Created")
            )

    def fetch_file_references(self):
        """Fetch file references from supplier quotations without duplicating files"""
        # Clear existing references
        self.set("attached_files", [])

        if not self.request_for_quotation:
            return

        # Get all supplier quotations for this RFQ
        # distinct=True prevents duplicate rows caused by Frappe joining the SQ items child table
        # (which also has a request_for_quotation field) — without it, one row is returned per item
        supplier_quotations = frappe.get_all(
            "Supplier Quotation",
            filters={
                "request_for_quotation": self.request_for_quotation,
                "docstatus": ["!=", 2]  # Exclude cancelled; include draft (0) and submitted (1)
            },
            fields=["name", "supplier"],
            distinct=True,
            order_by="name desc"
        )

        # For each supplier quotation, get attached files
        for sq in supplier_quotations:
            files = frappe.get_all(
                "File",
                filters={
                    "attached_to_doctype": "Supplier Quotation",
                    "attached_to_name": sq.name
                },
                fields=["name", "file_name", "file_url"]
            )

            # Add each file as a reference
            for f in files:
                self.append("attached_files", {
                    "supplier": sq.supplier,
                    "supplier_quotation": sq.name,
                    "file": f.name,
                    "file_name": f.file_name,
                    "file_url": f.file_url
                })

    def fetch_rfq_fields(self):
        """Fetch project, cost_center, and required_by_in_days from RFQ"""
        if not self.request_for_quotation:
            return

        rfq_doc = frappe.get_doc("Request for Quotation", self.request_for_quotation)

        # Fetch project - try custom field first, then standard field
        project = rfq_doc.get("custom_project") or rfq_doc.get("project")
        if project:
            self.project = project

        # Fetch cost_center - try custom field first, then standard field
        cost_center = rfq_doc.get("custom_cost_center") or rfq_doc.get("cost_center")
        if cost_center:
            self.cost_center = cost_center

        # Fetch required_by_in_days from RFQ
        required_by_in_days = rfq_doc.get("custom_required_by_in_days")
        if required_by_in_days:
            self.required_by_in_days = required_by_in_days

        # required_by_date is intentionally NOT fetched here.
        # The PO schedule_date is calculated at submit time as: today() + required_by_in_days
        # This ensures the date reflects when the PO is actually created, not when the RFQ was raised.

    def populate_items_table(self):
        if not self.request_for_quotation:
            return

        rfq_doc = frappe.get_doc("Request for Quotation", self.request_for_quotation)
        self.supplier_selection_table = []

        # Populate the child table — store rfq_item_row (row name) for precise row-level matching
        for row in rfq_doc.items:
            self.append("supplier_selection_table", {
                "item_code": row.item_code,
                "material_request": row.get("material_request") or "",
                "rfq_item_row": row.name
            })


@frappe.whitelist()
def get_supplier_quotation(rfq, supplier, item_code=None, material_request=None, rfq_item_row=None):
    """
    Fetch the supplier quotation linked to the RFQ where supplier matches.
    If rfq_item_row is provided, match by RFQ item row ID (request_for_quotation_item) — precise.
    Falls back to item_code + material_request match if rfq_item_row is not set.
    """
    if not rfq or not supplier:
        return None

    try:
        supplier_quotations = frappe.get_all(
            "Supplier Quotation",
            filters={
                "request_for_quotation": rfq,
            },
            fields=["name", "supplier", "modified", "total"],  # pre-tax total for tiebreaking
            order_by="modified desc"
        )

        for sq in supplier_quotations:
            if sq.supplier == supplier:
                sq_name = sq.name

                if item_code:
                    try:
                        sq_doc = frappe.get_doc("Supplier Quotation", sq_name)

                        # Get delivery_term, payment_terms, and notes from supplier quotation
                        delivery_term = sq_doc.get("custom_delivery_terms") or ""
                        payment_terms_template = sq_doc.get("custom_payment_terms_template") or ""
                        notes = sq_doc.get("custom_note") or ""

                        # Match by rfq_item_row (precise) if provided, else fall back to item_code+MR
                        matched_item = None
                        for item in sq_doc.items:
                            if rfq_item_row:
                                if item.get("request_for_quotation_item") == rfq_item_row:
                                    matched_item = item
                                    break
                            elif item.item_code == item_code:
                                if material_request:
                                    item_mr = item.get("material_request") or ""
                                    if item_mr == material_request:
                                        matched_item = item
                                        break
                                else:
                                    matched_item = item
                                    break

                        if matched_item:
                            return {
                                "name": sq_name,
                                "rate": matched_item.rate,
                                "qty": matched_item.qty,
                                "amount": matched_item.amount,
                                "delivery_term": delivery_term,
                                "payment_terms_template": payment_terms_template,
                                "notes": notes
                            }

                        # Item not found in this quotation
                        return {
                            "name": sq_name,
                            "rate": 0,
                            "qty": 0,
                            "amount": 0,
                            "delivery_term": delivery_term,
                            "payment_terms_template": payment_terms_template,
                            "notes": notes
                        }
                    except Exception as e:
                        frappe.logger().error(f"Error fetching Supplier Quotation {sq_name}: {str(e)}")
                        return {
                            "name": sq_name,
                            "rate": 0,
                            "qty": 0,
                            "amount": 0,
                            "delivery_term": None,
                            "payment_terms_template": None,
                            "notes": ""
                        }
                else:
                    return sq_name

        return None

    except Exception as e:
        frappe.logger().error(f"Error in get_supplier_quotation: {str(e)}")
        return None


@frappe.whitelist()
def get_comparison_report_data(docname):
    sqc = frappe.get_doc("Supplier Quotation Comparison", docname)
    rfq = sqc.request_for_quotation
    if not rfq:
        frappe.throw("Please select Request for Quotation first")

    rfq_doc = frappe.get_doc("Request for Quotation", rfq)

    # Get all suppliers from RFQ
    all_rfq_suppliers = []
    supplier_names = {}
    supplier_grand_totals = {}

    for supplier_row in rfq_doc.suppliers:
        supplier_id = supplier_row.supplier
        all_rfq_suppliers.append(supplier_id)
        supplier_doc = frappe.get_doc("Supplier", supplier_id)
        supplier_names[supplier_id] = supplier_doc.supplier_name or supplier_id
        supplier_grand_totals[supplier_id] = 0  # Initialize to 0

    # Get all supplier quotations for this RFQ (latest first)
    # Fetch currency alongside other fields
    supplier_quotations = frappe.get_all(
        "Supplier Quotation",
        filters={
            "request_for_quotation": rfq,
            "docstatus": ["!=", 2]  # Exclude cancelled; include draft (0) and submitted (1)
        },
        fields=["name", "supplier", "modified", "total", "currency"],  # "total" is pre-tax, excludes GST
        order_by="modified desc"
    )

    processed_suppliers = {}
    supplier_currencies = {}  # supplier_id -> currency code

    # Keep latest quotation per supplier
    for sq in supplier_quotations:
        if sq.supplier not in processed_suppliers:
            processed_suppliers[sq.supplier] = sq.name
            supplier_grand_totals[sq.supplier] = sq.total or 0  # pre-tax total, excludes GST
            supplier_currencies[sq.supplier] = sq.currency or ""

    # Resolve currency symbol for each supplier (cached to avoid redundant DB hits)
    currency_symbol_cache = {}

    def get_currency_symbol(currency_code):
        if not currency_code:
            return ""
        if currency_code in currency_symbol_cache:
            return currency_symbol_cache[currency_code]
        symbol = frappe.db.get_value("Currency", currency_code, "symbol") or currency_code
        currency_symbol_cache[currency_code] = symbol
        return symbol

    supplier_currency_symbols = {
        supplier: get_currency_symbol(currency_code)
        for supplier, currency_code in supplier_currencies.items()
    }

    # Fetch payment terms, delivery terms per supplier from their quotations
    supplier_payment_terms = {}
    supplier_delivery_terms = {}
    supplier_notes = {}

    for supplier, sq_name in processed_suppliers.items():
        sq_doc = frappe.get_doc("Supplier Quotation", sq_name)
        supplier_payment_terms[supplier] = sq_doc.get("custom_payment_terms_template") or ""
        delivery_term_code = sq_doc.get("custom_delivery_terms") or ""
        supplier_delivery_terms[supplier] = get_incoterm_title(delivery_term_code) if delivery_term_code else ""
        supplier_notes[supplier] = sq_doc.get("custom_note") or ""

    # Prepare item structure from RFQ
    # Key by rfq_item.name (row ID) — handles duplicate item codes from same MR
    items_data = {}
    item_order = []  # preserve insertion order

    for rfq_item in rfq_doc.items:
        material_request = rfq_item.get("material_request") or ""
        key = rfq_item.name  # unique row ID

        last_purchase = get_last_purchase_details(rfq_item.item_code)

        # Strip HTML tags from description, preserving structure from Frappe text editor HTML
        description = rfq_item.description or rfq_item.item_name or rfq_item.item_code
        if description:
            import re
            from frappe.utils import strip_html_tags

            # Convert ordered list items to numbered text before stripping
            # Frappe text editor saves <ol><li>item</li></ol>
            ol_counter = [0]
            def replace_ol_li(m):
                ol_counter[0] += 1
                return f'\n{ol_counter[0]}. '
            # Reset counter per <ol> block
            def replace_ol(m):
                ol_counter[0] = 0
                return m.group(0)
            description = re.sub(r'<ol[^>]*>', replace_ol, description, flags=re.IGNORECASE)
            description = re.sub(r'<ol[^>]*>.*?</ol>', lambda m: re.sub(r'<li[^>]*>', replace_ol_li, m.group(0), flags=re.IGNORECASE), description, flags=re.IGNORECASE | re.DOTALL)

            # Convert unordered list items to bullet text
            description = re.sub(r'<ul[^>]*>.*?</ul>', lambda m: re.sub(r'<li[^>]*>', '\n• ', m.group(0), flags=re.IGNORECASE), description, flags=re.IGNORECASE | re.DOTALL)

            # Replace block-level closing tags with newlines
            description = re.sub(r'<br\s*/?>', '\n', description, flags=re.IGNORECASE)
            description = re.sub(r'</p>|</div>|</tr>|</li>', '\n', description, flags=re.IGNORECASE)

            description = strip_html_tags(description)

            # Decode common HTML entities
            description = description.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&nbsp;', ' ').replace('&#39;', "'").replace('&quot;', '"')

            # Collapse runs of blank lines, trim
            description = re.sub(r'\n{3,}', '\n\n', description).strip()

        items_data[key] = {
            "rfq_item_row": rfq_item.name,
            "item_code": rfq_item.item_code,
            "material_request": material_request,
            "description": description,
            "qty": rfq_item.qty,
            "uom": rfq_item.uom or rfq_item.stock_uom,
            "last_purchase_rate": last_purchase.get("rate", ""),
            "last_purchase_supplier": last_purchase.get("supplier", "")
        }
        item_order.append(key)

    # Track lowest rate supplier per rfq_item_row
    lowest_rate_suppliers = {}

    # Iterate through suppliers that have quotations
    for supplier, sq_name in processed_suppliers.items():
        try:
            sq_doc = frappe.get_doc("Supplier Quotation", sq_name)
        except Exception as e:
            frappe.logger().error(f"Error fetching Supplier Quotation {sq_name}: {str(e)}")
            continue

        for item in sq_doc.items:
            # Match SQ item back to its RFQ item row via request_for_quotation_item
            rfq_row_name = item.get("request_for_quotation_item") or ""
            key = rfq_row_name

            if key in items_data:
                items_data[key][supplier] = {
                    "rate": item.rate,
                    "qty": item.qty,
                    "amount": item.amount,
                    # Store the currency symbol alongside so the JS can render it per cell
                    "currency_symbol": supplier_currency_symbols.get(supplier, "")
                }

                # Compare by rate; on tie use supplier grand total as tiebreaker
                if item.rate and item.rate > 0:
                    if key not in lowest_rate_suppliers:
                        lowest_rate_suppliers[key] = {
                            "supplier": supplier,
                            "rate": item.rate,
                            "qty": item.qty,
                            "amount": item.amount,
                            "supplier_quotation": sq_name
                        }
                    else:
                        current = lowest_rate_suppliers[key]
                        current_grand_total = supplier_grand_totals.get(current["supplier"], 0) or 0
                        new_grand_total = supplier_grand_totals.get(supplier, 0) or 0
                        if item.rate < current["rate"]:
                            lowest_rate_suppliers[key] = {
                                "supplier": supplier,
                                "rate": item.rate,
                                "qty": item.qty,
                                "amount": item.amount,
                                "supplier_quotation": sq_name
                            }
                        elif item.rate == current["rate"] and new_grand_total < current_grand_total:
                            lowest_rate_suppliers[key] = {
                                "supplier": supplier,
                                "rate": item.rate,
                                "qty": item.qty,
                                "amount": item.amount,
                                "supplier_quotation": sq_name
                            }

    # Populate supplier selection table
    sqc.set("supplier_selection_table", [])

    grand_total = 0

    for rfq_row_name, lowest_info in lowest_rate_suppliers.items():
        item_info = items_data[rfq_row_name]

        # Fetch delivery_term, payment_terms, and notes from supplier quotation
        sq_delivery_term, sq_payment_terms, sq_notes = frappe.db.get_value(
            "Supplier Quotation",
            lowest_info["supplier_quotation"],
            ["custom_delivery_terms", "custom_payment_terms_template", "custom_note"]
        )

        sqc.append("supplier_selection_table", {
            "item_code": item_info["item_code"],
            "material_request": item_info["material_request"],
            "rfq_item_row": rfq_row_name,
            "suggested_supplier": lowest_info["supplier"],
            "supplier": lowest_info["supplier"],
            "supplier_quotation": lowest_info["supplier_quotation"],
            "rate": lowest_info["rate"],
            "qty": lowest_info["qty"],
            "amount": lowest_info["amount"],
            "payment_terms_template": sq_payment_terms,
            "delivery_term": sq_delivery_term,
            "notes": sq_notes or "",
            "manually_changed": 0
        })

        grand_total += lowest_info["amount"]

    # Set the grand total
    sqc.grand_total = grand_total

    # STORE COMPARISON TABLE DATA IN CHILD TABLE
    sqc.set("comparison_table", [])

    # Use all suppliers from RFQ (sorted)
    suppliers = sorted(all_rfq_suppliers)

    for key in item_order:
        item_info = items_data[key]
        item_code = item_info["item_code"]
        material_request = item_info["material_request"]

        row_data = {
            "rfq_item_row": key,
            "item_code": item_code,
            "material_request": material_request,
            "description": item_info.get("description", ""),
            "qty": item_info.get("qty", 0),
            "uom": item_info.get("uom", ""),
            "last_purchase_rate": item_info.get("last_purchase_rate", 0),
            "last_purchase_supplier": item_info.get("last_purchase_supplier", "")
        }

        # Each supplier entry is now {"rate": value, "currency_symbol": "₹"}
        # so the JS can render symbol + rate together in each cell
        supplier_rates = {}
        for supplier in suppliers:
            supplier_data = item_info.get(supplier, {})
            display_name = supplier_names[supplier]
            if supplier_data:
                rate_val = supplier_data.get("rate", None)
                sym = supplier_data.get("currency_symbol", "")
                if rate_val is None or rate_val == 0:
                    supplier_rates[display_name] = {"rate": "N/A", "currency_symbol": sym}
                else:
                    supplier_rates[display_name] = {"rate": rate_val, "currency_symbol": sym}
            else:
                supplier_rates[display_name] = {"rate": "N/A", "currency_symbol": ""}

        # Embed the lowest supplier name directly in supplier_rates JSON
        if key in lowest_rate_suppliers:
            lowest_supplier = lowest_rate_suppliers[key]["supplier"]
            lowest_display_name = supplier_names.get(lowest_supplier, lowest_supplier)
            supplier_rates["__lowest__"] = lowest_display_name
            row_data["lowest_rate_supplier"] = lowest_display_name

        row_data["supplier_rates"] = frappe.as_json(supplier_rates)

        sqc.append("comparison_table", row_data)

    # Add total row — grand totals also carry the currency symbol
    total_supplier_grand_totals = {}
    for supplier in suppliers:
        total_value = supplier_grand_totals.get(supplier, 0)
        display_name = supplier_names[supplier]
        sym = supplier_currency_symbols.get(supplier, "")
        if supplier not in processed_suppliers:
            total_supplier_grand_totals[display_name] = {"value": "No Quotation", "currency_symbol": ""}
        else:
            total_supplier_grand_totals[display_name] = {"value": total_value, "currency_symbol": sym}

    total_row = {
        "item_code": "TOTAL",
        "material_request": "",
        "description": "",
        "qty": 0,
        "uom": "",
        "last_purchase_rate": 0,
        "last_purchase_supplier": "",
        "supplier_grand_totals": frappe.as_json(total_supplier_grand_totals),
        "supplier_rates": ""
    }
    sqc.append("comparison_table", total_row)

    # Add payment terms, delivery terms, and notes rows
    payment_terms_data = {}
    delivery_terms_data = {}
    notes_data = {}
    for supplier in suppliers:
        name = supplier_names[supplier]
        payment_terms_data[name] = supplier_payment_terms.get(supplier, "") if supplier in processed_suppliers else "No Quotation"
        delivery_terms_data[name] = supplier_delivery_terms.get(supplier, "") if supplier in processed_suppliers else "No Quotation"
        notes_data[name] = supplier_notes.get(supplier, "") if supplier in processed_suppliers else "No Quotation"

    sqc.append("comparison_table", {
        "item_code": "PAYMENT_TERMS",
        "material_request": "",
        "description": "",
        "qty": 0,
        "uom": "",
        "last_purchase_rate": 0,
        "last_purchase_supplier": "",
        "supplier_rates": frappe.as_json(payment_terms_data)
    })
    sqc.append("comparison_table", {
        "item_code": "DELIVERY_TERMS",
        "material_request": "",
        "description": "",
        "qty": 0,
        "uom": "",
        "last_purchase_rate": 0,
        "last_purchase_supplier": "",
        "supplier_rates": frappe.as_json(delivery_terms_data)
    })
    sqc.append("comparison_table", {
        "item_code": "NOTES",
        "material_request": "",
        "description": "",
        "qty": 0,
        "uom": "",
        "last_purchase_rate": 0,
        "last_purchase_supplier": "",
        "supplier_rates": frappe.as_json(notes_data)
    })
    # Refresh attached files on every Fetch Report — clear and re-fetch from current SQs
    sqc.set("attached_files", [])
    supplier_quotations_for_files = frappe.get_all(
        "Supplier Quotation",
        filters={
            "request_for_quotation": rfq,
            "docstatus": ["!=", 2]  # Exclude cancelled
        },
        fields=["name", "supplier"],
        distinct=True,
        order_by="name desc"
    )
    for sq in supplier_quotations_for_files:
        files = frappe.get_all(
            "File",
            filters={
                "attached_to_doctype": "Supplier Quotation",
                "attached_to_name": sq.name
            },
            fields=["name", "file_name", "file_url"]
        )
        for f in files:
            sqc.append("attached_files", {
                "supplier": sq.supplier,
                "supplier_quotation": sq.name,
                "file": f.name,
                "file_name": f.file_name,
                "file_url": f.file_url
            })

    sqc.save(ignore_permissions=True)
    frappe.db.commit()

    # Build report columns
    columns = ["Item Code", "Material Request", "Description", "Qty", "UOM", "Last Purchase Rate", "Last Purchase Supplier"]
    for supplier in suppliers:
        columns.append(f"{supplier_names[supplier]} - Rate")

    # Build report rows
    data = []
    for key in item_order:
        item_info = items_data[key]
        item_code = item_info["item_code"]
        material_request = item_info["material_request"]

        row = {
            "Item Code": item_code,
            "Material Request": material_request,
            "Description": item_info.get("description", ""),
            "Qty": item_info.get("qty", ""),
            "UOM": item_info.get("uom", ""),
            "Last Purchase Rate": item_info.get("last_purchase_rate", ""),
            "Last Purchase Supplier": item_info.get("last_purchase_supplier", "")
        }

        for supplier in suppliers:
            supplier_data = item_info.get(supplier, {})
            if supplier_data:
                rate_val = supplier_data.get("rate", None)
                row[f"{supplier_names[supplier]} - Rate"] = "N/A" if (rate_val is None or rate_val == 0) else rate_val
            else:
                row[f"{supplier_names[supplier]} - Rate"] = "N/A"

        data.append(row)

    # Add total row to report data
    total_row_data = {
        "Item Code": "TOTAL",
        "Material Request": "",
        "Description": "",
        "Qty": "",
        "UOM": "",
        "Last Purchase Rate": "",
        "Last Purchase Supplier": ""
    }
    for supplier in suppliers:
        total_value = supplier_grand_totals.get(supplier, 0)
        if supplier not in processed_suppliers:
            total_row_data[f"{supplier_names[supplier]} - Rate"] = "No Quotation"
        else:
            total_row_data[f"{supplier_names[supplier]} - Rate"] = total_value
    data.append(total_row_data)

    return {
        "columns": columns,
        "data": data,
        "lowest_rate_suppliers": lowest_rate_suppliers,
        "supplier_id_to_name": supplier_names
    }


@frappe.whitelist()
def clear_selection_table_links(docname):
    """Clear purchase_order and supplier_quotation from all rows in supplier_selection_table"""
    doc = frappe.get_doc("Supplier Quotation Comparison", docname)

    if doc.docstatus != 1:
        frappe.throw(_("Document must be submitted to clear links"))

    for row in doc.supplier_selection_table:
        row.purchase_order = ""
        row.supplier_quotation = ""

    doc.flags.ignore_validate_update_after_submit = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()


def format_indian_currency(rate):
    """Format a number using Indian comma system (lakhs, crores). e.g. 1234567.89 -> '12,34,567.89'"""
    rate = float(rate)
    is_negative = rate < 0
    rate = abs(rate)
    # Split into integer and decimal parts
    int_part = int(rate)
    dec_part = f"{rate:.2f}".split(".")[1]
    # Indian grouping: last 3 digits, then groups of 2
    s = str(int_part)
    if len(s) > 3:
        last3 = s[-3:]
        rest = s[:-3]
        # Group rest in pairs from the right
        groups = []
        while len(rest) > 2:
            groups.append(rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.append(rest)
        groups.reverse()
        s = ",".join(groups) + "," + last3
    return ("-" if is_negative else "") + s + "." + dec_part


def get_last_purchase_details(item_code):
    """Get the last purchase rate and supplier for an item from the latest submitted Purchase Order"""
    last_purchase = frappe.db.sql("""
        SELECT
            poi.rate,
            po.supplier,
            po.transaction_date,
            po.currency
        FROM
            `tabPurchase Order Item` poi
        INNER JOIN
            `tabPurchase Order` po ON poi.parent = po.name
        WHERE
            poi.item_code = %(item_code)s
            AND po.docstatus = 1
        ORDER BY
            po.transaction_date DESC, po.creation DESC
        LIMIT 1
    """, {"item_code": item_code}, as_dict=True)

    if last_purchase:
        supplier_name = frappe.db.get_value("Supplier", last_purchase[0].supplier, "supplier_name")
        currency_symbol = frappe.db.get_value("Currency", last_purchase[0].currency, "symbol") or ""
        rate = last_purchase[0].rate or 0
        formatted_rate = f"{currency_symbol}{format_indian_currency(rate)}" if currency_symbol else format_indian_currency(rate)
        return {
            "rate": formatted_rate,
            "supplier": supplier_name or last_purchase[0].supplier
        }

    return {"rate": "", "supplier": ""}


def add_po_reference(comparison_doc, po, selected_rfq_item_rows):
    """
    Update selection table rows with purchase_order field.
    selected_rfq_item_rows is a set of rfq_item_row values.
    """
    for row in comparison_doc.supplier_selection_table:
        if row.get("rfq_item_row") in selected_rfq_item_rows and row.supplier == po.supplier:
            row.purchase_order = po.name


def create_po_from_supplier_quotation(sq_name, selected_items, comparison_doc, project, cost_center, po_schedule_date):
    try:
        from erpnext.buying.doctype.supplier_quotation.supplier_quotation import make_purchase_order

        po = make_purchase_order(sq_name)

        # Set project and cost center at header level
        if hasattr(po, 'custom_project'):
            po.custom_project = project
        elif hasattr(po, 'project'):
            po.project = project

        if hasattr(po, 'custom_cost_center'):
            po.custom_cost_center = cost_center
        elif hasattr(po, 'cost_center'):
            po.cost_center = cost_center

        # Populate custom proposer fields from SQC document
        proposer_user = comparison_doc.get("created_by")

        if hasattr(po, 'custom_proposed_by') and proposer_user:
            po.custom_proposed_by = proposer_user

        if proposer_user and (hasattr(po, 'custom_proposer_name') or hasattr(po, 'custom_proposer_designation')):
            proposer_employee = frappe.db.get_value(
                "Employee",
                {"user_id": proposer_user},
                ["employee_name", "designation"],
                as_dict=True
            )

            if proposer_employee:
                if hasattr(po, 'custom_proposer_name'):
                    po.custom_proposer_name = proposer_employee.get("employee_name")
                if hasattr(po, 'custom_proposer_designation'):
                    po.custom_proposer_designation = proposer_employee.get("designation")

        # Populate custom approver fields from SQC document
        if comparison_doc.docstatus == 1:
            approver_user = comparison_doc.modified_by

            if hasattr(po, 'custom_approver'):
                po.custom_approver = approver_user

            if hasattr(po, 'custom_approver_name') or hasattr(po, 'custom_approver_designation'):
                approver_employee = frappe.db.get_value(
                    "Employee",
                    {"user_id": approver_user},
                    ["employee_name", "designation"],
                    as_dict=True
                )

                if approver_employee:
                    if hasattr(po, 'custom_approver_name'):
                        po.custom_approver_name = approver_employee.get("employee_name")
                    if hasattr(po, 'custom_approver_designation'):
                        po.custom_approver_designation = approver_employee.get("designation")

        # Build a map keyed by rfq_item_row for row-level precise matching
        selected_items_map = {
            item["rfq_item_row"]: item
            for item in selected_items
            if item.get("rfq_item_row")
        }
        # Also build sq_item → rfq_item_row lookup so PO items can be matched
        sq_doc_for_map = frappe.get_doc("Supplier Quotation", sq_name)
        sq_item_to_rfq_row = {
            sq_item.name: (sq_item.get("request_for_quotation_item") or "")
            for sq_item in sq_doc_for_map.items
        }

        first_item = selected_items[0] if selected_items else {}
        payment_terms_template = first_item.get("payment_terms_template")
        delivery_term = first_item.get("delivery_term")
        notes = first_item.get("notes") or ""

        if payment_terms_template:
            po.payment_terms_template = payment_terms_template
            po.run_method("set_payment_schedule")

        if delivery_term and hasattr(po, 'custom_delivery_terms'):
            po.custom_delivery_terms = delivery_term

        if notes and hasattr(po, 'custom_notes'):
            po.custom_notes = notes

        # Set terms and conditions
        po.tc_name = "GENERAL PURCHASE TERMS AND CONDITIONS"
        terms_content = frappe.db.get_value("Terms and Conditions", "GENERAL PURCHASE TERMS AND CONDITIONS", "terms")
        if terms_content:
            po.terms = terms_content

        items_to_keep = []
        for po_item in po.items:
            sq_item_name = po_item.get("supplier_quotation_item") or ""
            rfq_row = sq_item_to_rfq_row.get(sq_item_name, "")
            key = rfq_row

            if key in selected_items_map:
                selected_item = selected_items_map[key]
                po_item.qty = selected_item["qty"]
                po_item.rate = selected_item["rate"]

                # schedule_date is calculated as today + required_by_in_days at submit time
                # po_schedule_date is passed in already computed from create_purchase_orders_on_submit
                po_item.schedule_date = po_schedule_date

                if hasattr(po_item, 'custom_project'):
                    po_item.custom_project = project
                elif hasattr(po_item, 'project'):
                    po_item.project = project

                if hasattr(po_item, 'custom_cost_center'):
                    po_item.custom_cost_center = cost_center
                elif hasattr(po_item, 'cost_center'):
                    po_item.cost_center = cost_center

                # Set material_request on the PO item if the field exists
                if hasattr(po_item, 'material_request') and selected_item.get("material_request"):
                    po_item.material_request = selected_item["material_request"]

                items_to_keep.append(po_item)

        po.items = items_to_keep

        if hasattr(po, 'custom_supplier_quotation_comparison'):
            po.custom_supplier_quotation_comparison = comparison_doc.name

        po.docstatus = 0
        po.insert(ignore_permissions=False)
        po.submit()

        frappe.msgprint(
            _("Purchase Order {0} successfully submitted for supplier {1}").format(
                frappe.bold(po.name),
                frappe.bold(po.supplier)
            )
        )

        return po
    except Exception as e:
        frappe.logger().error(f"Error creating PO from SQ {sq_name}: {str(e)}")
        raise
