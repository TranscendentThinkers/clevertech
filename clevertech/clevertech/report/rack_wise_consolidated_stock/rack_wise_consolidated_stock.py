import frappe

def execute(filters=None):
    """
    Returns columns and tree-structured data rows.
    Required filter: warehouse (parent group or a warehouse)
    Optional filter: item_code
    """
    filters = filters or {}
    # require warehouse filter for tree parent
    parent_wh = filters.get("warehouse")
#    if not parent_wh:
#        frappe.throw("Please select a Warehouse (group) in the filter.")

    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    # "name" and "parent" are hidden fields used by frappe to build the tree
    return [
        {"label": "Item Code", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 450},
        {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 450},
        {"label": "Warehouse", "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 150},
        {"label": "Actual Qty", "fieldname": "actual_qty", "fieldtype": "Float", "width": 120},
        {"label": "parent", "fieldname": "parent", "hidden": 1},
        {"label": "name", "fieldname": "name", "hidden": 1}
    ]


def get_data(filters):
    parent_wh = filters.get("warehouse")
    if not parent_wh:
        frappe.throw("Please select a parent Warehouse (Group).")

    child_warehouses = get_relevant_warehouses(filters)

    # 1) Get child warehouses (direct children only)
#    child_warehouses = frappe.get_all(
#       "Warehouse",
#       filters={"parent_warehouse": parent_wh, "is_group": 0},
#       pluck="name"
#   )

    # If none, and parent itself is leaf, include parent
    if not child_warehouses:
        wh_doc = frappe.get_doc("Warehouse", parent_wh)
        if not wh_doc.is_group:
            child_warehouses = [parent_wh]
        else:
            return []

    wh_list_sql = ", ".join(["'%s'" % w.replace("'", "\\'") for w in child_warehouses])

    # Optional item filter
    item_cond = ""
    if filters.get("item_code"):
        item_cond = "AND b.item_code = '{}'".format(filters["item_code"].replace("'", "\\'"))

    # 2) Fetch non-zero stock
    bin_rows = frappe.db.sql(f"""
        SELECT b.item_code,
               b.warehouse,
               SUM(b.actual_qty) AS qty
        FROM `tabBin` b
        WHERE b.warehouse IN ({wh_list_sql})
        {item_cond}
        GROUP BY b.item_code, b.warehouse
        HAVING SUM(b.actual_qty) != 0
        ORDER BY b.item_code, b.warehouse
    """, as_dict=True)

    if not bin_rows:
        return []

    # 3) Aggregate totals per item
    item_totals = {}
    children_map = {}

    for r in bin_rows:
        item = r.item_code
        wh = r.warehouse
        qty = r.qty

        item_totals[item] = item_totals.get(item, 0) + qty

        children_map.setdefault(item, []).append({
            "indent": 1,
            "is_group": 0,
            "item_code": item,
            "warehouse": wh,
            "actual_qty": qty,
        })

    # 3B) Fetch item names ONCE (optimization)
    item_list = list(item_totals.keys())
    item_names = {
        d.name: d.item_name
        for d in frappe.get_all(
            "Item",
            filters={"name": ["in", item_list]},
            fields=["name", "item_name"]
        )
    }

    # Inject item_name into children
    for item, child_rows in children_map.items():
        for c in child_rows:
            c["item_name"] = item_names.get(item)

    # 4) Build final rows (parent then children)
    rows = []
    for item, total_qty in item_totals.items():

        # parent row
        rows.append({
            "indent": 0,
            "is_group": 1,
            "item_code": item,
            "item_name": item_names.get(item),
            "warehouse": parent_wh,
            "actual_qty": total_qty
        })

        # child rows
        rows.extend(children_map[item])

    return rows


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
