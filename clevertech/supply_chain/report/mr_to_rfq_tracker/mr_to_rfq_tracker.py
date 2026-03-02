import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}

    # If show_all_projects is unchecked, a project must be selected
    if not filters.get("show_all_projects") and not filters.get("project"):
        frappe.throw(_("Please select a Project, or check 'Show All Projects'"))

    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    """Define columns for MR to RFQ Tracker report"""
    return [
        {
            "label": _("Project No"),
            "fieldname": "project",
            "fieldtype": "Link",
            "options": "Project",
            "width": 120
        },
        {
            "label": _("Project Name"),
            "fieldname": "project_name",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": _("MR No"),
            "fieldname": "mr_no",
            "fieldtype": "Link",
            "options": "Material Request",
            "width": 150
        },
        {
            "label": _("MR Date"),
            "fieldname": "mr_date",
            "fieldtype": "Date",
            "width": 100
        },
        {
            "label": _("Item Image"),
            "fieldname": "item_image",
            "fieldtype": "Data",
            "width": 80
        },
        {
            "label": _("Item Code"),
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 150
        },
        {
            "label": _("Part Number"),
            "fieldname": "part_number",
            "fieldtype": "Data",
            "width": 130
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
            "label": _("Item Group"),
            "fieldname": "item_group",
            "fieldtype": "Link",
            "options": "Item Group",
            "width": 120
        },
        {
            "label": _("Type of Material"),
            "fieldname": "type_of_material",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": _("Required Days"),
            "fieldname": "required_days",
            "fieldtype": "Int",
            "width": 100
        },
        {
            "label": _("RFQ No"),
            "fieldname": "rfq_no",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": _("RFQ Status"),
            "fieldname": "rfq_status",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "label": _("RFQ Qty"),
            "fieldname": "rfq_qty",
            "fieldtype": "Float",
            "width": 80
        },
        {
            "label": _("Balance Qty"),
            "fieldname": "balance_qty",
            "fieldtype": "Float",
            "width": 90
        },
        {
            "label": _("Supplier Code"),
            "fieldname": "supplier_code",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": _("RFQ-Supplier Name"),
            "fieldname": "supplier_name",
            "fieldtype": "Data",
            "width": 200
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
    Fetch Material Request Items with their RFQ coverage.

    Logic:
    - One row per MR Item
    - Aggregate all RFQs related to that MR Item
    - Show only pending/partial items (Balance Qty > 0)
    - Hide MRs where all items are fully covered by RFQs
    - Show all projects by default; filter only when project/mr_no is specified
    - Latest MRs appear at the top (sorted by transaction_date DESC)
    """

    conditions = build_conditions(filters)

    # Main query to get MR Items with RFQ aggregation
    data = frappe.db.sql(f"""
        SELECT
            mr.name as project,
            proj.project_name,
            mr.name as mr_no,
            mr.transaction_date as mr_date,
            item.image as item_image,
            mri.item_code,
            item.custom_excode as part_number,
            mri.description as item_description,
            mri.qty,
            mri.stock_uom as uom,
            item.item_group,
            mri.custom_type_of_material as type_of_material,
            mr.custom_required_by_in_days as required_days,
            mri.name as mr_item_name,
            mri.project as project_no
        FROM `tabMaterial Request Item` mri
        INNER JOIN `tabMaterial Request` mr ON mr.name = mri.parent
        LEFT JOIN `tabProject` proj ON proj.name = mri.project
        LEFT JOIN `tabItem` item ON item.name = mri.item_code
        WHERE mr.docstatus = 1
        AND mr.material_request_type = 'Purchase'
        {conditions}
        ORDER BY mr.transaction_date DESC, mri.project, mr.name, mri.item_code
    """, filters, as_dict=True)

    if not data:
        return []

    # Fix: project field should show the project number (name of the Project doc),
    # not the MR name. We already fetch mri.project as project_no above.
    for row in data:
        row['project'] = row.get('project_no', '')

    # Get RFQ data for all MR Items
    mr_item_names = [d.mr_item_name for d in data]
    rfq_data = get_rfq_data(mr_item_names)

    # Enrich ALL items with RFQ information and calculate balance
    enriched_data = []
    mr_has_pending = {}  # Track which MRs have at least one pending item

    for row in data:
        rfq_info = rfq_data.get(row.mr_item_name, {})

        rfq_qty = rfq_info.get('rfq_qty', 0)
        balance_qty = row.qty - rfq_qty

        # Enrich the row with RFQ data
        row.update({
            'rfq_no': rfq_info.get('rfq_nos', ''),
            'rfq_status': rfq_info.get('rfq_status', ''),
            'rfq_qty': rfq_qty,
            'balance_qty': balance_qty,
            'supplier_code': rfq_info.get('supplier_code', ''),
            'supplier_name': rfq_info.get('supplier_name', ''),
            'status': get_status(balance_qty, row.qty)
        })

        enriched_data.append(row)

        # Track if this MR has any pending item
        mr_no = row['mr_no']
        if balance_qty > 0:
            mr_has_pending[mr_no] = True

    # Filter: Only show MRs that have at least one pending item
    # (Show ALL items from those MRs, including completed ones)
    result = [row for row in enriched_data if mr_has_pending.get(row['mr_no'], False)]

    # Apply status filter if selected (blank = show all)
    status_filter = filters.get("status_filter")
    if status_filter == "Complete":
        result = [row for row in result if row['status'] == 'Complete']
    elif status_filter == "Incomplete":
        result = [row for row in result if row['status'] in ('Pending', 'Partial')]

    return result


def build_conditions(filters):
    """Build WHERE conditions based on filters"""
    conditions = ""

    if filters.get("project"):
        conditions += " AND mri.project = %(project)s"

    if filters.get("mr_no"):
        conditions += " AND mr.name = %(mr_no)s"

    return conditions


def get_rfq_data(mr_item_names):
    """
    Get aggregated RFQ data for given MR Items.

    Returns:
        dict: {mr_item_name: {rfq_nos, rfq_status, rfq_qty, supplier_code, supplier_name}}
    """
    if not mr_item_names:
        return {}

    # Get RFQ Items linked to these MR Items
    # docstatus: 0 = Draft, 1 = Submitted, 2 = Cancelled
    rfq_items = frappe.db.sql("""
        SELECT
            rfqi.material_request_item,
            rfqi.parent as rfq_no,
            rfqi.qty,
            rfq.status,
            rfq.docstatus
        FROM `tabRequest for Quotation Item` rfqi
        INNER JOIN `tabRequest for Quotation` rfq ON rfq.name = rfqi.parent
        WHERE rfqi.material_request_item IN %(mr_item_names)s
        AND rfq.docstatus < 2
        ORDER BY rfq.name
    """, {'mr_item_names': mr_item_names}, as_dict=True)

    # Get RFQ Suppliers
    rfq_nos = list(set([item.rfq_no for item in rfq_items]))
    suppliers_map = get_rfq_suppliers(rfq_nos)

    # Aggregate by MR Item
    result = {}
    for item in rfq_items:
        mr_item = item.material_request_item

        if mr_item not in result:
            result[mr_item] = {
                'rfq_nos': [],
                'rfq_status': [],
                'rfq_qty': 0,
                'suppliers': []
            }

        result[mr_item]['rfq_nos'].append(item.rfq_no)
        result[mr_item]['rfq_status'].append(item.status or 'Draft')
        # Only submitted RFQs (docstatus=1) count toward covered qty.
        # Draft RFQs are visible in the report but must not reduce the balance,
        # otherwise a Draft RFQ would incorrectly show the item as Complete.
        if item.docstatus == 1:
            result[mr_item]['rfq_qty'] += item.qty or 0
        # Add suppliers for this RFQ
        if item.rfq_no in suppliers_map:
            result[mr_item]['suppliers'].extend(suppliers_map[item.rfq_no])

    # Format aggregated data
    for mr_item, data in result.items():
        # Remove duplicates and join
        data['rfq_nos'] = ', '.join(list(dict.fromkeys(data['rfq_nos'])))
        data['rfq_status'] = ', '.join(list(dict.fromkeys(data['rfq_status'])))

        # Format suppliers comma-separated
        unique_suppliers = list({s['supplier']: s for s in data['suppliers']}.values())

        data['supplier_code'] = ', '.join([s['supplier'] for s in unique_suppliers])
        data['supplier_name'] = ', '.join([s['supplier_name'] for s in unique_suppliers])

        del data['suppliers']  # Clean up

    return result


def get_rfq_suppliers(rfq_nos):
    """
    Get suppliers for given RFQ numbers.

    Returns:
        dict: {rfq_no: [{'supplier': 'VC001', 'supplier_name': 'Vendor A'}, ...]}
    """
    if not rfq_nos:
        return {}

    suppliers = frappe.db.sql("""
        SELECT
            parent as rfq_no,
            supplier,
            supplier_name
        FROM `tabRequest for Quotation Supplier`
        WHERE parent IN %(rfq_nos)s
        ORDER BY parent, supplier
    """, {'rfq_nos': rfq_nos}, as_dict=True)

    result = {}
    for sup in suppliers:
        if sup.rfq_no not in result:
            result[sup.rfq_no] = []
        result[sup.rfq_no].append({
            'supplier': sup.supplier,
            'supplier_name': sup.supplier_name
        })

    return result


def get_status(balance_qty, total_qty):
    """Calculate status based on balance quantity"""
    if balance_qty >= total_qty:
        return "Pending"
    elif balance_qty > 0:
        return "Partial"
    else:
        return "Complete"
