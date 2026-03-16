from frappe import _


def get_data(data):
    data["internal_links"]["Supplier Quotation Comparison"] = "custom_supplier_quotation_comparison"
    data["transactions"].append({
        "label": _("Procurement"),
        "items": ["Supplier Quotation Comparison"]
    })
    return data
