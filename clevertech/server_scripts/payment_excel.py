import frappe
from openpyxl import load_workbook
from frappe.utils import getdate
import xlrd
import os
import re

# =========================================================
# GLOBAL ERROR COLLECTOR
# =========================================================
GLOBAL_ERRORS = {
    "missing_accounts": set(),
    "missing_suppliers": set(),
    "format_errors": []
}

# =========================================================
# HELPERS
# =========================================================
def normalize_name(name):
    return name.lower().replace(".", "").replace(",", "").replace(" ", " ").strip()

def find_supplier_fuzzy(name):
    if not name:
        return None
    norm = normalize_name(name)
    suppliers = frappe.get_all("Supplier", fields=["name", "supplier_name"])
    for s in suppliers:
        if normalize_name(s.supplier_name) == norm:
            return s.name
    return None

def parse_amount(val):
    """Parse numeric or string amounts like '11246.00 Cr' → 11246.0"""
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return float(val)
    # Strip text like ' Cr', ' Dr' and commas
    cleaned = re.sub(r'[^\d.]', '', str(val).replace(",", ""))
    try:
        return float(cleaned)
    except ValueError:
        return 0

# =========================================================
# MAIN API
# =========================================================
@frappe.whitelist()
def upload_payment_excel(file_url):
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
    # CONFIG
    # =========================================================
    COMPANY = frappe.defaults.get_user_default("Company")
    MODE_OF_PAYMENT = "NEFT"
    PAID_TO_ACCOUNT = "Creditors - CT"  # payable

    # =========================================================
    # COLUMN INDICES — adjusted to match actual Excel layout:
    # Col 0: Date | Col 1: Particulars | Col 4: Vch Type
    # Col 5: Vch No. | Col 6: Debit Amount | Col 7: Credit Amount
    # =========================================================
    COL_DATE        = 0
    COL_PARTICULARS = 1
    COL_VCH_NO      = 5
    COL_DEBIT       = 6
    COL_CREDIT      = 7

    # =========================================================
    # PROCESSING
    # =========================================================
    created = 0
    current_doc = None

    def flush_payment():
        nonlocal created
        if not current_doc:
            return

        if not current_doc.get("party"):
            GLOBAL_ERRORS["missing_suppliers"].add(current_doc.get("party_name", ""))
            return

        if current_doc.get("paid_amount", 0) <= 0:
            GLOBAL_ERRORS["format_errors"].append(
                f"Voucher {current_doc.get('voucher_no')} : Paid amount is zero"
            )
            return

        if not current_doc.get("paid_from"):
            GLOBAL_ERRORS["format_errors"].append(
                f"Voucher {current_doc.get('voucher_no')} : Paid From account not found"
            )
            return

        # ---------------- CREATE PAYMENT ENTRY ----------------
        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Pay"
        pe.posting_date = current_doc["date"]
        pe.company = COMPANY
        pe.mode_of_payment = MODE_OF_PAYMENT
        pe.party_type = "Supplier"
        pe.party = current_doc["party"]
        pe.party_name = current_doc["party_name"]
        pe.paid_from = current_doc["paid_from"]
        pe.paid_to = PAID_TO_ACCOUNT
        pe.paid_amount = current_doc["paid_amount"]
        pe.received_amount = current_doc["paid_amount"]
        pe.reference_no = current_doc.get("reference_no")
        pe.reference_date = current_doc.get("date")
        pe.custom_tally_voucher_no = current_doc.get("voucher_no")
        pe.remarks = current_doc.get("remarks")
        pe.docstatus = 0  # Draft
        pe.insert(ignore_permissions=True)
        created += 1

    # -------- PROCESS SOURCE (START FROM ROW 8, index 7) --------
    for idx, r in enumerate(rows[7:], start=8):
        try:
            # Guard: skip rows that don't have enough columns
            if len(r) < 8:
                continue

            date_val    = r[COL_DATE]
            particulars = r[COL_PARTICULARS]
            voucher_no  = r[COL_VCH_NO]
            debit       = parse_amount(r[COL_DEBIT])
            credit      = parse_amount(r[COL_CREDIT])

            text = str(particulars).strip() if particulars else ""

            # -------- New Payment Voucher (row has a date) --------
            if date_val:
                flush_payment()
                current_doc = {
                    "date": getdate(date_val),
                    "party_name": text,
                    "party": None,
                    "reference_no": "",
                    "remarks": "",
                    "voucher_no": voucher_no,
                    "paid_from": None,
                    "paid_amount": 0
                }

                # fuzzy supplier match
                sup = find_supplier_fuzzy(text)
                if sup:
                    current_doc["party"] = sup
                else:
                    GLOBAL_ERRORS["missing_suppliers"].add(text)
                continue

            if not current_doc:
                continue

            # -------- CREDIT → Bank/Cash (Paid From) --------
            if credit and text:
                acc = frappe.db.get_value("Account", {"account_name": text}, "name")
                if acc:
                    current_doc["paid_from"] = acc
                    current_doc["paid_amount"] = credit
                else:
                    GLOBAL_ERRORS["missing_accounts"].add(text)

            # -------- DEBIT → Alternative amount detection --------
            elif debit and current_doc["paid_amount"] == 0:
                current_doc["paid_amount"] = debit

            # -------- REMARKS LOGIC --------
            if text and not date_val and not debit and not credit:
                low = text.lower()

                # exclude supplier row
                if normalize_name(text) == normalize_name(current_doc.get("party_name", "")):
                    continue

                # exclude bank/account row
                acc_check = frappe.db.get_value("Account", {"account_name": text}, "name")
                if acc_check:
                    continue

                # exclude reference/helper rows
                EXCLUDE_PREFIX = [
                    "agst ref", "against ref", "new ref", "reference", "ref", "bill ref"
                ]
                if any(low.startswith(p) for p in EXCLUDE_PREFIX):
                    continue

                # include only real narration keywords
                INCLUDE_KEYWORDS = [
                    "being", "neft", "imps", "rtgs", "upi", "cms",
                    "flight", "ticket", "pnr", "booking", "travel",
                    "payment", "transfer", "air india", "indigo", "spicejet"
                ]
                if not any(k in low for k in INCLUDE_KEYWORDS):
                    continue

                # valid remark
                if current_doc["remarks"]:
                    current_doc["remarks"] += " | "
                current_doc["remarks"] += text

        except Exception as e:
            GLOBAL_ERRORS["format_errors"].append(f"Row {idx}: {str(e)}")
            continue

    # flush last record
    flush_payment()

    # =========================================================
    # GLOBAL ERROR REPORTING
    # =========================================================
    if (GLOBAL_ERRORS["missing_accounts"] or
        GLOBAL_ERRORS["missing_suppliers"] or
        GLOBAL_ERRORS["format_errors"]):

        msg = "❌ PAYMENT EXCEL VALIDATION FAILED:\n\n"

        if GLOBAL_ERRORS["missing_accounts"]:
            msg += "MISSING ACCOUNTS:\n"
            for a in sorted(GLOBAL_ERRORS["missing_accounts"]):
                msg += f"  - {a}\n"

        if GLOBAL_ERRORS["missing_suppliers"]:
            msg += "\nMISSING SUPPLIERS:\n"
            for s in sorted(GLOBAL_ERRORS["missing_suppliers"]):
                msg += f"  - {s}\n"

        if GLOBAL_ERRORS["format_errors"]:
            msg += "\nFORMAT ERRORS:\n"
            for e in GLOBAL_ERRORS["format_errors"]:
                msg += f"  - {e}\n"

        frappe.log_error(message=msg, title="Payment Entry Excel Validation Errors")
        frappe.throw(msg)

    return f"✅ {created} Payment Entries created successfully in Draft status"
