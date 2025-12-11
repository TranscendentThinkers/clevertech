import frappe


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": "Purchase Order", "fieldname": "purchase_order", "fieldtype": "Link", "options": "Purchase Order", "width": 150},
        {"label": "PO Date", "fieldname": "po_date", "fieldtype": "Date", "width": 100},
        {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 150},
        {"label": "Supplier Name", "fieldname": "supplier_name", "fieldtype": "Data", "width": 180},
        {"label": "Item Code", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 120},
        {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 180},
        {"label": "PO Qty", "fieldname": "po_qty", "fieldtype": "Float", "width": 90},
        {"label": "Purchase Receipt", "fieldname": "purchase_receipt", "fieldtype": "Link", "options": "Purchase Receipt", "width": 150},
        {"label": "Received Qty", "fieldname": "received_qty", "fieldtype": "Float", "width": 110},
        {"label": "Order Status", "fieldname": "order_status", "fieldtype": "Data", "width": 160},
    ]


def get_data(filters):
    conditions = []

    if filters.get("supplier"):
        conditions.append("po.supplier = %(supplier)s")

    if filters.get("purchase_receipt"):
        conditions.append("pr.name = %(purchase_receipt)s")

    condition_str = ""
    if conditions:
        condition_str = " AND " + " AND ".join(conditions)

    query = f"""
        SELECT
            po.name AS purchase_order,
            po.transaction_date AS po_date,
            po.supplier,
            sup.supplier_name,
            poi.item_code,
            poi.item_name,
            poi.qty AS po_qty,
            MAX(pr.name) AS purchase_receipt,
            IFNULL(SUM(pri.qty), 0) AS received_qty
        FROM `tabPurchase Order` po
        INNER JOIN `tabPurchase Order Item` poi ON poi.parent = po.name
        LEFT JOIN `tabSupplier` sup ON sup.name = po.supplier
        LEFT JOIN `tabPurchase Receipt Item` pri
            ON pri.purchase_order = po.name
            AND pri.purchase_order_item = poi.name
        LEFT JOIN `tabPurchase Receipt` pr
            ON pr.name = pri.parent
            AND pr.docstatus = 1
        WHERE po.docstatus = 1
        {condition_str}
        GROUP BY poi.name
        ORDER BY po.transaction_date DESC
    """

    rows = frappe.db.sql(query, filters, as_dict=1)

    result = []
    for row in rows:
        if row.received_qty == 0:
            row.order_status = "Pending"
        elif row.received_qty >= row.po_qty:
            row.order_status = "Completed"
        else:
            row.order_status = "Partially Completed"

        if filters.get("order_status") and row.order_status != filters.get("order_status"):
            continue

        result.append(row)

    return result

