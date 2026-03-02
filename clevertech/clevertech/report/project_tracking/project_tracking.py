# Copyright (c) 2026, Bharatbodh and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}

    if not filters.get("project"):
        return [], []

    # If showing stale BOM references, use different columns and data
    if filters.get("show_stale_bom"):
        columns = get_stale_bom_columns()
        data = get_stale_bom_data(filters)
        return columns, data

    columns = get_columns(filters)
    data = get_data(filters)

    return columns, data


def get_columns(filters):
    """Build columns based on filter toggles"""

    # Section 1: Default columns (always visible)
    columns = [
        {"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 120},
        {"label": _("Machine Code"), "fieldname": "machine_code", "fieldtype": "Data", "width": 120},
        {"label": _("WBS Code"), "fieldname": "cost_center", "fieldtype": "Link", "options": "Cost Center", "width": 150},
        {"label": _("M-Code"), "fieldname": "m_code", "fieldtype": "Data", "width": 100},
        {"label": _("G-Code"), "fieldname": "g_code", "fieldtype": "Data", "width": 100},
        {"label": _("Image"), "fieldname": "component_image", "fieldtype": "Data", "width": 80},
        {"label": _("Item No"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
        {"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
        {"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 200},
        {"label": _("Make/Buy"), "fieldname": "make_or_buy", "fieldtype": "Data", "width": 80},
        {"label": _("Qty"), "fieldname": "total_qty_limit", "fieldtype": "Float", "width": 80},
        {"label": _("UOM"), "fieldname": "stock_uom", "fieldtype": "Data", "width": 70},
    ]

    # Section 4: Material Request columns
    if filters.get("show_mr"):
        columns += [
            {"label": _("MR No"), "fieldname": "mr_nos", "fieldtype": "Data", "width": 150},
            {"label": _("MR Qty"), "fieldname": "mr_qty", "fieldtype": "Float", "width": 80},
            {"label": _("MR ETA"), "fieldname": "mr_eta", "fieldtype": "Date", "width": 100},
            {"label": _("Pending for MR"), "fieldname": "pending_mr_qty", "fieldtype": "Float", "width": 100},
        ]

    # Section 5: RFQ & Supplier Quotation columns
    if filters.get("show_rfq"):
        # Vendor 1-4 columns (4 vendors x 4 fields = 16 columns)
        for i in range(1, 5):
            columns += [
                {"label": _(f"Vendor {i}"), "fieldname": f"vendor_{i}_name", "fieldtype": "Data", "width": 120},
                {"label": _(f"V{i} Rate"), "fieldname": f"vendor_{i}_rate", "fieldtype": "Currency", "width": 90},
                {"label": _(f"V{i} Total"), "fieldname": f"vendor_{i}_total", "fieldtype": "Currency", "width": 100},
            ]

        # Comparison columns
        columns += [
            {"label": _("Lowest Vendor"), "fieldname": "lowest_vendor", "fieldtype": "Data", "width": 120},
            {"label": _("Lowest Rate"), "fieldname": "lowest_rate", "fieldtype": "Currency", "width": 90},
            {"label": _("Decided Vendor"), "fieldname": "decided_vendor", "fieldtype": "Data", "width": 120},
            {"label": _("Decided Rate"), "fieldname": "decided_rate", "fieldtype": "Currency", "width": 90},
        ]

    # Section 6: Purchase Order & Delivery columns
    if filters.get("show_po"):
        columns += [
            {"label": _("PO No"), "fieldname": "po_nos", "fieldtype": "Data", "width": 150},
            {"label": _("PO Date"), "fieldname": "po_date", "fieldtype": "Date", "width": 100},
            {"label": _("PO Qty"), "fieldname": "po_qty", "fieldtype": "Float", "width": 80},
            {"label": _("Pending for PO"), "fieldname": "pending_po_qty", "fieldtype": "Float", "width": 100},
            {"label": _("GRN No"), "fieldname": "grn_nos", "fieldtype": "Data", "width": 150},
            {"label": _("Delivery Qty"), "fieldname": "delivery_qty", "fieldtype": "Float", "width": 100},
            {"label": _("Delivery Date"), "fieldname": "delivery_date", "fieldtype": "Date", "width": 100},
            {"label": _("Pending Delivery"), "fieldname": "pending_delivery_qty", "fieldtype": "Float", "width": 110},
            {"label": _("Delivery Status"), "fieldname": "delivery_status", "fieldtype": "Data", "width": 100},
        ]

    return columns


def get_data(filters):
    """
    Fetch data for Project Tracking Report.

    Key concept: Each row = one BOM usage path (M-code/G-code combination).
    For multi-parent items (same raw material under multiple G-codes),
    we show SEPARATE rows for each path.

    Procurement is tracked per BOM path using:
    - MR Item.bom_no = bom_usage.parent_bom
    """
    project = filters.get("project")

    # 1. Get all bom_usage rows - one row per M-code/G-code path
    bom_usage_rows = frappe.db.sql("""
        SELECT
            cbu.parent as component_master,
            cbu.parent_bom,
            cbu.m_code,
            cbu.g_code,
            cbu.qty_per_unit,
            cbu.total_qty_required,
            pcm.project,
            pcm.machine_code,
            pcm.item_code,
            pcm.item_name,
            pcm.description,
            pcm.make_or_buy,
            pcm.total_qty_limit,
            pcm.component_image,
            COALESCE(pcm.cost_center, cc.name) as cost_center,
            item.stock_uom
        FROM `tabComponent BOM Usage` cbu
        INNER JOIN `tabProject Component Master` pcm ON pcm.name = cbu.parent
        LEFT JOIN `tabItem` item ON item.name = pcm.item_code
        LEFT JOIN `tabCost Center` cc ON cc.custom_machine_code = pcm.machine_code
        WHERE pcm.project = %(project)s
        ORDER BY cbu.m_code, cbu.g_code, pcm.item_code
    """, {"project": project}, as_dict=True)

    # 2. Get CMs WITHOUT bom_usage (M-codes themselves, loose items)
    #    These use header-level m_code, g_code
    cms_without_bom_usage = frappe.db.sql("""
        SELECT
            pcm.name as component_master,
            NULL as parent_bom,
            pcm.m_code,
            pcm.g_code,
            NULL as qty_per_unit,
            NULL as total_qty_required,
            pcm.project,
            pcm.machine_code,
            pcm.item_code,
            pcm.item_name,
            pcm.description,
            pcm.make_or_buy,
            pcm.total_qty_limit,
            pcm.component_image,
            COALESCE(pcm.cost_center, cc.name) as cost_center,
            item.stock_uom
        FROM `tabProject Component Master` pcm
        LEFT JOIN `tabItem` item ON item.name = pcm.item_code
        LEFT JOIN `tabCost Center` cc ON cc.custom_machine_code = pcm.machine_code
        WHERE pcm.project = %(project)s
        AND NOT EXISTS (
            SELECT 1 FROM `tabComponent BOM Usage` cbu
            WHERE cbu.parent = pcm.name
        )
        ORDER BY pcm.m_code, pcm.g_code, pcm.item_code
    """, {"project": project}, as_dict=True)

    # 3. Combine all rows
    all_rows = list(bom_usage_rows) + list(cms_without_bom_usage)

    if not all_rows:
        return []

    # 4. Build procurement data maps keyed by (item_code, bom_no)
    procurement_data = get_procurement_data_by_bom(project)

    data = []
    for row in all_rows:
        # Key for procurement lookup: (item_code, parent_bom)
        procurement_key = (row.item_code, row.parent_bom)

        # For items without bom_usage, fall back to item_code-only lookup
        procurement_key_fallback = (row.item_code, None)

        result_row = {
            "component_master": row.component_master,
            "project": row.project,
            "machine_code": row.machine_code,
            "cost_center": row.cost_center,
            "m_code": row.m_code,
            "g_code": row.g_code,
            "component_image": row.component_image,
            "item_code": row.item_code,
            "item_name": row.item_name,
            "description": row.description,
            "make_or_buy": row.make_or_buy,
            # Use total_qty_required from bom_usage if available, else total_qty_limit
            "total_qty_limit": row.total_qty_required or row.total_qty_limit,
            "stock_uom": row.stock_uom,
        }

        # Determine qty for pending calculations
        base_qty = row.total_qty_required or row.total_qty_limit or 0

        # Add Material Request data
        if filters.get("show_mr"):
            mr_data = (procurement_data.get("mr", {}).get(procurement_key) or
                      procurement_data.get("mr", {}).get(procurement_key_fallback) or {})
            mr_qty = mr_data.get("qty") or 0
            result_row.update({
                "mr_nos": mr_data.get("doc_names", ""),
                "mr_qty": mr_qty,
                "mr_eta": mr_data.get("eta"),
                "pending_mr_qty": base_qty - mr_qty,
            })

        # Add RFQ & Supplier Quotation data
        if filters.get("show_rfq"):
            sq_data = (procurement_data.get("sq", {}).get(procurement_key) or
                      procurement_data.get("sq", {}).get(procurement_key_fallback) or {})
            vendors = sq_data.get("vendors", [])

            # Populate vendor columns (up to 4 vendors)
            for i in range(1, 5):
                if i <= len(vendors):
                    v = vendors[i-1]
                    result_row[f"vendor_{i}_name"] = v.get("supplier")
                    result_row[f"vendor_{i}_rate"] = v.get("rate")
                    result_row[f"vendor_{i}_total"] = v.get("amount")
                else:
                    result_row[f"vendor_{i}_name"] = None
                    result_row[f"vendor_{i}_rate"] = None
                    result_row[f"vendor_{i}_total"] = None

            # Comparison columns
            result_row["lowest_vendor"] = sq_data.get("lowest_vendor")
            result_row["lowest_rate"] = sq_data.get("lowest_rate")
            result_row["decided_vendor"] = sq_data.get("decided_vendor")
            result_row["decided_rate"] = sq_data.get("decided_rate")

        # Add Purchase Order & Delivery data
        if filters.get("show_po"):
            po_data = (procurement_data.get("po", {}).get(procurement_key) or
                      procurement_data.get("po", {}).get(procurement_key_fallback) or {})
            pr_data = (procurement_data.get("pr", {}).get(procurement_key) or
                      procurement_data.get("pr", {}).get(procurement_key_fallback) or {})

            po_qty = po_data.get("qty") or 0
            delivery_qty = pr_data.get("qty") or 0

            result_row.update({
                "po_nos": po_data.get("doc_names", ""),
                "po_date": po_data.get("date"),
                "po_qty": po_qty,
                "pending_po_qty": base_qty - po_qty,
                "grn_nos": pr_data.get("doc_names", ""),
                "delivery_qty": delivery_qty,
                "delivery_date": pr_data.get("date"),
                "pending_delivery_qty": po_qty - delivery_qty,
                "delivery_status": get_delivery_status(po_qty, delivery_qty),
            })

        data.append(result_row)

    return data


def get_procurement_data_by_bom(project):
    """
    Fetch procurement data keyed by (item_code, bom_no).

    This allows tracking procurement per BOM path:
    - MR Item has bom_no = parent D-code's BOM
    - bom_usage has parent_bom = same D-code's BOM
    - Match: MR Item.bom_no = bom_usage.parent_bom

    Returns:
        dict: {
            "mr": {(item_code, bom_no): {"doc_names": "...", "qty": X, "eta": date}, ...},
            "sq": {(item_code, bom_no): {"vendors": [...], ...}, ...},
            "po": {(item_code, bom_no): {"doc_names": "...", "qty": X, "date": date}, ...},
            "pr": {(item_code, bom_no): {"doc_names": "...", "qty": X, "date": date}, ...},
        }
    """
    result = {
        "mr": {},   # Material Request
        "sq": {},   # Supplier Quotation
        "po": {},   # Purchase Order
        "pr": {},   # Purchase Receipt
    }

    # ========== Material Request ==========
    # Query MR Items with bom_no for the project
    mr_items = frappe.db.sql("""
        SELECT
            mri.item_code,
            mri.bom_no,
            mri.qty,
            mr.name as mr_no,
            mr.schedule_date
        FROM `tabMaterial Request Item` mri
        INNER JOIN `tabMaterial Request` mr ON mr.name = mri.parent
        WHERE mri.project = %(project)s
        AND mr.docstatus = 1
    """, {"project": project}, as_dict=True)

    for item in mr_items:
        key = (item.item_code, item.bom_no)
        if key not in result["mr"]:
            result["mr"][key] = {"doc_names": [], "qty": 0, "eta": None}
        result["mr"][key]["doc_names"].append(item.mr_no)
        result["mr"][key]["qty"] += item.qty or 0
        if not result["mr"][key]["eta"] and item.schedule_date:
            result["mr"][key]["eta"] = item.schedule_date

    # ========== Purchase Order ==========
    # PO Items linked via MR → PO flow, get bom_no from linked MR Item
    po_items = frappe.db.sql("""
        SELECT
            poi.item_code,
            poi.qty,
            poi.rate,
            po.name as po_no,
            po.transaction_date,
            po.supplier,
            mri.bom_no
        FROM `tabPurchase Order Item` poi
        INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
        LEFT JOIN `tabMaterial Request Item` mri ON mri.name = poi.material_request_item
        WHERE poi.project = %(project)s
        AND po.docstatus = 1
    """, {"project": project}, as_dict=True)

    for item in po_items:
        key = (item.item_code, item.bom_no)
        if key not in result["po"]:
            result["po"][key] = {"doc_names": [], "qty": 0, "date": None}
        result["po"][key]["doc_names"].append(item.po_no)
        result["po"][key]["qty"] += item.qty or 0
        if not result["po"][key]["date"] and item.transaction_date:
            result["po"][key]["date"] = item.transaction_date

        # Also track decided vendor in SQ data
        if key not in result["sq"]:
            result["sq"][key] = {"vendors": [], "lowest_vendor": None, "lowest_rate": None}
        result["sq"][key]["decided_vendor"] = item.supplier
        result["sq"][key]["decided_rate"] = item.rate

    # ========== Purchase Receipt (Delivery) ==========
    # PR Items linked via PO → PR flow
    pr_items = frappe.db.sql("""
        SELECT
            pri.item_code,
            pri.qty,
            pr.name as pr_no,
            pr.posting_date,
            mri.bom_no
        FROM `tabPurchase Receipt Item` pri
        INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        LEFT JOIN `tabPurchase Order Item` poi ON poi.name = pri.purchase_order_item
        LEFT JOIN `tabMaterial Request Item` mri ON mri.name = poi.material_request_item
        WHERE pri.project = %(project)s
        AND pr.docstatus = 1
    """, {"project": project}, as_dict=True)

    for item in pr_items:
        key = (item.item_code, item.bom_no)
        if key not in result["pr"]:
            result["pr"][key] = {"doc_names": [], "qty": 0, "date": None}
        result["pr"][key]["doc_names"].append(item.pr_no)
        result["pr"][key]["qty"] += item.qty or 0
        if not result["pr"][key]["date"] and item.posting_date:
            result["pr"][key]["date"] = item.posting_date

    # ========== Supplier Quotation ==========
    # SQ Items - link via RFQ → SQ flow if available
    sq_items = frappe.db.sql("""
        SELECT
            sqi.item_code,
            sqi.qty,
            sqi.rate,
            sqi.amount,
            sq.name as sq_no,
            sq.supplier,
            mri.bom_no
        FROM `tabSupplier Quotation Item` sqi
        INNER JOIN `tabSupplier Quotation` sq ON sq.name = sqi.parent
        LEFT JOIN `tabRequest for Quotation Item` rfqi ON rfqi.name = sqi.request_for_quotation_item
        LEFT JOIN `tabMaterial Request Item` mri ON mri.name = rfqi.material_request_item
        WHERE sqi.project = %(project)s
        AND sq.docstatus = 1
    """, {"project": project}, as_dict=True)

    for item in sq_items:
        key = (item.item_code, item.bom_no)
        if key not in result["sq"]:
            result["sq"][key] = {"vendors": [], "lowest_vendor": None, "lowest_rate": None}
        result["sq"][key]["vendors"].append({
            "supplier": item.supplier,
            "rate": item.rate,
            "amount": item.amount,
        })

    # ========== Post-process ==========
    # Join doc_names and find lowest vendor
    for key, data in result["mr"].items():
        data["doc_names"] = ", ".join(list(set(data["doc_names"])))

    for key, data in result["sq"].items():
        if data["vendors"]:
            data["vendors"].sort(key=lambda x: x.get("rate") or float("inf"))
            data["lowest_vendor"] = data["vendors"][0].get("supplier")
            data["lowest_rate"] = data["vendors"][0].get("rate")

    for key, data in result["po"].items():
        data["doc_names"] = ", ".join(list(set(data["doc_names"])))

    for key, data in result["pr"].items():
        data["doc_names"] = ", ".join(list(set(data["doc_names"])))

    return result


def get_delivery_status(po_qty, delivery_qty):
    """Calculate delivery status based on PO qty vs delivered qty"""
    if not po_qty:
        return "Pending"
    if delivery_qty >= po_qty:
        return "Completed"
    if delivery_qty > 0:
        return "Partial"
    return "Pending"


# ==================== Stale BOM References ====================

def get_stale_bom_columns():
    """Columns for Stale BOM References view"""
    return [
        {"label": _("Parent BOM"), "fieldname": "parent_bom", "fieldtype": "Link", "options": "BOM", "width": 180},
        {"label": _("Parent Item"), "fieldname": "parent_item", "fieldtype": "Link", "options": "Item", "width": 150},
        {"label": _("Child Item"), "fieldname": "child_item", "fieldtype": "Link", "options": "Item", "width": 150},
        {"label": _("Child BOM (in Parent)"), "fieldname": "child_bom_in_parent", "fieldtype": "Link", "options": "BOM", "width": 180},
        {"label": _("Current Default BOM"), "fieldname": "current_default_bom", "fieldtype": "Link", "options": "BOM", "width": 180},
        {"label": _("Used by CM"), "fieldname": "used_by_cm", "fieldtype": "Data", "width": 180},
        {"label": _("Procurement Impact"), "fieldname": "procurement_impact", "fieldtype": "Data", "width": 120},
        {"label": _("Status"), "fieldname": "bom_status", "fieldtype": "Data", "width": 120},
    ]


def get_stale_bom_data(filters):
    """
    Find all parent BOMs in the project that have outdated child BOM references.

    A "stale" reference occurs when:
    - Parent BOM has a BOM Item with bom_no = BOM-X-001
    - But the current default BOM for that child item is BOM-X-002

    This happens after a child BOM version change - the parent still references
    the old (now demoted) child BOM version.

    Also shows which Component Masters reference the stale parent BOM as their
    active_bom. If no CM references it, procurement is not affected.
    """
    project = filters.get("project")

    # Get all active submitted BOMs for the project
    # that have child items with their own BOMs (bom_no is set)
    stale_refs = frappe.db.sql("""
        SELECT
            parent_bom.name AS parent_bom,
            parent_bom.item AS parent_item,
            bi.item_code AS child_item,
            bi.bom_no AS child_bom_in_parent,
            child_default.name AS current_default_bom
        FROM `tabBOM` parent_bom
        INNER JOIN `tabBOM Item` bi ON bi.parent = parent_bom.name
        LEFT JOIN `tabBOM` child_default ON (
            child_default.item = bi.item_code
            AND child_default.is_active = 1
            AND child_default.is_default = 1
            AND child_default.docstatus = 1
        )
        WHERE parent_bom.project = %(project)s
        AND parent_bom.docstatus = 1
        AND parent_bom.is_active = 1
        AND bi.bom_no IS NOT NULL
        AND bi.bom_no != ''
        AND (
            child_default.name IS NULL
            OR bi.bom_no != child_default.name
        )
        ORDER BY parent_bom.item, bi.item_code
    """, {"project": project}, as_dict=True)

    if not stale_refs:
        return []

    # Build lookup: parent_bom_name → list of CMs that reference it as active_bom
    stale_bom_names = list(set(r.parent_bom for r in stale_refs))
    cm_usage = {}
    if stale_bom_names:
        cm_rows = frappe.db.sql("""
            SELECT name, item_code, active_bom
            FROM `tabProject Component Master`
            WHERE project = %(project)s
            AND active_bom IN %(bom_names)s
        """, {"project": project, "bom_names": stale_bom_names}, as_dict=True)
        for cm in cm_rows:
            cm_usage.setdefault(cm.active_bom, []).append(cm.name)

    data = []
    for row in stale_refs:
        status = "⚠️ Outdated" if row.current_default_bom else "⚠️ No Default"
        cms_using = cm_usage.get(row.parent_bom, [])
        if cms_using:
            used_by = ", ".join(cms_using)
            impact = "⚠️ Active"
        else:
            used_by = "-"
            impact = "No Impact"

        data.append({
            "parent_bom": row.parent_bom,
            "parent_item": row.parent_item,
            "child_item": row.child_item,
            "child_bom_in_parent": row.child_bom_in_parent,
            "current_default_bom": row.current_default_bom or "-",
            "used_by_cm": used_by,
            "procurement_impact": impact,
            "bom_status": status,
        })

    return data
