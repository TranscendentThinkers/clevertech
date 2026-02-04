"""
Procurement Event Hooks for Project Component Master

Tracks procurement documents (MR, RFQ, PO, PR) in the Component Procurement Record
child table. Uses silent skip pattern — only processes items that have a Component Master.

Supplier Quotations are NOT tracked here (use separate comparison report).
"""

import frappe
from frappe import _


# ==================== Material Request ====================

def on_mr_submit(doc, method=None):
    """Track submitted Material Request items in Component Master."""
    _add_procurement_records(doc, "Material Request")


def on_mr_cancel(doc, method=None):
    """Remove Material Request tracking from Component Master."""
    _remove_procurement_records(doc, "Material Request")


# ==================== Request for Quotation ====================

def on_rfq_submit(doc, method=None):
    """Track submitted RFQ items in Component Master."""
    _add_procurement_records(doc, "Request for Quotation")


def on_rfq_cancel(doc, method=None):
    """Remove RFQ tracking from Component Master."""
    _remove_procurement_records(doc, "Request for Quotation")


# ==================== Purchase Order ====================

def on_po_submit(doc, method=None):
    """Track submitted Purchase Order items in Component Master."""
    _add_procurement_records(doc, "Purchase Order")


def on_po_cancel(doc, method=None):
    """Remove Purchase Order tracking from Component Master."""
    _remove_procurement_records(doc, "Purchase Order")


# ==================== Purchase Receipt ====================

def on_pr_submit(doc, method=None):
    """Track submitted Purchase Receipt items in Component Master."""
    _add_procurement_records(doc, "Purchase Receipt")


def on_pr_cancel(doc, method=None):
    """Remove Purchase Receipt tracking from Component Master."""
    _remove_procurement_records(doc, "Purchase Receipt")


# ==================== Common Helpers ====================

def _get_project_from_doc(doc):
    """
    Extract project from a procurement document.
    Different doctypes store the project in different fields:
    - Purchase Order / Purchase Receipt: project (standard field)
    - Material Request: custom_project_ (with trailing underscore)
    - Request for Quotation: custom_project (no trailing underscore)
    """
    # Standard project field (PO, PR)
    if doc.get("project"):
        return doc.project

    # Material Request uses custom_project_ (with underscore)
    if doc.get("custom_project_"):
        return doc.custom_project_

    # Request for Quotation uses custom_project (no underscore)
    if doc.get("custom_project"):
        return doc.custom_project

    return None


def _get_items_from_doc(doc, doc_type):
    """
    Extract item rows from a procurement document.
    Returns list of dicts with item_code, qty, rate, project.
    """
    items = []

    if doc_type == "Request for Quotation":
        # RFQ has items child table but qty/rate may be in suppliers child
        for item in doc.get("items", []):
            items.append({
                "item_code": item.item_code,
                "qty": item.qty,
                "rate": 0,  # RFQ doesn't have rates
                "project": item.get("project") or _get_project_from_doc(doc),
            })
    else:
        for item in doc.get("items", []):
            items.append({
                "item_code": item.item_code,
                "qty": item.qty,
                "rate": item.get("rate") or 0,
                "project": item.get("project") or _get_project_from_doc(doc),
            })

    return items


