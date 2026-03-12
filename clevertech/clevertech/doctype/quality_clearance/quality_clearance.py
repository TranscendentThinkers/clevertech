import html
import frappe
from frappe.model.document import Document


@frappe.whitelist()
def get_qc_print_html(doc_name):
	doc = frappe.get_doc("Quality Clearance", doc_name)
	frappe.has_permission("Quality Clearance", "print", doc=doc_name, throw=True)

	lh = frappe.db.get_value("Letter Head", "QC Letter Head", ["content", "footer"], as_dict=True)

	# Render footer Jinja (inspected_by lookup, supplier name fallback, etc.)
	footer_html = frappe.render_template(lh.footer or "", {"doc": doc})

	# Sync footer "FOR [name]" row heights: Clevertech's long name wraps to 2 lines (3 total).
	# When supplier name is short (won't wrap), inject <br> so both cells have equal height.
	_sname = doc.supplier_name or ""
	if len(_sname) < 45:
		_marker = 'colspan="4"'
		_idx1 = footer_html.find(_marker)
		if _idx1 >= 0:
			_idx2 = footer_html.find(_marker, _idx1 + len(_marker))
			if _idx2 >= 0:
				_close = footer_html.find("</td>", _idx2)
				if _close >= 0:
					footer_html = footer_html[:_close] + "<br><br>" + footer_html[_close:]

	supplier_name = html.escape(
		doc.supplier_name
		or frappe.db.get_value("Purchase Receipt", doc.grn_name, "supplier_name")
		or frappe.db.get_value("Supplier", doc.supplier, "supplier_name")
		or ""
	)

	if doc.type == "Purchase Order Based":
		po_grn_label, po_grn_value = "PO NO.", html.escape(doc.po_no or "")
	else:
		po_grn_label, po_grn_value = "GRN NO.", html.escape(doc.grn_name or "")

	items_rows = ""
	for i, row in enumerate(doc.grn_items_quality_reqd, 1):
		items_rows += f"""<tr>
			<td style="text-align:center;">{i}</td>
			<td style="text-align:center;">{html.escape(row.item_code or "")}</td>
			<td style="text-align:center;">{html.escape(row.item_name or "")}</td>
			<td style="text-align:center;">{row.po_qty or 0}</td>
			<td style="text-align:center;">{row.accepted_qty or 0}</td>
			<td style="text-align:center;">{row.rejected_qty or 0}</td>
			<td style="text-align:center;">{html.escape(row.type_of_issue or "")}</td>
			<td style="text-align:center;">{html.escape(row.reason or "")}</td>
		</tr>"""

	notes_html = f'<div style="margin-top:6px;">{doc.notes}</div>' if doc.notes else ""

	site_url = frappe.utils.get_url()
	has_images_in_notes = "<img" in (doc.notes or "")

	# Footer placement strategy:
	# - Notes has images → <tfoot> (follows content, prevents image/footer overlap)
	# - Notes is text-only → position:fixed pinned to page bottom
	if has_images_in_notes:
		footer_tfoot = f"<tfoot><tr><td class=\"footer-cell\">{footer_html}</td></tr></tfoot>"
		footer_fixed = ""
		content_padding_bottom = "5mm"
		page_margin_bottom = "8mm"
	else:
		footer_tfoot = ""
		footer_fixed = f"<div class=\"page-footer\">{footer_html}</div>"
		content_padding_bottom = "70mm"
		page_margin_bottom = "8mm"

	return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<base href="{site_url}">
