import difflib

import frappe
import pandas as pd
from frappe.utils import getdate


# =========================================================
# FILE LOADER
# =========================================================

def _load_receipt_df(file_url):
    file_doc = frappe.get_doc("File", {"file_url": file_url})
    return pd.read_excel(file_doc.get_full_path())


# =========================================================
# PARSER — splits rows into receipt blocks
# Each block has an `issues` list; empty = can be imported.
# =========================================================

def _parse_receipt_blocks(df):
    """
    Row types in the Receipt Excel:
      1. Date + Credit     → new receipt block
      2. "new ref" row     → sets reference_no
      3. "bank ..." row    → sets bank account
      4. Remarks row       → finalizes block (text len > 5, anything else)
    """
    blocks = []
    current = None

    def flush():
        if not current:
            return
        issues = []
        if not current["customer"]:
            issues.append(f"Customer not found: {current['customer_name']}")
        if not current["reference_no"]:
            issues.append(f"Missing reference no")
        if not current["bank_account"]:
            bank_label = current["bank_name"] or "not identified"
            issues.append(f"Bank account not found: {bank_label}")
        if current["amount"] <= 0:
            issues.append("Amount is zero")
        current["issues"] = issues
        blocks.append(dict(current))

    for _, row in df.iterrows():
        date        = row.get("Date")
        particulars = row.get("Particulars")
        ref_value   = row.get("Unnamed: 2")
        credit      = row.get("Credit")

        try:
            # ---- New receipt block ----
            if pd.notna(date) and pd.notna(credit):
                flush()
                customer_name = str(particulars).strip() if pd.notna(particulars) else ""
                customer = frappe.db.get_value("Customer", {"customer_name": customer_name}, "name")
                current = {
                    "date":          getdate(date),
                    "customer_name": customer_name,
                    "customer":      customer,
                    "amount":        float(credit),
                    "bank_name":     None,
                    "bank_account":  None,
                    "reference_no":  None,
                    "voucher_no":    None,
                    "remarks":       "",
                    "issues":        [],
                }
                continue

            if not current:
                continue

            # ---- Reference row ----
            if isinstance(particulars, str) and particulars.strip().lower() == "new ref":
                if pd.notna(ref_value):
                    current["reference_no"] = str(ref_value).strip()
                continue

            # ---- Bank row ----
            if isinstance(particulars, str) and "bank" in particulars.lower():
                bank_name = particulars.strip()
                current["bank_name"] = bank_name
                account_name = f"{bank_name} - CT"
                if frappe.db.exists("Account", account_name):
                    current["bank_account"] = account_name
                continue

            # ---- Remarks / finalize row ----
            if isinstance(particulars, str) and len(particulars.strip()) > 5:
                current["remarks"] = particulars.strip()
                flush()
                current = None

        except Exception:
            pass

    flush()
    return blocks


# =========================================================
# API 1 — VALIDATE  (pre-flight, no PEs created)
# =========================================================

@frappe.whitelist()
def validate_receipt_excel(file_url):
    """
    Returns:
    {
        total, matched, skipped,
        unresolved: [{name, issue_type, context, suggestions}]
    }
    """
    df = _load_receipt_df(file_url)
    blocks = _parse_receipt_blocks(df)

    matched = sum(1 for b in blocks if not b["issues"])
    skipped = len(blocks) - matched

    # Build deduplicated unresolved list
    seen = set()
    unresolved_list = []
    for b in blocks:
        for issue in b["issues"]:
            key = (b["customer_name"], issue)
            if key in seen:
                continue
            seen.add(key)
            unresolved_list.append({
                "name":       b["customer_name"],
                "issue_type": issue,
                "context":    f"₹{b['amount']:,.2f} on {b['date']}",
                "suggestions": [],
            })

    # Fuzzy suggestions — customers only (for "Customer not found" issues)
    missing_customer_names = list({
        b["customer_name"] for b in blocks if not b["customer"]
    })
    if missing_customer_names:
        all_customers = frappe.db.sql_list(
            "SELECT customer_name FROM `tabCustomer` WHERE disabled = 0"
        )
        sugg_map = {
            name: difflib.get_close_matches(name, all_customers, n=3, cutoff=0.6)
            for name in missing_customer_names
        }
        for u in unresolved_list:
            if "Customer not found" in u["issue_type"]:
                u["suggestions"] = sugg_map.get(u["name"], [])

    return {
        "total":      len(blocks),
        "matched":    matched,
        "skipped":    skipped,
        "unresolved": unresolved_list,
    }


# =========================================================
# API 2 — IMPORT  (creates PEs for matched blocks only)
# =========================================================

@frappe.whitelist()
def import_receipt_excel(file_url):
    df = _load_receipt_df(file_url)
    blocks = _parse_receipt_blocks(df)

    created   = 0
    skipped   = 0
    duplicate = 0

    for b in blocks:
        if b["issues"]:
            skipped += 1
            continue
        # Duplicate check — reference_no is the bank transaction identifier
        ref = b["reference_no"]
        if ref and frappe.db.exists("Payment Entry", {"reference_no": ref, "payment_type": "Receive"}):
            duplicate += 1
            continue
        try:
            _create_receipt_entry(b)
            created += 1
        except Exception:
            skipped += 1

    parts = [f"✅ {created} created"]
    if skipped:
        parts.append(f"⚠️ {skipped} skipped (unresolved / missing data)")
    if duplicate:
        parts.append(f"🔁 {duplicate} duplicate (reference no already exists)")

    return {"created": created, "skipped": skipped, "duplicate": duplicate, "message": " | ".join(parts)}


# =========================================================
# CREATOR
# =========================================================

def _create_receipt_entry(data):
    pe = frappe.new_doc("Payment Entry")
    pe.payment_type          = "Receive"
    pe.party_type            = "Customer"
    pe.party                 = data["customer"]
    pe.posting_date          = data["date"]
    pe.paid_amount           = data["amount"]
    pe.received_amount       = data["amount"]
    pe.source_exchange_rate  = 1
    pe.target_exchange_rate  = 1
    pe.paid_to               = data["bank_account"]
    pe.paid_to_account_currency = frappe.get_cached_value(
        "Account", data["bank_account"], "account_currency"
    )
    pe.reference_no          = data["reference_no"]
    pe.reference_date        = data["date"]
    pe.remarks               = data["remarks"]
    pe.insert(ignore_permissions=True)
