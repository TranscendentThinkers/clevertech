import frappe
from frappe import _
from frappe.utils import today, date_diff, getdate


def execute(filters=None):
    filters = filters or {}

    # Return empty if neither a project is selected nor show_all_projects is ticked
    if not filters.get("project") and not filters.get("show_all_projects"):
        return get_columns(), []

    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "label": _("Project No"),
            "fieldname": "project_no",
            "fieldtype": "Link",
            "options": "Project",
            "width": 130
        },
        {
            "label": _("Project Name"),
            "fieldname": "project_name",
            "fieldtype": "Data",
            "width": 180
        },
        {
            "label": _("PO No"),
            "fieldname": "po_no",
            "fieldtype": "Link",
            "options": "Purchase Order",
            "width": 150
        },
        {
            "label": _("Supplier Name"),
            "fieldname": "supplier_name",
            "fieldtype": "Data",
            "width": 180
        },
        {
            "label": _("Date"),
            "fieldname": "po_date",
            "fieldtype": "Date",
            "width": 100
        },
        {
            "label": _("Item Code"),
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 150
        },
        {
            "label": _("Item Description"),
            "fieldname": "item_description",
            "fieldtype": "Data",
            "width": 200
        },
        {
            "label": _("Qty"),
            "fieldname": "qty",
            "fieldtype": "Float",
            "width": 80
        },
        {
            "label": _("UOM"),
            "fieldname": "uom",
            "fieldtype": "Data",
            "width": 70
        },
        {
            "label": _("Require Date"),
            "fieldname": "schedule_date",
            "fieldtype": "Date",
            "width": 110
        },
        {
            "label": _("Delivery Overdue Days"),
            "fieldname": "overdue_days",
            "fieldtype": "Int",
            "width": 140
        },
        {
            "label": _("Delivered Date"),
            "fieldname": "delivered_date",
            "fieldtype": "Date",
            "width": 110
        },
        {
            "label": _("Purchase Receipt No"),
            "fieldname": "pr_no",
            "fieldtype": "Data",
            "width": 180
        },
        {
            "label": _("Receive Qty"),
            "fieldname": "received_qty",
            "fieldtype": "Float",
            "width": 100
        },
        {
            "label": _("Pending Qty"),
            "fieldname": "pending_qty",
            "fieldtype": "Float",
            "width": 100
        },
        {
            "label": _("Status"),
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 100
        }
    ]


def get_data(filters):
    """
    Fetch submitted POs with item-level delivery tracking from Purchase Receipts.

    Logic:
    - Only submitted POs (docstatus=1)
    - No mandatory filter — fetches all projects by default
    - Hide entire PO when ALL items are fully received
    - One row per PO item with aggregated PR data
    - Overdue days: positive = overdue, negative = early
    """

    conditions = build_conditions(filters)

    # Get PO Items with project name from Project doctype
    items = frappe.db.sql(f"""
        SELECT
            po.project as project_no,
            p.project_name,
            po.name as po_no,
            po.supplier_name,
            po.transaction_date as po_date,
            poi.item_code,
            poi.description as item_description,
            poi.qty,
            poi.uom,
            poi.schedule_date,
            poi.received_qty,
            poi.name as po_item_name
        FROM `tabPurchase Order Item` poi
        INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
        LEFT JOIN `tabProject` p ON p.name = po.project
        WHERE po.docstatus = 1
        {conditions}
        ORDER BY po.project, po.name, poi.idx
    """, filters, as_dict=True)

    if not items:
        return []

    # Group items by PO
    items_by_po = {}
    po_item_names = []
    for item in items:
        items_by_po.setdefault(item.po_no, []).append(item)
        po_item_names.append(item.po_item_name)

    # Get PR data per PO item
    pr_map = get_pr_data(po_item_names)

    # Build result — hide PO if ALL items fully received
    result = []

    for po_no, po_items in items_by_po.items():
        all_complete = all(
            item.received_qty >= item.qty for item in po_items
        )
        if all_complete:
            continue

        for item in po_items:
            pr_info = pr_map.get(item.po_item_name, {})
            received_qty = item.received_qty or 0
            pending_qty = item.qty - received_qty

            # Determine status
            if received_qty <= 0:
                status = "Pending"
            elif received_qty >= item.qty:
                status = "Complete"
            else:
                status = "Partial"

            # Calculate overdue days
            overdue_days = None
            delivered_date = pr_info.get("latest_date")

            if item.schedule_date:
                if received_qty >= item.qty and delivered_date:
                    # Fully delivered: delivery date - schedule date
                    overdue_days = date_diff(delivered_date, item.schedule_date)
                elif received_qty < item.qty:
                    # Not fully delivered: today - schedule date
                    overdue_days = date_diff(today(), item.schedule_date)

            row = {
                "project_no": item.project_no,
                "project_name": item.project_name,
                "po_no": item.po_no,
                "supplier_name": item.supplier_name,
                "po_date": item.po_date,
                "item_code": item.item_code,
                "item_description": item.item_description,
                "qty": item.qty,
                "uom": item.uom,
                "schedule_date": item.schedule_date,
                "overdue_days": overdue_days,
                "delivered_date": delivered_date,
                "pr_no": pr_info.get("pr_nos", ""),
                "received_qty": received_qty,
                "pending_qty": pending_qty,
                "status": status,
                "po_item_name": item.po_item_name,
            }

            result.append(row)

    return result


def build_conditions(filters):
    conditions = ""

    if filters.get("project"):
        conditions += " AND po.project = %(project)s"

    if filters.get("po_no"):
        conditions += " AND po.name = %(po_no)s"

    return conditions


def get_pr_data(po_item_names):
    """
    Get Purchase Receipt data linked to PO items.

    Returns:
        dict: {po_item_name: {'pr_nos': 'PR-001, PR-002', 'latest_date': date}}
    """
    if not po_item_names:
        return {}

    pr_items = frappe.db.sql("""
        SELECT
            pri.purchase_order_item as po_item_name,
            pri.parent as pr_no,
            pr.posting_date
        FROM `tabPurchase Receipt Item` pri
        INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        WHERE pri.purchase_order_item IN %(po_item_names)s
        AND pr.docstatus = 1
        ORDER BY pr.posting_date DESC
    """, {"po_item_names": po_item_names}, as_dict=True)

    result = {}
    for row in pr_items:
        key = row.po_item_name
        if key not in result:
            result[key] = {
                "pr_nos": [],
                "latest_date": row.posting_date
            }

        if row.pr_no not in result[key]["pr_nos"]:
            result[key]["pr_nos"].append(row.pr_no)

        # Track latest posting date
        if row.posting_date and row.posting_date > result[key]["latest_date"]:
            result[key]["latest_date"] = row.posting_date

    for key, info in result.items():
        info["pr_nos"] = ", ".join(info["pr_nos"])

    return result
