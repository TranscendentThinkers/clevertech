import frappe

def on_submit(doc, method):
    pending = False

    for row in doc.items:
        # Check if item requires inspection
        requires_qi = frappe.db.get_value(
            "Item",
            row.item_code,
            "inspection_required_before_purchase"
        )

        if requires_qi:
            # Look for submitted QI for this PR + Item
            qi_exists = frappe.db.exists(
                "Quality Inspection",
                {
                    "reference_type": "Purchase Receipt",
                    "reference_name": doc.name,
                    "item_code": row.item_code,
                    "docstatus": 1
                }
            )
            if not qi_exists:
                pending = True
                break

    doc.db_set("custom_quality_status", "Pending" if pending else "Completed")

def before_validate(doc, method):
    # Skip warehouse changes if custom_bulk_quality_inspection_for_grn is filled
    if doc.get("custom_bulk_quality_inspection_for_grn"):
        return
    
    # Fetch settings once
    settings = frappe.get_cached_doc("Quality Warehouse Settings")
    qc_accepted = settings.qc_accepted_warehouse or doc.set_warehouse
    qc_rejected = settings.qc_rejected_warehouse or doc.rejected_warehouse
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
            row.rejected_warehouse = qc_rejected
        else:
            row.warehouse = default_store

def before_submit(doc, method):
    if doc.custom_bulk_quality_inspection_for_grn:
        if frappe.db.get_value("Quality Clearance", doc.custom_bulk_quality_inspection_for_grn, "docstatus") != 1:
            frappe.throw(f"Submit the Quality Clearance: {doc.custom_bulk_quality_inspection_for_grn}, before submitting the Purchase Receipt")


@frappe.whitelist()
def get_items_from_bulk_quality_inspection(bqi_doc):
    doc = frappe.get_doc("Quality Clearance", bqi_doc)
    qty_map = {}
    settings = frappe.get_cached_doc("Quality Warehouse Settings")
    qc_accepted = settings.qc_accepted_warehouse or doc.set_warehouse
    qc_rejected = settings.qc_rejected_warehouse or doc.rejected_warehouse
    default_store = settings.default_store_warehouse
    
    def add_rows(child_table):
        for row in child_table:
            if row.item_code:
                if row.item_code not in qty_map:
                    qty_map[row.item_code] = {"accepted_qty": 0, "rejected_qty": 0}
                
                if row.accepted_qty:
                    qty_map[row.item_code]["accepted_qty"] += row.accepted_qty
                
                if row.rejected_qty:
                    qty_map[row.item_code]["rejected_qty"] += row.rejected_qty
    
    add_rows(doc.grn_items_quality_reqd)
    #add_rows(doc.grn_items_quality_not_reqd)
    
    return [
        {
            "item_code": item_code, 
            "qty": qty_data["accepted_qty"],
            "rejected_qty": qty_data["rejected_qty"],
            "warehouse": default_store,
            "rejected_warehouse": qc_rejected
        }
        for item_code, qty_data in qty_map.items()
    ]

@frappe.whitelist()
def submit_bqi(bqi_doc, pr_name):
    bqi = frappe.get_doc("Quality Clearance", bqi_doc)
    if bqi.docstatus == 0:
        bqi.grn_name = pr_name
        bqi.submit()
        return {"success": True, "message": "Quality Clearance Document Submitted"}
    else:
        return {"success": True, "message": "Quality Clearance Already Submitted"}
