import frappe

def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": "Purchase Receipt", "fieldname": "pr_name", "fieldtype": "Link", "options": "Purchase Receipt", "width": 160},
        {"label": "Posting Date", "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 140},
        {"label": "Supplier Name", "fieldname": "supplier_name", "fieldtype": "Data", "width": 180},
        {"label": "Item Code", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140,"show_preview": 0},
        {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "options": "Item", "width": 140},
        {"label": "Qty", "fieldname": "qty", "fieldtype": "Float", "width": 80},
        {"label": "Requires Inspection", "fieldname": "requires_inspection", "fieldtype": "Data", "width": 120},
        {"label": "Quality Inspection", "fieldname": "qi_name", "fieldtype": "Link", "options": "Quality Inspection", "width": 170},
        {"label": "Quality Status", "fieldname": "quality_status", "fieldtype": "Data", "width": 120},
    ]

    conditions = []
    params = {}

    if filters.get("purchase_receipt"):
        conditions.append("pr.name = %(purchase_receipt)s")
        params["purchase_receipt"] = filters["purchase_receipt"]

    if filters.get("quality_inspection"):
        conditions.append("qi.name = %(quality_inspection)s")
        params["quality_inspection"] = filters["quality_inspection"]

    if filters.get("item_code"):
        conditions.append("pri.item_code = %(item_code)s")
        params["item_code"] = filters["item_code"]

    where_clause = " AND ".join(conditions)
    if where_clause:
        where_clause = "AND " + where_clause

    query = f"""
        SELECT
            pr.name AS pr_name,
            pr.posting_date,
            pr.supplier,
            sup.supplier_name,
            pri.item_code,
            pri.item_name,
            pri.qty,
            i.inspection_required_before_purchase AS requires_inspection,
            qi.name AS qi_name,
            pr.custom_quality_status AS quality_status
        FROM `tabPurchase Receipt` pr
        JOIN `tabPurchase Receipt Item` pri ON pri.parent = pr.name
        JOIN `tabItem` i ON i.name = pri.item_code
        LEFT JOIN `tabQuality Inspection` qi
            ON qi.reference_type = 'Purchase Receipt'
            AND qi.reference_name = pr.name
            AND qi.item_code = pri.item_code
            AND qi.docstatus = 1
        LEFT JOIN `tabSupplier` sup ON sup.name = pr.supplier
        WHERE pr.docstatus = 1
        {where_clause}
        ORDER BY pr.posting_date DESC, pr.name, pri.idx
    """

    raw = frappe.db.sql(query, params, as_dict=True)

    # ---- FORMAT FOR ONE-TO-MANY VISUAL GROUPING ----
    data = []
    last_pr = None

    for row in raw:
        if row.pr_name == last_pr:
            # Blank out repeated PR fields
            row.pr_name = ""
            row.posting_date = ""
            row.supplier = ""
            row.supplier_name = ""
            row.quality_status = ""   # Optional: blank this too
        else:
            last_pr = row.pr_name

        # Convert check to Yes/No
        row.requires_inspection = "Yes" if row.requires_inspection else "No"

        data.append(row)

    return columns, data

