# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
import frappe

def execute(filters=None):
    filters = filters or {}
    columns = get_columns(filters)
    data = get_data(filters, columns)
    return columns, data


def get_columns(filters):
    # Fixed columns
    columns = [
        {"label": "Item Code", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
        {"label": "Total Available Stock", "fieldname": "total_stock", "fieldtype": "Float", "width": 120},
    ]

    # Dynamic warehouse columns
    warehouse_list = get_relevant_warehouses(filters)
    for wh in warehouse_list:
        columns.append({
            "label": wh,
            "fieldname": frappe.scrub(wh),
            "fieldtype": "Float",
            "width": 120
        })

    return columns


def get_data(filters, columns=None):
    warehouse_list = get_relevant_warehouses(filters)

    if not warehouse_list:
        return []

    # Build Bin query conditions
    conditions = []
    if filters.get("item_code"):
        conditions.append(f"b.item_code = '{filters['item_code']}'")
    if warehouse_list:
        wh_list = "', '".join([w.replace("'", "\\'") for w in warehouse_list])
        conditions.append(f"b.warehouse IN ('{wh_list}')")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Fetch non-zero stock data only
    bin_data = frappe.db.sql(f"""
        SELECT
            b.item_code,
            b.warehouse,
            SUM(b.actual_qty) AS actual_qty
        FROM `tabBin` b
        {where_clause}
        GROUP BY b.item_code, b.warehouse
        HAVING SUM(b.actual_qty) != 0
    """, as_dict=True)

    # Organize by item
    item_map = {}
    non_zero_warehouses = set()
    for d in bin_data:
        item_code = d.item_code
        wh = frappe.scrub(d.warehouse)
        qty = d.actual_qty or 0

        non_zero_warehouses.add(d.warehouse)

        if item_code not in item_map:
            item_map[item_code] = {"item_code": item_code, "total_stock": 0}
        item_map[item_code][wh] = qty
        item_map[item_code]["total_stock"] += qty

    # Adjust dynamic columns (skip warehouses with 0 qty globally)
    if columns is not None:
        # Remove old dynamic warehouse columns
        columns[:] = columns[:2]
        for wh in sorted(non_zero_warehouses):
            columns.append({
                "label": wh,
                "fieldname": frappe.scrub(wh),
                "fieldtype": "Float",
                "width": 120
            })

    return list(item_map.values())


def get_relevant_warehouses(filters):
    """
    Logic:
    - No warehouse filter → return all non-group warehouses.
    - If warehouse (group) selected → get all child warehouses (recursively if needed).
    """
    if not filters.get("warehouse"):
        return frappe.get_all("Warehouse", filters={"is_group": 0}, pluck="name")

    parent = filters.get("warehouse")
    # Recursive fetch (using lft/rgt for efficiency)
    parent_wh = frappe.db.get_value("Warehouse", parent, ["lft", "rgt"], as_dict=True)
    if parent_wh:
        return frappe.db.get_all(
            "Warehouse",
            filters={"lft": [">", parent_wh.lft], "rgt": ["<", parent_wh.rgt], "is_group": 0},
            pluck="name"
        )
