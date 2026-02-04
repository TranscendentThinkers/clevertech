import frappe


def execute(filters=None):
    filters = filters or {}
    columns, supplier_map = get_columns(filters)
    data = get_data(filters, supplier_map)
    return columns, data


def get_columns(filters):

    comparison = filters.get("comparison")

    columns = [
        {"label": "Item", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
        {"label": "Qty", "fieldname": "qty", "fieldtype": "Float", "width": 80},
        {"label": "UOM", "fieldname": "uom", "fieldtype": "Data", "width": 80},
    ]

    suppliers = frappe.get_all(
        "Supplier Quotation Comparison Item",
        filters={
            "parent": comparison,
            "parenttype": "Supplier Quotation Comparison"
        },
        fields=["supplier"],
        group_by="supplier"
    )

    supplier_map = {}  # supplier_code -> supplier_name

    for s in suppliers:
        supplier_code = s.supplier
        supplier_name = frappe.db.get_value("Supplier", supplier_code, "supplier_name") or supplier_code

        supplier_map[supplier_code] = supplier_name

        field_prefix = frappe.scrub(supplier_code)

        columns.append({
            "label": f"{supplier_name} Rate",
            "fieldname": f"{field_prefix}_rate",
            "fieldtype": "Currency",
            "width": 120
        })

        columns.append({
            "label": f"{supplier_name} Amount",
            "fieldname": f"{field_prefix}_amount",
            "fieldtype": "Currency",
            "width": 120
        })

    return columns, supplier_map


def get_data(filters, supplier_map):

    comparison = filters.get("comparison")

    rows = frappe.get_all(
        "Supplier Quotation Comparison Item",
        filters={
            "parent": comparison,
            "parenttype": "Supplier Quotation Comparison"
        },
        fields=[
            "item_code",
            "qty",
            "uom",
            "supplier",
            "rate",
            "amount"
        ]
    )

    result = {}

    for r in rows:
        key = (r.item_code, r.qty, r.uom)

        if key not in result:
            result[key] = {
                "item_code": r.item_code,
                "qty": r.qty,
                "uom": r.uom
            }

        field_prefix = frappe.scrub(r.supplier)

        result[key][f"{field_prefix}_rate"] = r.rate
        result[key][f"{field_prefix}_amount"] = r.amount

    return list(result.values())

