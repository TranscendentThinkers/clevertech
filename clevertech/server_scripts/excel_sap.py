import frappe
from openpyxl import load_workbook
from frappe.utils import getdate
import xlrd
import os

# =========================================================
# =========================================================
# GLOBAL ERROR COLLECTOR
# =========================================================

GLOBAL_ERRORS = {
    "missing_accounts": set(),
    "missing_suppliers": set(),
    "unbalanced_journals": [],
    "format_errors": []
}

# =========================================================
# MAIN API
# =========================================================

@frappe.whitelist()
def upload_sap_journal(file_url):
    file_doc = frappe.get_doc("File", {"file_url": file_url})
    file_path = file_doc.get_full_path()

    # =============================
    # FILE FORMAT AUTO DETECTION
    # =============================
    ext = os.path.splitext(file_path)[1].lower()
    rows = []

    if ext == ".xlsx":
        wb = load_workbook(file_path, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))

    elif ext == ".xls":
        book = xlrd.open_workbook(file_path)
        sheet = book.sheet_by_index(0)
        for r in range(sheet.nrows):
            rows.append(sheet.row_values(r))

    else:
        frappe.throw("❌ Unsupported file format. Upload .xls or .xlsx only.")

    # =========================================================
    # HEADER AUTO DETECTION
    # =========================================================

    def normalize(text):
        return str(text).lower().replace(" ", "").replace("_", "").strip()

    def find_header_row(rows):
        for idx, row in enumerate(rows):
            row_norm = [normalize(c) if c else "" for c in row]

            has_date = any("date" in c for c in row_norm)
            has_particular = any("particular" in c for c in row_norm)
            has_debit = any("debit" in c for c in row_norm)
            has_credit = any("credit" in c for c in row_norm)

            if has_date and has_particular and has_debit and has_credit:
                return idx
        return None

    header_row_index = find_header_row(rows)
    if header_row_index is None:
        frappe.throw("❌ Could not detect header row. Invalid SAP format.")

    headers_raw = rows[header_row_index]
    headers = [normalize(h) if h else "" for h in headers_raw]

    # =========================================================
    # COLUMN AUTO DETECTION
    # =========================================================

    def find_col(keywords):
        for i, h in enumerate(headers):
            for k in keywords:
                if k in h:
                    return i
        return None

    COL_DATE = find_col(["date"])
    COL_PARTICULAR = find_col(["particular"])
    COL_DEBIT = find_col(["debit"])
    COL_CREDIT = find_col(["credit"])
    COL_VOUCHER = find_col(["vchno", "voucher", "documentno", "docno"])

    missing = []
    if COL_DATE is None: missing.append("Date")
    if COL_PARTICULAR is None: missing.append("Particulars")
    if COL_DEBIT is None: missing.append("Debit")
    if COL_CREDIT is None: missing.append("Credit")
    if missing:
        frappe.throw(f"❌ Missing required columns in Excel: {', '.join(missing)}")

    DATA_START_ROW = header_row_index + 1

    # =========================================================
    # DATA PROCESSING
    # =========================================================

    created = 0
    current_entry = None
    accounts_buffer = []

    def safe(row, idx):
        if idx is None:
            return None
        if idx >= len(row):
            return None
        return row[idx]

    for i, r in enumerate(rows[DATA_START_ROW:], start=DATA_START_ROW+1):

        try:
            posting_date = safe(r, COL_DATE)
            particulars = safe(r, COL_PARTICULAR)
            voucher_no = safe(r, COL_VOUCHER)
            debit = safe(r, COL_DEBIT) or 0
            credit = safe(r, COL_CREDIT) or 0

            text = str(particulars).strip() if particulars else ""

            # -------------------------
            # New Journal Entry
            # -------------------------
            if posting_date:
                if current_entry and accounts_buffer:
                    err = validate_balance_soft(current_entry, accounts_buffer)
                    if not err:
                        create_journal_entry(current_entry, accounts_buffer)
                        created += 1

                current_entry = {
                    "posting_date": getdate(posting_date),
                    "voucher_no": str(voucher_no).strip() if voucher_no else None,
                    "title": text,
                    "remark": ""
                }
                accounts_buffer = []

            if not current_entry:
                continue

            # -------------------------
            # Narration Row
            # -------------------------
            if text and not debit and not credit:
                if current_entry["remark"]:
                    current_entry["remark"] += "\n"
                current_entry["remark"] += text
                continue

            # -------------------------
            # Accounting Row
            # -------------------------
            if not text:
                continue

            if not debit and not credit:
                continue

            account_data = resolve_account_or_supplier(text)
            if not account_data:
                continue

            accounts_buffer.append({
                "account": account_data["account"],
                "party_type": account_data.get("party_type"),
                "party": account_data.get("party"),
                "debit": float(debit or 0),
                "credit": float(credit or 0)
            })

        except Exception as e:
            GLOBAL_ERRORS["format_errors"].append(f"Row {i}: {str(e)}")

    # -------------------------
    # LAST ENTRY
    # -------------------------
    if current_entry and accounts_buffer:
        err = validate_balance_soft(current_entry, accounts_buffer)
        if not err:
            create_journal_entry(current_entry, accounts_buffer)
            created += 1

    # =========================================================
    # =========================================================
    # GLOBAL ERROR REPORTING
    # =========================================================

    if (GLOBAL_ERRORS["missing_accounts"] or GLOBAL_ERRORS["missing_suppliers"] 
        or GLOBAL_ERRORS["unbalanced_journals"] or GLOBAL_ERRORS["format_errors"]):

        msg = "❌ EXCEL FILE VALIDATION FAILED. Fix following issues and re-upload:\n\n"

        if GLOBAL_ERRORS["missing_accounts"]:
            msg += "MISSING ACCOUNTS:\n"
            for a in sorted(GLOBAL_ERRORS["missing_accounts"]):
                msg += f" - {a}\n"

        if GLOBAL_ERRORS["missing_suppliers"]:
            msg += "\nMISSING SUPPLIERS:\n"
            for s in sorted(GLOBAL_ERRORS["missing_suppliers"]):
                msg += f" - {s}\n"

        if GLOBAL_ERRORS["unbalanced_journals"]:
            msg += "\nUNBALANCED JOURNALS:\n"
            for e in GLOBAL_ERRORS["unbalanced_journals"]:
                msg += f" - {e}\n"

        if GLOBAL_ERRORS["format_errors"]:
            msg += "\nFORMAT ERRORS:\n"
            for e in GLOBAL_ERRORS["format_errors"]:
                msg += f" - {e}\n"

        frappe.log_error(message=msg, title="SAP Excel Full Validation Errors")
        frappe.throw(msg)

    return f"✅ {created} Journal Entries created successfully (Draft mode)"


