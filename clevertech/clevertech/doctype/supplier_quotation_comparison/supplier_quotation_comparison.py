import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, add_days

class SupplierQuotationComparison(Document):
    def validate(self):
        self.validate_request_for_quotations()
        self.calculate_required_by_dates()

        # Only populate items table on initial creation or when RFQ changes
        # Skip if supplier_selection_table already has data (workflow transition)
        if self.is_new() and self.request_for_quotation and not self.supplier_selection_table:
            self.populate_items_table()
            self.fetch_file_references()
            self.fetch_rfq_fields()
        elif self.has_value_changed("request_for_quotation") and self.request_for_quotation:
            # Only repopulate if RFQ actually changed (not on workflow transitions)
            self.populate_items_table()
            self.fetch_file_references()
            self.fetch_rfq_fields()

    def on_submit(self):
        """Auto-submit supplier quotations and create purchase orders on submit"""
        # Step 1: Auto-submit supplier quotations that are in draft
        self.auto_submit_supplier_quotations()

        # Step 2: Create purchase orders
        self.create_purchase_orders_on_submit()

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

    def calculate_required_by_dates(self):
        """Calculate required_by_date from required_by_in_days at document level"""
        # Get required_by_in_days from document level
        required_by_in_days = self.get("required_by_in_days")
        
        if required_by_in_days and required_by_in_days > 0:
            # Calculate and set required_by_date at document level
            self.required_by_date = add_days(today(), required_by_in_days)

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
                "qty": row.qty or 0,
                "rate": row.rate or 0,
                "payment_terms_template": row.get("payment_terms_template"),
                "delivery_term": row.get("delivery_term")
            })

        if not supplier_quotation_map:
            frappe.msgprint(
                _("No valid items with supplier quotations found for PO creation"),
                indicator="orange"
            )
            return

        created_pos = []

        for sq_name, items in supplier_quotation_map.items():
            po = create_po_from_supplier_quotation(sq_name, items, self, project, cost_center, self.required_by_date)
            if po:
                created_pos.append(po.name)
                # Update selection table with PO reference
                selected_item_codes = {item["item_code"] for item in items}
                add_po_reference(self, po, selected_item_codes)

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
        supplier_quotations = frappe.get_all(
            "Supplier Quotation",
            filters={
                "request_for_quotation": self.request_for_quotation,
                # "docstatus": 1  # Uncomment if you only want submitted ones
            },
            fields=["name", "supplier"],
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
        """Fetch project and cost_center from RFQ"""
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

    def populate_items_table(self):
        if not self.request_for_quotation:
            return

        rfq_doc = frappe.get_doc("Request for Quotation", self.request_for_quotation)
        self.supplier_selection_table = []

        # Populate the child table
        for row in rfq_doc.items:
            self.append("supplier_selection_table", {
                "item_code": row.item_code
            })

@frappe.whitelist()
def get_supplier_quotation(rfq, supplier, item_code=None):
    """
    Fetch the supplier quotation linked to the RFQ where supplier matches
    If item_code is provided, also return rate, qty, amount, and total_tax for that item
    """
    if not rfq or not supplier:
        return None

    try:
        # Find Supplier Quotation that:
        # 1. Has request_for_quotation = our RFQ
        # 2. Has supplier = our supplier
        # 3. Is not cancelled
        supplier_quotations = frappe.get_all(
            "Supplier Quotation",
            filters={
                "request_for_quotation": rfq,
                # "docstatus": 1  # Uncomment if you only want submitted quotations
            },
            fields=["name", "supplier", "modified", "grand_total"],
            order_by="modified desc"
        )

        for sq in supplier_quotations:
            if sq.supplier == supplier:
                sq_name = sq.name

                # If item_code is provided, fetch rate, qty, amount, and total_tax for that item
                if item_code:
                    try:
                        sq_doc = frappe.get_doc("Supplier Quotation", sq_name)

                        # Find the matching item in the supplier quotation
                        for item in sq_doc.items:
                            if item.item_code == item_code:
                                # Calculate total tax for this item
                                total_tax = calculate_item_tax(item)

                                return {
                                    "name": sq_name,
                                    "rate": item.rate,
                                    "qty": item.qty,
                                    "amount": item.amount,
                                    "total_tax": total_tax
                                }

                        # Item not found in this quotation
                        return {
                            "name": sq_name,
                            "rate": 0,
                            "qty": 0,
                            "amount": 0,
                            "total_tax": 0
                        }
                    except Exception as e:
                        frappe.logger().error(f"Error fetching Supplier Quotation {sq_name}: {str(e)}")
                        return {
                            "name": sq_name,
                            "rate": 0,
                            "qty": 0,
                            "amount": 0,
                            "total_tax": 0
                        }
                else:
                    # Just return the quotation name
                    return sq_name

        return None

    except Exception as e:
        frappe.logger().error(f"Error in get_supplier_quotation: {str(e)}")
        return None

def calculate_item_tax(item):
    """
    Calculate total tax for an item by summing up all tax amounts
    Supports: igst_amount, cgst_amount, sgst_amount, cess_amount, cess_non_advol_amount
    """
    total_tax = 0

    # List of tax field names to check
    tax_fields = [
        'igst_amount',
        'cgst_amount',
        'sgst_amount',
        'cess_amount',
        'cess_non_advol_amount'
    ]

    for field in tax_fields:
        if hasattr(item, field):
            field_value = getattr(item, field)
            if field_value:
                total_tax += field_value

    return total_tax

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
    supplier_quotations = frappe.get_all(
        "Supplier Quotation",
        filters={
            "request_for_quotation": rfq,
            # "docstatus": 1
        },
        fields=["name", "supplier", "modified", "grand_total"],
        order_by="modified desc"
    )

    processed_suppliers = {}

    # Keep latest quotation per supplier
    for sq in supplier_quotations:
        if sq.supplier not in processed_suppliers:
            processed_suppliers[sq.supplier] = sq.name
            supplier_grand_totals[sq.supplier] = sq.grand_total or 0

    # Prepare item structure from RFQ
    items_data = {}
    for rfq_item in rfq_doc.items:
        last_purchase = get_last_purchase_details(rfq_item.item_code)
        items_data[rfq_item.item_code] = {
            "description": rfq_item.description or rfq_item.item_name or rfq_item.item_code,
            "qty": rfq_item.qty,
            "uom": rfq_item.uom or rfq_item.stock_uom,
            "last_purchase_rate": last_purchase.get("rate", ""),
            "last_purchase_supplier": last_purchase.get("supplier", "")
        }

    # Track lowest rate supplier per item (considering amount + tax)
    lowest_rate_suppliers = {}

    # Iterate through suppliers that have quotations
    for supplier, sq_name in processed_suppliers.items():
        try:
            sq_doc = frappe.get_doc("Supplier Quotation", sq_name)
        except Exception as e:
            frappe.logger().error(f"Error fetching Supplier Quotation {sq_name}: {str(e)}")
            # Skip this quotation if there's an error fetching it
            continue

        for item in sq_doc.items:
            if item.item_code in items_data:
                # Calculate total tax for this item
                total_tax = calculate_item_tax(item)

                items_data[item.item_code][supplier] = {
                    "rate": item.rate,
                    "qty": item.qty,
                    "amount": item.amount,
                    "total_tax": total_tax
                }

                # Calculate total cost (amount + tax) for comparison
                total_cost = item.amount + total_tax

                if item.item_code not in lowest_rate_suppliers:
                    lowest_rate_suppliers[item.item_code] = {
                        "supplier": supplier,
                        "rate": item.rate,
                        "qty": item.qty,
                        "amount": item.amount,
                        "total_tax": total_tax,
                        "total_cost": total_cost,
                        "supplier_quotation": sq_name
                    }
                elif total_cost < lowest_rate_suppliers[item.item_code]["total_cost"]:
                    lowest_rate_suppliers[item.item_code] = {
                        "supplier": supplier,
                        "rate": item.rate,
                        "qty": item.qty,
                        "amount": item.amount,
                        "total_tax": total_tax,
                        "total_cost": total_cost,
                        "supplier_quotation": sq_name
                    }

    # Populate supplier selection table
    sqc.set("supplier_selection_table", [])

    grand_total = 0

    for item_code, lowest_info in lowest_rate_suppliers.items():
        sqc.append("supplier_selection_table", {
            "item_code": item_code,
            "suggested_supplier": lowest_info["supplier"],
            "supplier": lowest_info["supplier"],
            "supplier_quotation": lowest_info["supplier_quotation"],
            "rate": lowest_info["rate"],
            "qty": lowest_info["qty"],
            "amount": lowest_info["amount"],
            "total_tax": lowest_info["total_tax"],
            "manually_changed": 0
        })
        # Grand total includes amount + tax
        grand_total += (lowest_info["amount"] + lowest_info["total_tax"])

    # Set the grand total
    sqc.grand_total = grand_total

    # STORE COMPARISON TABLE DATA IN CHILD TABLE
    sqc.set("comparison_table", [])

    # Use all suppliers from RFQ (sorted)
    suppliers = sorted(all_rfq_suppliers)
    for item_code, item_info in items_data.items():
        # Create a row for each item
        row_data = {
            "item_code": item_code,
            "description": item_info.get("description", ""),
            "qty": item_info.get("qty", 0),
            "uom": item_info.get("uom", ""),
            "last_purchase_rate": item_info.get("last_purchase_rate", 0),
            "last_purchase_supplier": item_info.get("last_purchase_supplier", "")
        }

        # Store supplier rates as JSON
        supplier_rates = {}
        for supplier in suppliers:
            supplier_data = item_info.get(supplier, {})
            if supplier_data:
                supplier_rates[supplier_names[supplier]] = supplier_data.get("rate", "N/A")
            else:
                supplier_rates[supplier_names[supplier]] = "N/A"

        row_data["supplier_rates"] = frappe.as_json(supplier_rates)

        # Mark if this is the lowest rate
        if item_code in lowest_rate_suppliers:
            lowest_supplier = lowest_rate_suppliers[item_code]["supplier"]
            row_data["lowest_rate_supplier"] = supplier_names.get(lowest_supplier, lowest_supplier)

        sqc.append("comparison_table", row_data)

    # Add total row
    total_row = {
        "item_code": "TOTAL",
        "description": "",
        "qty": 0,
        "uom": "",
        "last_purchase_rate": 0,
        "last_purchase_supplier": ""
    }

    # Store grand totals (with taxes) separately
    total_supplier_grand_totals = {}
    for supplier in suppliers:
        total_value = supplier_grand_totals.get(supplier, 0)
        if supplier not in processed_suppliers:
            total_supplier_grand_totals[supplier_names[supplier]] = "No Quotation"
        else:
            total_supplier_grand_totals[supplier_names[supplier]] = total_value

    # For TOTAL row, use supplier_grand_totals instead of supplier_rates
    total_row["supplier_grand_totals"] = frappe.as_json(total_supplier_grand_totals)
    total_row["supplier_rates"] = ""  # Empty for total row
    sqc.append("comparison_table", total_row)

    sqc.save(ignore_permissions=True)
    frappe.db.commit()

    # Build report columns - use all RFQ suppliers
    columns = ["Item Code", "Description", "Qty", "UOM", "Last Purchase Rate", "Last Purchase Supplier"]

    for supplier in suppliers:
        columns.append(f"{supplier_names[supplier]} - Rate")

    # Build report rows
    data = []

    for item_code, item_info in items_data.items():
        row = {
            "Item Code": item_code,
            "Description": item_info.get("description", ""),
            "Qty": item_info.get("qty", ""),
            "UOM": item_info.get("uom", ""),
            "Last Purchase Rate": item_info.get("last_purchase_rate", ""),
            "Last Purchase Supplier": item_info.get("last_purchase_supplier", "")
        }

        for supplier in suppliers:
            supplier_data = item_info.get(supplier, {})
            # If supplier has no quotation for this item, show "N/A"
            if supplier_data:
                row[f"{supplier_names[supplier]} - Rate"] = supplier_data.get("rate", "N/A")
            else:
                row[f"{supplier_names[supplier]} - Rate"] = "N/A"

        data.append(row)

    # Add total row
    total_row = {
        "Item Code": "TOTAL",
        "Description": "",
        "Qty": "",
        "UOM": "",
        "Last Purchase Rate": "",
        "Last Purchase Supplier": ""
    }

    for supplier in suppliers:
        total_value = supplier_grand_totals.get(supplier, 0)
        # Show "No Quotation" if supplier hasn't submitted a quotation
        if supplier not in processed_suppliers:
            total_row[f"{supplier_names[supplier]} - Rate"] = "No Quotation"
        else:
            total_row[f"{supplier_names[supplier]} - Rate"] = total_value

    data.append(total_row)

    return {
        "columns": columns,
        "data": data,
        "lowest_rate_suppliers": lowest_rate_suppliers,
        "supplier_id_to_name": supplier_names
    }


def get_last_purchase_details(item_code):
    """Get the last purchase rate and supplier for an item"""
    # Query the Purchase Invoice Item table for the latest purchase
    last_purchase = frappe.db.sql("""
        SELECT
            pii.rate,
            pi.supplier,
            pi.posting_date
        FROM
            `tabPurchase Invoice Item` pii
        INNER JOIN
            `tabPurchase Invoice` pi ON pii.parent = pi.name
        WHERE
            pii.item_code = %(item_code)s
            AND pi.docstatus = 1
        ORDER BY
            pi.posting_date DESC, pi.creation DESC
        LIMIT 1
    """, {"item_code": item_code}, as_dict=True)

    if last_purchase:
        # Get supplier name
        supplier_name = frappe.db.get_value("Supplier", last_purchase[0].supplier, "supplier_name")
        return {
            "rate": last_purchase[0].rate,
            "supplier": supplier_name or last_purchase[0].supplier
        }

    return {"rate": "", "supplier": ""}

@frappe.whitelist()
def create_purchase_orders(doc_name):
    try:
        doc = frappe.get_doc("Supplier Quotation Comparison", doc_name)
        if not doc.supplier_selection_table:
            frappe.throw(_("No items in supplier selection table"))

        if not doc.request_for_quotation:
            frappe.throw(_("Request for Quotation is required"))

        # Use project and cost_center from the comparison document
        project = doc.get("project")
        cost_center = doc.get("cost_center")

        # Mandatory validation for project and cost_center
        if not project:
            frappe.throw(_("Project is mandatory for creating Purchase Orders. Please set the Project field before proceeding."))

        if not cost_center:
            frappe.throw(_("Cost Center is mandatory for creating Purchase Orders. Please set the Cost Center field before proceeding."))


        # Check if POs are already created for all items
        items_with_po = []
        items_without_po = []

        for row in doc.supplier_selection_table:
            if not row.supplier or not row.supplier_quotation or not row.item_code:
                continue

            if row.purchase_order:
                items_with_po.append(f"{row.item_code} (PO: {row.purchase_order})")
            else:
                items_without_po.append(row.item_code)

        # If all items have POs, throw error
        if items_with_po and not items_without_po:
            frappe.throw(
                _("Purchase Orders have already been created for all items.<br><br>Items with POs:<br>{0}").format(
                    "<br>".join(items_with_po)
                )
            )

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

        for row in doc.supplier_selection_table:
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
                "qty": row.qty or 0,
                "rate": row.rate or 0,
                "payment_terms_template": row.get("payment_terms_template"),
                "delivery_term": row.get("delivery_term")
            })

        if not supplier_quotation_map:
            frappe.throw(_("No valid items with supplier quotations selected"))

        created_pos = []

        for sq_name, items in supplier_quotation_map.items():
            po = create_po_from_supplier_quotation(sq_name, items, doc, project, cost_center, doc.required_by_date)
            if po:
                created_pos.append(po.name)
                # Update selection table with PO reference
                selected_item_codes = {item["item_code"] for item in items}
                add_po_reference(doc, po, selected_item_codes)

        doc.save(ignore_permissions=True)

        return {
            "success": True,
            "purchase_orders": created_pos,
            "message": f"Successfully created {len(created_pos)} Purchase Order(s) in Draft"
        }

    except Exception as e:
        frappe.logger().error(f"Error creating purchase orders: {str(e)}")
        frappe.throw(_("Error creating purchase orders: {0}").format(str(e)))


