import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}

    if not filters.get("show_all_projects") and not filters.get("project") and not filters.get("rfq_no"):
        frappe.throw(_("Please check 'Show All Projects' or select a Project / RFQ No to load data."))

    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
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
            "label": _("RFQ No"),
            "fieldname": "rfq_no",
            "fieldtype": "Link",
            "options": "Request for Quotation",
            "width": 150
        },
        {
            "label": _("Date"),
            "fieldname": "rfq_date",
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
            "label": _("Required Days"),
            "fieldname": "required_days",
            "fieldtype": "Int",
            "width": 100
        },
        {
            "label": _("Supplier Code"),
            "fieldname": "supplier_code",
            "fieldtype": "Link",
            "options": "Supplier",
            "width": 120
        },
        {
            "label": _("Supplier Name"),
            "fieldname": "supplier_name",
            "fieldtype": "Data",
            "width": 180
        },
        {
            "label": _("Supplier Quotation Status"),
            "fieldname": "sq_status",
            "fieldtype": "Data",
            "width": 180
        },
        {
            "label": _("Supplier Quotation No"),
            "fieldname": "sq_no",
            "fieldtype": "Data",
            "width": 160
        },
        {
            "label": _("SQ Comparison Date"),
            "fieldname": "sqc_date",
            "fieldtype": "Date",
            "width": 130
        },
        {
            "label": _("SQ Comparison No"),
            "fieldname": "sqc_no",
            "fieldtype": "Data",
            "width": 160
        },
        {
            "label": _("SQ Comparison Status"),
            "fieldname": "sqc_status",
            "fieldtype": "Data",
            "width": 160
        }
    ]


def get_data(filters):
    """
    Fetch submitted RFQs with items and suppliers shown side-by-side.

    Layout: Items on the left, Suppliers on the right.
    Rows per RFQ = max(item count, supplier count).
    - If more items than suppliers, extra item rows have blank supplier columns.
    - If more suppliers than items, extra supplier rows have blank item columns.

    SQ Comparison data is per-RFQ (shown on the first row only).

    Filtering:
    - Only Submitted RFQs (docstatus=1)
    - Hide entire RFQ when ALL items have POs
    - Show all projects by default unless a specific project or RFQ is selected
    - Latest RFQs appear first (ORDER BY rfq.transaction_date DESC)
    """

    conditions = build_conditions(filters)

    # Get RFQ Items — ordered latest first
    items = frappe.db.sql(f"""
        SELECT
            COALESCE(mr.custom_project_, rfq.custom_project) as project,
            rfqi.parent as rfq_no,
            rfq.transaction_date as rfq_date,
            rfqi.item_code,
            rfqi.description as item_description,
            rfqi.qty,
            rfqi.stock_uom as uom,
            rfq.custom_required_by_in_days as required_days,
            rfqi.name as rfq_item_name
        FROM `tabRequest for Quotation Item` rfqi
        INNER JOIN `tabRequest for Quotation` rfq ON rfq.name = rfqi.parent
        LEFT JOIN `tabMaterial Request` mr ON mr.name = rfqi.material_request
        WHERE rfq.docstatus = 1
        {conditions}
        ORDER BY rfq.transaction_date DESC, COALESCE(mr.custom_project_, rfq.custom_project), rfq.name, rfqi.idx
    """, filters, as_dict=True)

    if not items:
        return []

    # Collect unique RFQ numbers preserving latest-first order
    seen_rfq = set()
    rfq_nos_ordered = []
    for d in items:
        if d.rfq_no not in seen_rfq:
            seen_rfq.add(d.rfq_no)
            rfq_nos_ordered.append(d.rfq_no)

    rfq_nos = rfq_nos_ordered

    # Get project names
    projects = list(set(d.project for d in items if d.project))
    project_names = {}
    if projects:
        for p in frappe.db.sql(
            "SELECT name, project_name FROM `tabProject` WHERE name IN %(projects)s",
            {"projects": projects}, as_dict=True
        ):
            project_names[p.name] = p.project_name

    # Get suppliers per RFQ
    suppliers_map = get_rfq_suppliers(rfq_nos)

    # Get Supplier Quotation info per (RFQ, Supplier)
    sq_info_map = get_sq_info(rfq_nos)

    # Enrich suppliers with SQ numbers and derived status
    for rfq_no, suppliers in suppliers_map.items():
        for sup in suppliers:
            info = sq_info_map.get((rfq_no, sup["supplier"]))
            if info:
                sup["sq_no"] = info["sq_nos"]
                sup["sq_status"] = info["status"]
            else:
                sup["sq_no"] = ""
                sup["sq_status"] = "Pending"

    # Get SQ Comparison per RFQ
    sqc_map = get_sq_comparison_data(rfq_nos)

    # Get PO data per RFQ item (used only to determine if all items have POs)
    rfq_item_names = [d.rfq_item_name for d in items]
    po_map = get_po_data(rfq_item_names)

    # Group items by RFQ
    items_by_rfq = {}
    for item in items:
        items_by_rfq.setdefault(item.rfq_no, []).append(item)

    # Build side-by-side rows
    result = []

    for rfq_no in rfq_nos:
        rfq_items = items_by_rfq.get(rfq_no, [])
        rfq_suppliers = suppliers_map.get(rfq_no, [])
        sqc = sqc_map.get(rfq_no, {})

        # Check if ALL items have POs — if so, skip this RFQ
        all_have_po = rfq_items and all(
            po_map.get(item.rfq_item_name, {}).get("po_nos") for item in rfq_items
        )
        if all_have_po:
            continue

        # RFQ-level fields (from first item)
        first = rfq_items[0] if rfq_items else {}
        project = first.get("project", "")
        proj_name = project_names.get(project, "")
        rfq_date = first.get("rfq_date")
        required_days = first.get("required_days")

        row_count = max(len(rfq_items), len(rfq_suppliers))

        for i in range(row_count):
            row = {
                "project": project,
                "project_name": proj_name,
                "rfq_no": rfq_no,
                "rfq_date": rfq_date,
            }

            # Item columns (left side)
            if i < len(rfq_items):
                item = rfq_items[i]
                row.update({
                    "item_code": item.item_code,
                    "item_description": item.item_description,
                    "qty": item.qty,
                    "uom": item.uom,
                    "required_days": required_days,
                })

            # Supplier columns (right side)
            if i < len(rfq_suppliers):
                sup = rfq_suppliers[i]
                row.update({
                    "supplier_code": sup["supplier"],
                    "supplier_name": sup["supplier_name"],
                    "sq_status": sup.get("sq_status", "Pending"),
                    "sq_no": sup.get("sq_no", ""),
                })

            # SQ Comparison (RFQ-level, show on first row only)
            if i == 0 and sqc:
                row.update({
                    "sqc_date": sqc.get("date"),
                    "sqc_no": sqc.get("name"),
                    "sqc_status": sqc.get("workflow_state", ""),
                })

            result.append(row)

    return result