def _add_procurement_records(doc, doc_type):
    """
    Add procurement record rows to Component Masters for all items in the document.
    Silent skip for items without a Component Master.
    """
    items = _get_items_from_doc(doc, doc_type)

    for item_data in items:
        project = item_data["project"]
        if not project:
            continue

        item_code = item_data["item_code"]

        # Find Component Master for this project + item
        cm_name = frappe.db.get_value(
            "Project Component Master",
            {"project": project, "item_code": item_code},
            "name"
        )

        if not cm_name:
            continue  # Silent skip — item not tracked

        cm = frappe.get_doc("Project Component Master", cm_name)

        # Check if this exact record already exists (idempotent)
        already_exists = False
        for row in cm.procurement_records:
            if row.document_type == doc_type and row.document_name == doc.name:
                already_exists = True
                break

        if already_exists:
            continue

        # Determine procurement source
        procurement_source = "BOM Item"
        if cm.is_loose_item:
            procurement_source = "Loose Item"

        # Get BOM version for tracking
        # Priority:
        # 1. If MR has custom_procurement_bom set, use that (accurate)
        # 2. Otherwise, infer from current active parent BOM (may not be accurate for historical data)
        bom_version = None
        if doc.get("custom_procurement_bom"):
            bom_version = doc.custom_procurement_bom
        else:
            # Fallback: For assemblies use their own active_bom, for raw materials use parent's active_bom
            bom_version = _get_bom_version_for_procurement(cm, project)

        # Add the procurement record row
        cm.append("procurement_records", {
            "document_type": doc_type,
            "document_name": doc.name,
            "quantity": item_data["qty"],
            "rate": item_data["rate"],
            "amount": item_data["qty"] * item_data["rate"],
            "date": doc.get("transaction_date") or doc.get("posting_date") or frappe.utils.today(),
            "status": _get_document_status(doc),
            "procurement_source": procurement_source,
            "bom_version": bom_version,
        })

        cm.flags.ignore_validate = True
        cm.flags.ignore_mandatory = True
        cm.save(ignore_permissions=True)


def _remove_procurement_records(doc, doc_type):
    """
    Remove procurement record rows from Component Masters when document is cancelled.
    Silent skip for items without a Component Master.
    """
    items = _get_items_from_doc(doc, doc_type)

    for item_data in items:
        project = item_data["project"]
        if not project:
            continue

        item_code = item_data["item_code"]

        cm_name = frappe.db.get_value(
            "Project Component Master",
            {"project": project, "item_code": item_code},
            "name"
        )

        if not cm_name:
            continue  # Silent skip

        cm = frappe.get_doc("Project Component Master", cm_name)

        # Find and remove matching rows
        rows_to_remove = []
        for idx, row in enumerate(cm.procurement_records):
            if row.document_type == doc_type and row.document_name == doc.name:
                rows_to_remove.append(idx)

        if not rows_to_remove:
            continue

        for idx in reversed(rows_to_remove):
            cm.remove(cm.procurement_records[idx])

        cm.flags.ignore_validate = True
        cm.flags.ignore_mandatory = True
        cm.save(ignore_permissions=True)


def _get_document_status(doc):
    """Get human-readable status from a document."""
    status_map = {
        0: "Draft",
        1: "Submitted",
        2: "Cancelled",
    }
    return status_map.get(doc.docstatus, "Unknown")


def _get_bom_version_for_procurement(component_master, project):
    """
    Get the BOM version to store in procurement records.

    For assemblies (has_bom=1): Returns their own active_bom
    For raw materials (has_bom=0): Returns parent assembly's active_bom

    If a child item is used in multiple parent BOMs, returns the first
    active parent BOM found (ordered by most recently modified).

    Args:
        component_master: Component Master document
        project: Project name

    Returns:
        str: BOM name, or None if no BOM found
    """
    # If this item has its own BOM, use that
    if component_master.has_bom and component_master.active_bom:
        return component_master.active_bom

    # For raw materials, find parent assembly's BOM
    # Check bom_usage table to see which parent BOMs use this item
    if not component_master.bom_usage:
        return None

    # Get all parent BOMs from bom_usage
    parent_boms = [row.parent_bom for row in component_master.bom_usage if row.parent_bom]

    if not parent_boms:
        return None

    # Find active parent BOMs (is_active=1, is_default=1, docstatus=1)
    active_parent_bom = frappe.db.get_value(
        "BOM",
        {
            "name": ["in", parent_boms],
            "is_active": 1,
            "is_default": 1,
            "docstatus": 1
        },
        "name",
        order_by="modified desc"  # Most recently modified first
    )

    if active_parent_bom:
        return active_parent_bom

    # Fallback: return the first parent BOM (even if not active)
    return parent_boms[0]