def add_po_reference(comparison_doc, po, selected_item_codes):
    """Update selection table rows with purchase_order field"""
    for row in comparison_doc.supplier_selection_table:
        if row.item_code in selected_item_codes and row.supplier == po.supplier:
            row.purchase_order = po.name


def create_po_from_supplier_quotation(sq_name, selected_items, comparison_doc, project, cost_center, required_by_date):
    try:
        # Use ERPNext's standard function - requires submitted Supplier Quotation
        from erpnext.buying.doctype.supplier_quotation.supplier_quotation import make_purchase_order

        # This will throw error if SQ is not submitted - let it fail with clear message
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

        # Build a set of selected item codes for this supplier
        selected_item_codes = {item["item_code"] for item in selected_items}

        # Create a map for quick lookup of selected items
        selected_items_map = {item["item_code"]: item for item in selected_items}

        # Extract payment_terms_template and delivery_term from first item (assumes all items in same PO have same values)
        # You may want to adjust this logic based on your business rules
        first_item = selected_items[0] if selected_items else {}
        payment_terms_template = first_item.get("payment_terms_template")
        delivery_term = first_item.get("delivery_term")

        # Set payment_terms_template at PO header level if provided
        if payment_terms_template:
            po.payment_terms_template = payment_terms_template
            # Trigger the template to populate payment schedule
            po.run_method("set_payment_schedule")

        # Set delivery_term at PO header level if provided
        if delivery_term and hasattr(po, 'custom_delivery_term'):
            po.custom_delivery_term = delivery_term

        # Filter items - keep only selected ones and update their qty/rate/required_by
        items_to_keep = []
        for po_item in po.items:
            if po_item.item_code in selected_item_codes:
                # Update qty, rate, and required_by from selection table
                selected_item = selected_items_map[po_item.item_code]
                po_item.qty = selected_item["qty"]
                po_item.rate = selected_item["rate"]

                # Use the required_by_date from document level
                if required_by_date:
                    po_item.schedule_date = required_by_date

                # Set project/cost center on item level
                if hasattr(po_item, 'custom_project'):
                    po_item.custom_project = project
                elif hasattr(po_item, 'project'):
                    po_item.project = project

                if hasattr(po_item, 'custom_cost_center'):
                    po_item.custom_cost_center = cost_center
                elif hasattr(po_item, 'cost_center'):
                    po_item.cost_center = cost_center

                items_to_keep.append(po_item)

        # Replace items with filtered list
        po.items = items_to_keep

        # Set reference to supplier quotation comparison if field exists
        if hasattr(po, 'supplier_quotation_comparison'):
            po.supplier_quotation_comparison = comparison_doc.name

        po.docstatus = 0
        po.insert(ignore_permissions=False)
        po.submit()


        frappe.msgprint(
            _("Purchase Order {0} created in Draft for supplier {1}").format(
                frappe.bold(po.name),
                frappe.bold(po.supplier)
            )
        )


        return po

    except Exception as e:
        frappe.logger().error(f"Error creating PO from SQ {sq_name}: {str(e)}")
        raise
