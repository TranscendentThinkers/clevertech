import frappe
from frappe.utils import flt, add_days, add_months, nowdate


def set_payment_schedule(doc):
    """
    Mimics ERPNext's standard payment schedule population (as done in Purchase Order)
    but writes into doc.custom_payment_schedule instead of doc.payment_schedule.
    """
    if not doc.custom_payment_terms_template:
        return

    template = frappe.get_doc("Payment Terms Template", doc.custom_payment_terms_template)
    doc.custom_payment_schedule = []  # Clear existing rows

    grand_total = flt(doc.grand_total or 0)
    posting_date = doc.transaction_date or nowdate()

    for term in template.terms:
        # Calculate due date
        if term.due_date_based_on == "Day(s) after invoice date":
            due_date = add_days(posting_date, term.credit_days)
        elif term.due_date_based_on == "Day(s) after the end of the invoice month":
            due_date = add_days(
                frappe.utils.get_last_day(posting_date), term.credit_days
            )
        elif term.due_date_based_on == "Month(s) after the end of the invoice month":
            due_date = add_months(
                frappe.utils.get_last_day(posting_date), term.credit_months
            )
        else:
            due_date = add_days(posting_date, term.credit_days or 0)

        # Calculate payment amount
        if term.invoice_portion:
            payment_amount = flt(grand_total * term.invoice_portion / 100, 2)
        else:
            payment_amount = 0.0

        doc.append("custom_payment_schedule", {
            "payment_term": term.payment_term,
            "description": term.description,
            "due_date": due_date,
            "invoice_portion": term.invoice_portion,
            "payment_amount": payment_amount,
            "mode_of_payment": term.mode_of_payment or "",
        })


def validate(doc, method):
    # Only set payment terms and schedule on the very first save.
    # After that, both fields are freely editable by the user.
    if doc.is_new():
        doc.custom_payment_terms_template = frappe.db.get_value("Supplier", doc.supplier, "payment_terms")
        set_payment_schedule(doc)

    # Collect all RFQs linked in SQ Items
    rfq_list = list({d.request_for_quotation for d in doc.items if d.request_for_quotation})
    if not rfq_list:
        return
    # Build map keyed by RFQ item row ID
    rfq_items = frappe.get_all(
        "Request for Quotation Item",
        filters={"parent": ("in", rfq_list)},
        fields=["name", "item_code", "qty", "parent"]
    )
    rfq_item_map = {i.name: i for i in rfq_items}

    # Validate each SQ row against its linked RFQ row
    for row in doc.items:
        if not row.request_for_quotation:
            frappe.throw(
                f"Extra item found in Supplier Quotation. "
                f"Item {row.item_code} does not belong to any selected Request For Quotation."
            )
        if not row.request_for_quotation_item or row.request_for_quotation_item not in rfq_item_map:
            frappe.throw(
                f"Item {row.item_code} (row {row.idx}) is not linked to a valid "
                f"Request For Quotation {row.request_for_quotation} row."
            )
        rfq_row = rfq_item_map[row.request_for_quotation_item]
        if flt(row.qty) > flt(rfq_row.qty):
            frappe.throw(
                f"Quantity mismatch for item {row.item_code} (row {row.idx}). "
                f"RFQ {row.request_for_quotation} allows {rfq_row.qty} "
                f"but Supplier Quotation has {row.qty}."
            )
    # Budget validation commented out
    # if not doc.project:
    #     doc.custom_consumed_budget = 0
    #     return
    # # Sum of submitted SQs for the same project (excluding current)
    # submitted_total = frappe.db.get_value(
    #     "Supplier Quotation",
    #     {
    #         "project": doc.project,
    #         "docstatus": 1,
    #         "name": ["!=", doc.name]
    #     },
    #     "SUM(grand_total)"
    # ) or 0
    # consumed_budget = flt(submitted_total) + flt(doc.grand_total or 0)
    # doc.custom_consumed_budget = consumed_budget
# Budget validation on submit commented out
# def before_submit(doc, method):
#     allocated_budget = flt(doc.custom_allocated_budget or 0)
#     consumed_budget = flt(doc.custom_consumed_budget or 0)
#     if consumed_budget > allocated_budget:
#         frappe.throw(
#             f"Budget exceeding.<br>"
#             f"Allocated: {allocated_budget}<br>"
#             f"Consumed: {consumed_budget}"
#         )
#     # Check if RFQ is missing any MR items
#     # rfq_keys = {f"{row.request_for_quotation}_{row.item_code}" for row in doc.items}
#     # missing_items = set(mr_map.keys()) - rfq_keys
#     # if missing_items:
#     #     missing_list = ", ".join(missing_items)
#     #     frappe.throw(
#     #         f"The following Request For Quotation items are missing in the Supplier Quotation: {missing_list}"
#     #     )
# Budget data fetch function commented out
# @frappe.whitelist()
# def get_project_budget_data(project, current_sq=None, current_sq_total=0):
#     allocated_budget = 0.0
#     consumed_budget = 0.0
#     # 1. Allocated Budget
#     budgets = frappe.get_all(
#         "Budget",
#         filters={
#             "project": project,
#             "budget_against": "Project",
#             "docstatus": 1
#         },
#         pluck="name"
#     )
#     if budgets:
#         allocated_budget = frappe.db.sql("""
#             SELECT SUM(budget_amount)
#             FROM `tabBudget Account`
#             WHERE parent IN %s
#         """, (tuple(budgets),))[0][0] or 0.0
#     return {
#         "allocated_budget": flt(allocated_budget),
#     }
