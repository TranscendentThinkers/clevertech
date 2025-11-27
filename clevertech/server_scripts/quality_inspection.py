import frappe
def before_validate(doc,method):
    if doc.inspection_type == "Incoming" and doc.reference_type == "Purchase Receipt" and doc.reference_name:
        purchase_receipt = frappe.get_doc("Purchase Receipt", doc.reference_name)

    # Iterate through the items in the Purchase Receipt
        for item in purchase_receipt.items:
            if item.item_code == doc.item_code:# and item.qty == doc.custom_qty_to_inspect:
                doc.child_row_reference = item.name
def validate(doc, method):
    # Fetch the Purchase Receipt document
    if doc.inspection_type == "Incoming" and doc.reference_type == "Purchase Receipt" and doc.reference_name:
        purchase_receipt = frappe.get_doc("Purchase Receipt", doc.reference_name)

    # Iterate through the items in the Purchase Receipt
        for item in purchase_receipt.items:
            if item.item_code == doc.item_code and item.name == doc.child_row_reference:
                # Update the qty directly in the child table
                doc.custom_qty_to_inspect = item.qty
                break

def before_submit(doc,method):
    if doc.inspection_type == "Incoming" and doc.reference_type == "Purchase Receipt":
        if doc.custom_accepted_qty + doc.custom_rejected_qty > doc.custom_qty_to_inspect:
            frappe.throw(f"Accepted+Rejected cannot be greater than Qty to Inspect {doc.custom_qty_to_inspect}")

def on_submit(doc, method):
    # Only for PR-linked QI
    if doc.reference_type != "Purchase Receipt" or not doc.reference_name:
        return

    pr = frappe.get_doc("Purchase Receipt", doc.reference_name)

    all_ok = True

    for row in pr.items:
        requires_qi = frappe.db.get_value(
            "Item",
            row.item_code,
            "inspection_required_before_purchase"
        )

        if requires_qi:
            qi_exists = frappe.db.exists(
                "Quality Inspection",
                {
                    "reference_type": "Purchase Receipt",
                    "reference_name": pr.name,
                    "item_code": row.item_code,
                    "docstatus": 1
                }
            )
            if not qi_exists:
                all_ok = False
                break

    pr.db_set("custom_quality_status", "Completed" if all_ok else "Pending")
    frappe.db.commit()


#def on_submit(doc, method):
    # Check if the inspection_type is 'Incoming' and reference_type is 'Purchase Receipt'
#    if doc.inspection_type == "Incoming" and doc.reference_type == "Purchase Receipt":

        # Fetch the Purchase Receipt document
#        purchase_receipt = frappe.get_doc("Purchase Receipt", doc.reference_name)
#        if purchase_receipt.rejected_warehouse:
#            rejected_warehouse = purchase_receipt.rejected_warehouse
#        else:
#            rejected_warehouse = frappe.db.get_value("Warehouse",{"is_rejected_warehouse":1},"name")


        # Iterate through the items in the Purchase Receipt
#        for item in purchase_receipt.items:
#            if item.item_code == doc.item_code and item.name == doc.child_row_reference:
                # Update the qty and rejected_qty directly in the child table
#                item.qty = doc.custom_accepted_qty
#                item.rejected_qty = doc.custom_rejected_qty
#                item.rejected_warehouse=rejected_warehouse


        # Save the changes to the Purchase Receipt
#        purchase_receipt.save()
#        frappe.db.commit()  # Ensure changes are saved to the database



