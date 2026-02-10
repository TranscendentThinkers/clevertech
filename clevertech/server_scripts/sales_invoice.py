import frappe

def before_validate(doc, method):
    """Auto-select the correct Debtors account based on invoice currency"""

    # Only apply for specific customer (or remove this check to apply for all customers)
    if doc.customer != "Clevertech S.p.A. - AR":
        return

    # Map currency to debtors account
    currency_account_map = {
        "EUR": "Debtors EUR - CT",
        "USD": "Debtors USD - CT",
        "INR": "Debtors - CT"
    }

    # Get the appropriate account based on invoice currency
    if doc.currency in currency_account_map:
        debit_account = currency_account_map[doc.currency]

        # Check if account exists
        if frappe.db.exists("Account", debit_account):
            doc.debit_to = debit_account
            frappe.logger().info(f"Auto-selected debit_to: {debit_account} for currency: {doc.currency}")
        else:
            frappe.throw(
                f"Debtors account for {doc.currency} currency not found. "
                f"Please create account: {debit_account}"
            )