def build_conditions(filters):
    conditions = ""

    if filters.get("project"):
        conditions += " AND COALESCE(mr.custom_project_, rfq.custom_project) = %(project)s"

    if filters.get("rfq_no"):
        conditions += " AND rfq.name = %(rfq_no)s"

    return conditions


def get_rfq_suppliers(rfq_nos):
    """
    Get suppliers and their quote_status for given RFQs.

    Returns:
        dict: {rfq_no: [{'supplier': ..., 'supplier_name': ..., 'quote_status': ...}, ...]}
    """
    if not rfq_nos:
        return {}

    suppliers = frappe.db.sql("""
        SELECT
            parent as rfq_no,
            supplier,
            supplier_name,
            quote_status
        FROM `tabRequest for Quotation Supplier`
        WHERE parent IN %(rfq_nos)s
        ORDER BY parent, idx
    """, {"rfq_nos": rfq_nos}, as_dict=True)

    result = {}
    for sup in suppliers:
        result.setdefault(sup.rfq_no, []).append({
            "supplier": sup.supplier,
            "supplier_name": sup.supplier_name,
            "quote_status": sup.quote_status or "Pending"
        })

    return result


def get_sq_info(rfq_nos):
    """
    Get Supplier Quotation info per (RFQ, Supplier).
    Derives status from actual SQ docstatus instead of RFQ Supplier.quote_status.

    Status logic:
    - No SQ exists → "Pending"
    - SQ exists in Draft (docstatus=0) → "Draft"
    - SQ exists and Submitted (docstatus=1) → "Submitted"

    Returns:
        dict: {(rfq_no, supplier): {'sq_nos': 'SQ-001, SQ-002', 'status': 'Submitted'}}
    """
    if not rfq_nos:
        return {}

    sq_list = frappe.db.sql("""
        SELECT DISTINCT
            sqi.request_for_quotation as rfq_no,
            sq.supplier,
            sq.name as sq_no,
            sq.docstatus
        FROM `tabSupplier Quotation Item` sqi
        INNER JOIN `tabSupplier Quotation` sq ON sq.name = sqi.parent
        WHERE sqi.request_for_quotation IN %(rfq_nos)s
        AND sq.docstatus < 2
        ORDER BY sq.name
    """, {"rfq_nos": rfq_nos}, as_dict=True)

    # Group by (rfq, supplier)
    grouped = {}
    for row in sq_list:
        key = (row.rfq_no, row.supplier)
        if key not in grouped:
            grouped[key] = {"sq_nos": [], "has_submitted": False}
        if row.sq_no not in grouped[key]["sq_nos"]:
            grouped[key]["sq_nos"].append(row.sq_no)
        if row.docstatus == 1:
            grouped[key]["has_submitted"] = True

    result = {}
    for key, info in grouped.items():
        result[key] = {
            "sq_nos": ", ".join(info["sq_nos"]),
            "status": "Submitted" if info["has_submitted"] else "Draft"
        }

    return result


