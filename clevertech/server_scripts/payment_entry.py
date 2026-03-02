import frappe
import pandas as pd


@frappe.whitelist()
def import_receipt_excel(file_url):

    file_path = frappe.get_site_path(
        "private", "files", file_url.split("/")[-1]
    )

    df = pd.read_excel(file_path)

    receipts = []  # store valid rows for second pass

    # 🔴 GLOBAL ERROR COLLECTORS
    missing_customers = set()
    missing_accounts = set()
    missing_reference = set()

    current_receipt = None

    # ======================================================
    # 🔍 PASS 1 → ONLY VALIDATION (NO CREATION)
    # ======================================================
    for idx, row in df.iterrows():

        # safe column access
        date = row.iloc[0] if len(row) > 0 else None
        particulars = row.iloc[1] if len(row) > 1 else None
        ref_value = row.iloc[2] if len(row) > 2 else None
        credit = row.iloc[9] if len(row) > 9 else None

        # 1️⃣ MAIN RECEIPT ROW
        if pd.notna(date) and pd.notna(credit):

            current_receipt = {
                "date": date,
                "customer_name": str(particulars).strip(),
                "amount": credit,
                "bank": None,
                "remarks": "",
                "reference_no": None,
                "reference_date": date
            }
            continue

        if not current_receipt:
            continue

        # 2️⃣ REFERENCE ROW
        if isinstance(particulars, str) and particulars.strip().lower() == "new ref":
            if pd.notna(ref_value):
                current_receipt["reference_no"] = str(ref_value).strip()
            continue

        # 3️⃣ BANK ROW
        if isinstance(particulars, str) and "bank" in particulars.lower():
            current_receipt["bank"] = particulars.strip()
            continue

        # 4️⃣ REMARKS ROW → FINALIZE ONE RECEIPT
        if isinstance(particulars, str) and len(particulars.strip()) > 10:
            current_receipt["remarks"] = particulars.strip()

            # ---------------- VALIDATIONS ----------------
            customer = frappe.db.get_value(
                "Customer",
                {"customer_name": current_receipt["customer_name"]},
                "name"
            )
            if not customer:
                missing_customers.add(current_receipt["customer_name"])

            if not current_receipt["reference_no"]:
                missing_reference.add(current_receipt["customer_name"])

            if current_receipt["bank"]:
                account = f"{current_receipt['bank']} - CT"
                if not frappe.db.exists("Account", account):
                    missing_accounts.add(account)
            else:
                missing_accounts.add("Bank not identified")

            receipts.append(current_receipt)
            current_receipt = None

    # ======================================================
    # ❌ STOP IF ANY ERROR FOUND
    # ======================================================
    if missing_customers or missing_accounts or missing_reference:

        msg = "<b>❌ Receipt Excel Validation Failed</b><br><br>"

        if missing_customers:
            msg += "<b>Missing Customers:</b><br>"
            for c in sorted(missing_customers):
                msg += f"- {c}<br>"

        if missing_accounts:
            msg += "<br><b>Missing Bank Accounts:</b><br>"
            for a in sorted(missing_accounts):
                msg += f"- {a}<br>"

        if missing_reference:
            msg += "<br><b>Missing Reference No for Customers:</b><br>"
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
# CREATE PAYMENT ENTRY (CLEAN & SAFE)
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