# =========================================================
# VALIDATION LOGIC
# =========================================================

def validate_balance_soft(header, rows):
    total_debit = sum(r["debit"] for r in rows)
    total_credit = sum(r["credit"] for r in rows)

    if round(total_debit, 2) != round(total_credit, 2):
        GLOBAL_ERRORS["unbalanced_journals"].append(
            f"Voucher {header.get('voucher_no') or header.get('title')} | Dr={total_debit} Cr={total_credit} Diff={total_debit-total_credit}"
        )
        return True
    return False

# =========================================================
# ACCOUNT / SUPPLIER RESOLVER
# =========================================================

def resolve_account_or_supplier(name):
    # Account
    acc = frappe.db.get_value("Account", {"account_name": name}, "name")
    if acc:
        return {"account": acc}

    # Supplier
    sup = frappe.db.get_value("Supplier", {"supplier_name": name}, "name")
    if sup:
        payable = get_supplier_payable_account(sup)
        return {
            "account": payable,
            "party_type": "Supplier",
            "party": sup
        }

    # Collect globally
    if name:
        lname = name.lower()
        if "ltd" in lname or "private" in lname or "pvt" in lname or "limited" in lname:
            GLOBAL_ERRORS["missing_suppliers"].add(name)
        else:
            GLOBAL_ERRORS["missing_accounts"].add(name)

    return None

# =========================================================
# PAYABLE ACCOUNT FETCHER
# =========================================================

def get_supplier_payable_account(supplier):
    company = frappe.defaults.get_user_default("Company")

    try:
        payable = frappe.db.get_value(
            "Party Account",
            {
                "party": supplier,
                "company": company
            },
            "account"
        )
        if payable:
            return payable
    except Exception:
        pass

    payable = frappe.db.get_value("Company", company, "default_payable_account")
    if payable:
        return payable

    frappe.throw(f"❌ No payable account found for Supplier '{supplier}' in company '{company}'")


# =========================================================
# JOURNAL ENTRY CREATOR
# =========================================================

def create_journal_entry(header, rows):
    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.posting_date = header["posting_date"]
    je.company = frappe.defaults.get_user_default("Company")

    je.user_remark = header.get("remark") or header.get("title")
    je.custom_tally_voucher_no = header.get("voucher_no")

    je.docstatus = 0   # Draft

    for r in rows:
        je.append("accounts", {
            "account": r["account"],
            "party_type": r.get("party_type"),
            "party": r.get("party"),
            "debit_in_account_currency": r["debit"],
            "credit_in_account_currency": r["credit"]
        })

    je.insert(ignore_permissions=True)