def get_sq_comparison_data(rfq_nos):
    """
    Get Supplier Quotation Comparison documents linked to RFQs.

    Returns:
        dict: {rfq_no: {'name': ..., 'date': ..., 'workflow_state': ...}}
    """
    if not rfq_nos:
        return {}

    sqc_list = frappe.db.sql("""
        SELECT
            name,
            request_for_quotation,
            date,
            workflow_state
        FROM `tabSupplier Quotation Comparison`
        WHERE request_for_quotation IN %(rfq_nos)s
        AND docstatus < 2
        ORDER BY date DESC
    """, {"rfq_nos": rfq_nos}, as_dict=True)

    # One SQC per RFQ (latest if multiple)
    result = {}
    for sqc in sqc_list:
        rfq = sqc.request_for_quotation
        if rfq not in result:
            result[rfq] = {
                "name": sqc.name,
                "date": sqc.date,
                "workflow_state": sqc.workflow_state or "Draft"
            }

    return result


def get_po_data(rfq_item_names):
    """
    Get PO data linked to RFQ items via Supplier Quotation chain.
    Used only to determine whether all items have POs (to hide completed RFQs).
    Chain: RFQ Item → SQ Item (request_for_quotation_item) → PO Item (supplier_quotation_item)

    Returns:
        dict: {rfq_item_name: {'po_nos': 'PO-001, PO-002', 'po_date': date}}
    """
    if not rfq_item_names:
        return {}

    # Find SQ Items linked to RFQ Items
    sq_items = frappe.db.sql("""
        SELECT
            sqi.request_for_quotation_item as rfq_item_name,
            sqi.name as sq_item_name
        FROM `tabSupplier Quotation Item` sqi
        INNER JOIN `tabSupplier Quotation` sq ON sq.name = sqi.parent
        WHERE sqi.request_for_quotation_item IN %(rfq_item_names)s
        AND sq.docstatus = 1
    """, {"rfq_item_names": rfq_item_names}, as_dict=True)

    if not sq_items:
        return {}

    sq_to_rfq = {}
    sq_item_names = []
    for si in sq_items:
        sq_to_rfq[si.sq_item_name] = si.rfq_item_name
        sq_item_names.append(si.sq_item_name)

    # Find PO Items linked to SQ Items
    po_items = frappe.db.sql("""
        SELECT
            poi.supplier_quotation_item as sq_item_name,
            poi.parent as po_no,
            po.transaction_date as po_date
        FROM `tabPurchase Order Item` poi
        INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
        WHERE poi.supplier_quotation_item IN %(sq_item_names)s
        AND po.docstatus = 1
    """, {"sq_item_names": sq_item_names}, as_dict=True)

    # Aggregate POs by RFQ Item
    result = {}
    for poi in po_items:
        rfq_item = sq_to_rfq.get(poi.sq_item_name)
        if not rfq_item:
            continue

        if rfq_item not in result:
            result[rfq_item] = {"po_nos": [], "po_date": poi.po_date}

        if poi.po_no not in result[rfq_item]["po_nos"]:
            result[rfq_item]["po_nos"].append(poi.po_no)

    for rfq_item, info in result.items():
        info["po_nos"] = ", ".join(info["po_nos"])

    return result
