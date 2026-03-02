import frappe
import pandas as pd
from frappe.utils import getdate


@frappe.whitelist()
def import_receipt_excel(file_url):

    file_path = frappe.get_site_path(
        "private", "files", file_url.split("/")[-1]
    )

    df = pd.read_excel(file_path)

    receipts = []

    # 🔴 GLOBAL ERROR COLLECTORS
    missing_customers = set()
    missing_accounts = set()
    missing_reference = set()

    current_receipt = None

    # ======================================================
    # 🔍 PASS 1 → VALIDATION ONLY
    # ======================================================
    for idx, row in df.iterrows():

        date = row.get("Date")
        particulars = row.get("Particulars")
        ref_value = row.get("Unnamed: 2")
        credit = row.get("Credit")

        # -------------------------------
        # 1️⃣ MAIN RECEIPT ROW
        # -------------------------------
        if pd.notna(date) and pd.notna(credit):

            current_receipt = {
                "date": getdate(date),
                "customer_name": str(particulars).strip() if pd.notna(particulars) else None,
                "amount": float(credit),
                "bank": None,
                "remarks": "",
                "reference_no": None,
                "reference_date": getdate(date)
            }
            continue

        if not current_receipt:
            continue

        # -------------------------------
        # 2️⃣ REFERENCE ROW
        # -------------------------------
        if isinstance(particulars, str) and particulars.strip().lower() == "new ref":
            if pd.notna(ref_value):
                current_receipt["reference_no"] = str(ref_value).strip()
            continue

        # -------------------------------
        # 3️⃣ BANK ROW
        # -------------------------------
        if isinstance(particulars, str) and "bank" in particulars.lower():
            current_receipt["bank"] = particulars.strip()
            continue

        # -------------------------------
        # 4️⃣ REMARKS ROW → FINALIZE
        # -------------------------------
        if isinstance(particulars, str) and len(particulars.strip()) > 5:

            current_receipt["remarks"] = particulars.strip()

            # -------- VALIDATIONS --------

            # Customer validation
            customer = frappe.db.get_value(
                "Customer",
                {"customer_name": current_receipt["customer_name"]},
                "name"
            )
            if not customer:
                missing_customers.add(current_receipt["customer_name"])

            # Reference validation
            if not current_receipt["reference_no"]:
                missing_reference.add(current_receipt["customer_name"])

            # Bank account validation
            if current_receipt["bank"]:
                account_name = f"{current_receipt['bank']} - CT"
                if not frappe.db.exists("Account", account_name):
                    missing_accounts.add(account_name)
            else:
                missing_accounts.add("Bank not identified")

            receipts.append(current_receipt)
            current_receipt = None

    # ======================================================
    # ❌ STOP IF ERRORS FOUND
    # ======================================================
    if missing_customers or missing_accounts or missing_reference:

        msg = "<b>❌ PAYMENT EXCEL VALIDATION FAILED</b><br><br>"

        if missing_customers:
            msg += "<b>Missing Customers:</b><br>"
            for c in sorted(missing_customers):
                msg += f"- {c}<br>"

        if missing_accounts:
            msg += "<br><b>Missing Bank Accounts:</b><br>"
            for a in sorted(missing_accounts):
                msg += f"- {a}<br>"

        if missing_reference:
            msg += "<br><b>Missing Reference No:</b><br>"
            for r in sorted(missing_reference):
                msg += f"- {r}<br>"

        frappe.log_error(
            message=msg.replace("<br>", "\n"),
            title="Receipt Excel Validation Errors"
        )

        frappe.throw(msg)

    # ======================================================
    # ✅ PASS 2 → CREATE PAYMENT ENTRIES
    # ======================================================
    created = 0

    for data in receipts:
        create_payment_entry(data)
        created += 1

    frappe.msgprint(
        f"✅ <b>{created}</b> Receipt Payment Entries created successfully."
    )


# ======================================================
# ✅ CREATE PAYMENT ENTRY
# ======================================================
def create_payment_entry(data):

    customer = frappe.db.get_value(
        "Customer",
        {"customer_name": data["customer_name"]},
        "name"
    )

    paid_to_account = f"{data['bank']} - CT"

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.party_type = "Customer"
    pe.party = customer
    pe.posting_date = data["date"]

    pe.paid_amount = data["amount"]
    pe.received_amount = data["amount"]

    pe.source_exchange_rate = 1
    pe.target_exchange_rate = 1

    pe.paid_to = paid_to_account
    pe.paid_to_account_currency = frappe.get_cached_value(
        "Account", paid_to_account, "account_currency"
    )

    pe.reference_no = data["reference_no"]
    pe.reference_date = data["reference_date"]
    pe.remarks = data["remarks"]

    pe.insert(ignore_permissions=True)

