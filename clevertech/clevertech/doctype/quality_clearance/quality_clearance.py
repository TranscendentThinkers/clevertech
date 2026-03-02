import frappe
from frappe.model.document import Document


class QualityClearance(Document):
     
    def validate(self):
        if self.is_new():
            if not self.supplier and self.po_no:
                self.supplier = frappe.db.get_value("Purchase Order", self.po_no, "supplier")
        self.validate_qty()
        # Only populate on first save or when source document changes
        if self.grn_name and not self.po_no:
            if self.is_new() or self.has_value_changed('grn_name'):
                self.get_items_from_grn()
        if self.po_no and not self.grn_name:
            if self.is_new() or self.has_value_changed('po_no'):
                self.get_items_from_po()
    
  
    def on_submit(self):
        #if not self.status:
            #frappe.throw(f"Status is mandatory for submitting Quality Inspection.")
        if not self.inspected_by:
            frappe.throw(f"Inspected By is mandatory for submitting Quality Inspection.")
        if not self.grn_name:
            frappe.throw(f"Cannot submit without GRN")
        self.validate_qty()
        self.create_quality_inspection()
        if self.type == "GRN Based":
            try:
                self.stock_transfer()
            except Exception as e:
                frappe.throw(f"Failed to transfer stock")

    def stock_transfer(self):
        wh_settings = frappe.get_single("Quality Warehouse Settings")
        accepted_wh = wh_settings.qc_accepted_warehouse
        rejected_wh = wh_settings.qc_rejected_warehouse
        for row in self.grn_items_quality_reqd:
            if row.accepted_qty>0:
                accepted_wh_in_grn = frappe.get_value("Purchase Receipt Item", {"parent": self.grn_name, "item_code": row.item_code}, "warehouse")
                row.db_set("accepted_stock_entry", self.create_stock_entry(row.item_code, accepted_wh_in_grn, accepted_wh, row.accepted_qty))
            if row.rejected_qty>0:
                row.db_set("rejected_stock_entry", self.create_stock_entry(row.item_code, accepted_wh_in_grn, rejected_wh, row.rejected_qty))    
    
    def create_stock_entry(self, item, source, target, qty):
        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = "Material Transfer"
        se.append("items", {
            "s_warehouse": source,
            "t_warehouse": target,
            "item_code": item,
            "qty": qty
        })
        se.insert()
        se.submit()
        return se.name

        
    def create_quality_inspection(self):
        for row in self.grn_items_quality_reqd:
            qi = frappe.new_doc('Quality Inspection')
            qi.inspection_type = "Incoming"
            qi.reference_type = "Purchase Receipt"
            qi.reference_name = self.grn_name
            qi.status = "Accepted"
            qi.item_code = row.item_code
            qi.custom_qty_to_inspect = row.qty_to_inspect
            qi.custom_accepted_qty = row.accepted_qty
            qi.custom_rejected_qty = row.rejected_qty
            qi.inspected_by = self.inspected_by
            qi.sample_size = row.qty_to_inspect
            qi.insert()
            qi.submit()
            row.db_set("quality_inspection_id", qi.name)
    
    def get_items_from_po(self):
        if self.po_no:
            po = frappe.get_doc("Purchase Order", self.po_no)
            self.project = po.project
            self.project_no = frappe.db.get_value("Project", self.project, "name")
            self.project_name = frappe.db.get_value("Project", self.project, "project_name")
            # Clear and repopulate only when PO changes
            self.grn_items_quality_reqd = []
           # self.grn_items_quality_not_reqd = []
            
            for row in po.items:
                remaining_qty = row.qty - (row.received_qty or 0)
                if remaining_qty <= 0:
                    continue
                if frappe.db.get_value("Item", row.item_code, "inspection_required_before_purchase") == 1:
                    self.append("grn_items_quality_reqd", {
                        "item_code": row.item_code,
                        "item_name": row.item_name,
                        "po_qty": row.qty,
                        "qty_to_inspect": remaining_qty
                    })
            if not self.grn_items_quality_reqd:
                frappe.throw(f"No items found for quality clearance in {po.name}")
                
    
    def get_items_from_grn(self):
        if self.grn_name:
            grn = frappe.get_doc("Purchase Receipt", self.grn_name)
            self.project = grn.project
            self.project_no = frappe.db.get_value("Project", self.project, "name")
            self.project_name = frappe.db.get_value("Project", self.project, "project_name")
            
            # Clear and repopulate only when GRN changes
            self.grn_items_quality_reqd = []
           # self.grn_items_quality_not_reqd = []
            
            for row in grn.items:
                po_qty = frappe.db.get_value("Purchase Order Item", row.purchase_order_item, "qty") 
                if frappe.db.get_value("Item", row.item_code, "inspection_required_before_purchase") == 1 and not row.quality_inspection:
                    self.append("grn_items_quality_reqd", {
                        "item_code": row.item_code,
                        "item_name": row.item_name,
                        "qty_to_inspect": row.qty,
                        "po_qty": po_qty
                    })
            if not self.grn_items_quality_reqd:
                frappe.throw(f"Not items found in {grn.name} with pending quality inspection.")
                    
    def validate_qty(self):
        for row in self.grn_items_quality_reqd:
            if row.accepted_qty + row.rejected_qty > row.qty_to_inspect:
                frappe.throw(f"Accepted Qty + Rejected Qty cannot be greater than Qty to Inspect for item: {row.item_code}")
            if row.accepted_qty < 0:
                frappe.throw(f"Accepted Qty cannot be less than 0 for item: {row.item_code}")
            if row.rejected_qty < 0:
                frappe.throw(f"Rejected Qty cannot be less than 0 for item: {row.item_code}")
            if row.accepted_qty + row.rejected_qty != row.qty_to_inspect:
                frappe.throw(f"Accepted Qty + Rejected Qty should be equal to Qty to Inspect for item: {row.item_code}")
            if not row.type_of_issue:
                if row.rejected_qty>0:
                    frappe.throw(f"Type of Issue is a mandatory field for the item: {row.item_code}")

        #for row in self.grn_items_quality_not_reqd:
        #    if row.accepted_qty + row.rejected_qty > row.qty_to_inspect:
        #        frappe.throw(f"Accepted Qty + Rejected Qty cannot be greater than Qty to Inspect for item: {row.item_code}")
        #    if row.accepted_qty < 0:
        #        frappe.throw(f"Accepted Qty cannot be less than 0 for item: {row.item_code}")
        #    if row.rejected_qty < 0:
        #        frappe.throw(f"Rejected Qty cannot be less than 0 for item: {row.item_code}")
