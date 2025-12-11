# Copyright (c) 2025, Bharatbodh and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class GRNQualityInspection(Document):

    def validate(self):
        over_requested = []
        for row in self.grn_items:
            # Check accepted qty
            if (row.accepted_qty + row.rejected_qty or 0) > (row.qty_to_inspect or 0):
                over_requested.append(row.item_code)
        frappe.throw(
                f"Accepted + Rejected Qty cannot be greater than Qty To Inspect "
                f"for <b>{over_requested}</b>."
            )         
            

	
