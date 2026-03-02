import json

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.party import get_party_account_currency
from erpnext.buying.doctype.request_for_quotation.request_for_quotation import add_items


@frappe.whitelist()
def create_supplier_quotation(doc):
	"""Override of erpnext's create_supplier_quotation to prevent
	price list / last purchase rates from auto-populating.

	set_missing_values (called during SQ creation) fetches rates from
	the supplier's price list into price_list_rate.  During save,
	calculate_taxes_and_totals recalculates rate from price_list_rate.

	This override captures the rates the supplier entered on the RFQ
	portal form, lets set_missing_values run for currency/taxes/other
	fields, then overwrites ALL rate-related fields before saving.
	"""
	if isinstance(doc, str):
		doc = json.loads(doc)

	# Capture rates the supplier entered on the web form.
	# RFQ Item has no rate field; the JS only sets data.rate when the
	# supplier changes the input.  Untouched items have no rate key.
	supplier_rates = {}
	for item in doc.get("items", []):
		if isinstance(item, dict):
			idx = int(item.get("idx", 0))
			supplier_rates[idx] = flt(item.get("rate", 0))

	try:
		sq_doc = frappe.get_doc(
			{
				"doctype": "Supplier Quotation",
				"supplier": doc.get("supplier"),
				"terms": doc.get("terms"),
				"company": doc.get("company"),
				"currency": doc.get("currency")
				or get_party_account_currency(
					"Supplier", doc.get("supplier"), doc.get("company")
				),
				"buying_price_list": doc.get("buying_price_list")
				or frappe.db.get_value("Buying Settings", None, "buying_price_list"),
			}
		)

		add_items(sq_doc, doc.get("supplier"), doc.get("items"))
		sq_doc.flags.ignore_permissions = True
		sq_doc.run_method("set_missing_values")

		# Restore supplier-entered rates — overwrite ALL rate-related
		# fields so calculate_taxes_and_totals (during save → validate)
		# cannot recalculate rate from price_list_rate.
		for item in sq_doc.items:
			rate = supplier_rates.get(item.idx, 0)
			item.rate = rate
			item.price_list_rate = rate
			item.base_rate = rate
			item.base_price_list_rate = rate
			item.net_rate = rate
			item.discount_percentage = 0
			item.discount_amount = 0
			item.amount = flt(rate) * flt(item.qty)
			item.base_amount = flt(rate) * flt(item.qty)
			item.net_amount = flt(rate) * flt(item.qty)
			item.base_net_amount = flt(rate) * flt(item.qty)

		sq_doc.save()
		frappe.msgprint(_("Supplier Quotation {0} Created").format(sq_doc.name))
		return sq_doc.name
	except Exception:
		return None
