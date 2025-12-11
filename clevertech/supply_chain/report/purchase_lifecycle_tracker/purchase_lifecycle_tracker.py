import frappe
def execute(filters=None):
    filters = filters or {}

    columns = get_columns(filters)
    data = get_bom_items(filters)

    if filters.get("show_mr"):
        apply_mr(data)

    if filters.get("show_rfq"):
        apply_rfq(data)

    if filters.get("show_sq"):
        apply_sq(data)

    if filters.get("show_po"):
        apply_po(data)

    if filters.get("show_pr"):
        apply_pr(data)

    return columns, data
def get_columns(filters):
    columns = [
        {"label": "BOM", "fieldname": "bom", "fieldtype": "Link", "options": "BOM", "width": 250},
        {"label": "Project", "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 130},
        {"label": "Item Code", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
        {"label": "Item Name", "fieldname": "item_name", "width": 300},
        {"label": "BOM Qty", "fieldname": "bom_qty", "fieldtype": "Float", "width": 90},
    ]

    if filters.get("show_mr"):
        columns += [
            {"label": "MR Qty", "fieldname": "mr_qty", "fieldtype": "Float", "width": 90},
            {"label": "MR Status", "fieldname": "mr_status", "width": 110},
        ]

    if filters.get("show_rfq"):
        columns += [
            {"label": "RFQ Qty", "fieldname": "rfq_qty", "fieldtype": "Float", "width": 90},
            {"label": "RFQ Status", "fieldname": "rfq_status", "width": 110},
        ]

    if filters.get("show_sq"):
        columns += [
            {"label": "SQ Qty", "fieldname": "sq_qty", "fieldtype": "Float"},
            {"label": "SQ Status", "fieldname": "sq_status"},
        ]

    if filters.get("show_po"):
        columns += [
            {"label": "PO Qty", "fieldname": "po_qty", "fieldtype": "Float"},
            {"label": "PO Status", "fieldname": "po_status"},
        ]

    if filters.get("show_pr"):
        columns += [
            {"label": "PR Qty", "fieldname": "pr_qty", "fieldtype": "Float"},
            {"label": "PR Status", "fieldname": "pr_status"},
        ]

    return columns
def get_bom_items(filters):
    conditions = [
        "bom.docstatus = 1",
        "bom.is_active = 1",
        "bom.is_default = 1"
    ]

    if filters.get("bom"):
        conditions.append("bom.name = %(bom)s")
    if filters.get("project"):
        conditions.append("bom.project = %(project)s")

    return frappe.db.sql(f"""
        SELECT
            bom.name AS bom,
            bom.project AS project,
            bo.item_code,
            bo.item_name,
            bo.qty AS bom_qty
        FROM `tabBOM` bom
        INNER JOIN `tabBOM Item` bo
            ON bo.parent = bom.name
        WHERE {" AND ".join(conditions)}
    """, filters, as_dict=True)
def apply_mr(rows):
    mr_data = frappe.db.sql("""
        SELECT
            mri.bom_no,
            mri.item_code,
            SUM(mri.qty) AS qty
        FROM `tabMaterial Request Item` mri
        INNER JOIN `tabMaterial Request` mr
            ON mr.name = mri.parent
        WHERE mr.docstatus = 1
          AND mr.material_request_type = 'Purchase'
        GROUP BY mri.bom_no, mri.item_code
    """, as_dict=True)

    mr_map = {(d.bom_no, d.item_code): d.qty for d in mr_data}

    for r in rows:
        r.mr_qty = mr_map.get((r.bom, r.item_code), 0)
        r.mr_status = get_status(r.bom_qty, r.mr_qty)
def apply_rfq(rows):
    rfq_map = get_qty_map(
        "tabRequest for Quotation Item",
        "material_request",
        "item_code",
        "qty"
    )

    for r in rows:
        base_qty = r.mr_qty or 0
        r.rfq_qty = rfq_map.get((None, r.item_code), 0)
        r.rfq_status = get_status(base_qty, r.rfq_qty)
def apply_sq(rows):
    sq_map = get_qty_map(
        "tabSupplier Quotation Item",
        "material_request",
        "item_code",
        "qty"
    )

    for r in rows:
        r.sq_qty = sq_map.get(
            (r.material_request, r.item_code), 0
        )
        r.sq_status = get_status(r.mr_qty, r.sq_qty)
def apply_po(rows):
    po_map = get_qty_map(
        "tabPurchase Order Item",
        "material_request",
        "item_code",
        "qty"
    )

    for r in rows:
        r.po_qty = po_map.get(
            (r.material_request, r.item_code), 0
        )
        r.po_status = get_status(r.mr_qty, r.po_qty)
def apply_pr(rows):
    pr_map = get_qty_map(
        "tabPurchase Receipt Item",
        "material_request",
        "item_code",
        "qty"
    )

    for r in rows:
        r.pr_qty = pr_map.get(
            (r.material_request, r.item_code), 0
        )
        r.pr_status = get_status(r.mr_qty, r.pr_qty)
def get_qty_map(table, group_field, item_field, qty_field):
    data = frappe.db.sql(f"""
        SELECT
            {group_field},
            {item_field},
            SUM({qty_field}) AS qty
        FROM `{table}`
        WHERE docstatus = 1
        GROUP BY {group_field}, {item_field}
    """, as_dict=True)

    return {
        (d[group_field], d[item_field]): d.qty
        for d in data
    }


def get_status(base_qty, flow_qty):
    if not flow_qty:
        return "Pending"
    if flow_qty < base_qty:
        return "Partial"
    if flow_qty > base_qty:
        return "Excess Requested"
    return "Completed"