<title>Quality Inspection Report - {html.escape(doc_name)}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: Arial, sans-serif; font-size: 11px; }}
@page {{
	size: A4;
	margin: 0 15mm {page_margin_bottom} 15mm;
	@bottom-center {{
		content: "Page " counter(page) " of " counter(pages);
		font-size: 9px;
		color: #333;
	}}
}}
/* Outer layout table */
.outer-table {{ width: 100%; border-collapse: collapse; border: none; }}
.outer-table > thead > tr > td,
.outer-table > tfoot > tr > td,
.outer-table > tbody > tr > td {{ border: none; padding: 0; }}
/* Header cell */
.header-cell {{ padding: 5mm 0 0 0; }}
/* Footer cell (tfoot mode) */
.footer-cell {{ padding: 3mm 0; }}
/* Fixed footer (text-only mode) */
.page-footer {{
	position: fixed;
	bottom: 8mm; left: 0; right: 0;
	padding: 3mm 0;
	background: white;
}}
/* Global table styles */
table {{ width: 100%; border-collapse: collapse; font-size: 10px; }}
table, th, td {{ border: 1px solid #aaa; }}
th, td {{ padding: 6px; }}
.no-border, .no-border td, .no-border th {{ border: none !important; }}
tr {{ page-break-inside: avoid; }}
table {{ page-break-inside: auto; }}
/* Suppress borders inside header and footer cells */
.header-cell table, .header-cell th, .header-cell td {{ border: none !important; }}
/* Sync footer table header rows — ensures short supplier names match 2-line Clevertech name */
.footer-cell td[colspan="4"], .page-footer td[colspan="4"] {{ height: 3.5em; vertical-align: bottom; }}
/* Content cell */
.content-cell {{ padding: 5mm 0 {content_padding_bottom} 0; }}
.content-cell img {{ max-width: 100%; height: auto; margin-bottom: 14mm; }}
.print-btn {{
	position: fixed; top: 10px; right: 10px; z-index: 9999;
	padding: 8px 18px; background: #5c7cfa; color: white;
	border: none; border-radius: 4px; cursor: pointer; font-size: 13px;
}}
@media print {{ .print-btn {{ display: none; }} }}
</style>
<script>window.addEventListener('load', function() {{ window.print(); }});</script>
</head>
<body>

<button class="print-btn" onclick="window.print()">Print / Save PDF</button>

{footer_fixed}

<table class="outer-table">
<thead>
<tr><td class="header-cell">{lh.content or ""}</td></tr>
</thead>
{footer_tfoot}
<tbody>
<tr><td class="content-cell">

<div style="text-align:center; margin-bottom:6px;">
	<strong style="font-size:14px;">Quality Inspection Report</strong>
</div>

<table class="no-border" style="margin-bottom:5px; font-size:11px;">
<tr>
	<td style="width:20%; padding:3px 2px;">VENDOR NAME</td>
	<td style="width:2%; text-align:center;">:</td>
	<td style="width:33%; padding-left:3px;">{supplier_name}</td>
	<td style="width:13%; padding:3px 2px; text-align:right;">DATE</td>
	<td style="width:2%; text-align:center;">:</td>
	<td style="width:30%; padding-left:3px;">{doc.posting_date}</td>
</tr>
<tr>
	<td style="padding:3px 2px;">{po_grn_label}</td>
	<td style="text-align:center;">:</td>
	<td style="padding-left:3px;">{po_grn_value}</td>
	<td style="text-align:right; padding:3px 2px;">PRJ NO.</td>
	<td style="text-align:center;">:</td>
	<td style="padding-left:3px;">{html.escape(doc.project or "")}</td>
</tr>
<tr>
	<td style="padding:3px 2px;">SUB</td>
	<td style="text-align:center;">:</td>
	<td style="padding-left:3px;">MOM between Clevertech and {supplier_name}</td>
	<td></td><td></td><td></td>
</tr>
</table>

<table>
<thead>
<tr>
	<th style="width:7%; text-align:center;">Sr No.</th>
	<th style="width:19%; text-align:center;">Part Code</th>
	<th style="width:25%; text-align:center;">Item Description</th>
	<th style="width:4%; text-align:center;">Qty</th>
	<th style="width:12%; text-align:center;">Accepted Qty</th>
	<th style="width:11%; text-align:center;">Rejected Qty</th>
	<th style="width:13%; text-align:center;">Type of Issue</th>
	<th style="width:11%; text-align:center;">Reason</th>
</tr>
</thead>
<tbody>{items_rows}</tbody>
</table>

<div style="margin-top:12px;">
	<strong>NOTES:</strong>
	{notes_html}
</div>

</td></tr>
</tbody>
</table>

</body>
</html>"""


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
            self.supplier = grn.supplier
            self.supplier_name = grn.supplier_name
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
