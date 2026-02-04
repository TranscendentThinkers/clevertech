"""
BOM Event Hooks for Project Component Master

Handles updating BOM Usage child table when BOMs are created, updated, or cancelled.
Uses "silent skip" pattern - only updates if Component Master exists for the component.
Shows info message when project BOMs are not tracked (helps catch accidental omissions).
"""

import frappe
from frappe import _
import hashlib
import json


def on_bom_validate(doc, method=None):
    """
    Called during BOM validation (before submit).
    Implements tiered blocking for BOM version changes.

    If a different BOM was already active for this item+project:
    - Checks child items for active MR/RFQ/PO
    - Blocks submission if procurement exists
    - Guides user to deactivate old BOM first (uncheck "Is Active")

    This prevents BOM version changes when procurement is in progress.
    """
    if not doc.project:
        # No project linked - skip validation (standard product BOM)
        return

    # Check if this BOM is tracked in Component Master
    component_master = get_component_master(doc.project, doc.item)
    if not component_master:
        # Not tracked - skip validation
        return

    # Check for BOM version change
    old_bom = component_master.active_bom
    if not old_bom or old_bom == doc.name:
        # No version change, or same BOM being resubmitted
        return

    # BOM version change detected - check if old BOM is still active
    try:
        old_bom_doc = frappe.get_doc("BOM", old_bom)
        if old_bom_doc.is_active:
            # Old BOM is still active - check for procurement blocking
            blocking_result = _check_bom_version_blocking(doc.project, old_bom)

            if not blocking_result["can_proceed"]:
                # Build error message with procurement details
                error_msg = _(
                    "<b>Cannot submit new BOM version while old BOM is active.</b><br><br>"
                    "Another BOM (<b>{0}</b>) is currently active for item <b>{1}</b> in project <b>{2}</b>.<br><br>"
                ).format(old_bom, doc.item, doc.project)

                if blocking_result["procurement_docs"]:
                    error_msg += _("<b>Reason:</b> The following child items have active procurement documents:<br><ul>")

                    # Group by item code
                    items_with_docs = {}
                    for proc_doc in blocking_result["procurement_docs"]:
                        item = proc_doc["item_code"]
                        if item not in items_with_docs:
                            items_with_docs[item] = []
                        items_with_docs[item].append(proc_doc)

                    for item, docs in items_with_docs.items():
                        doc_list = ", ".join([f"{d['doctype']} {d['name']}" for d in docs])
                        error_msg += f"<li><b>{item}</b>: {doc_list}</li>"

                    error_msg += "</ul><br>"

                error_msg += _(
                    "<b>To proceed:</b><br>"
                    "1. Open the old BOM: <b>{0}</b><br>"
                    "2. Uncheck the <b>'Is Active'</b> flag<br>"
                    "3. Save the old BOM<br>"
                    "4. Then submit this new BOM<br><br>"
                    "This ensures version history is properly maintained and prevents conflicts."
                ).format(old_bom)

                frappe.throw(error_msg, title=_("BOM Version Change Blocked"))

    except frappe.DoesNotExistError:
        # Old BOM doesn't exist anymore - allow submission
        pass


def on_bom_submit(doc, method=None):
    """
    Called when a BOM is submitted.
    Updates BOM Usage table for all items in the BOM that have Component Masters.
    Shows info message if this is a project BOM that's not tracked.

    BOM Version Handling:
    - If a different BOM was already active for this item+project, the old BOM's
      bom_usage entries are removed from children before adding the new BOM's entries.
    - Warns user about the version change and any existing MRs/POs.
    """
    # Store BOM structure hash on the BOM itself (source of truth for change detection)
    # This runs for ALL submitted BOMs, not just project BOMs
    bom_hash = calculate_bom_structure_hash(doc)
    if bom_hash:
        doc.db_set('custom_bom_structure_hash', bom_hash, update_modified=False)

    if not doc.project:
        # No project linked - skip silently (standard product BOM)
        return

    # Check if this BOM itself is tracked in Component Master
    component_master = get_component_master(doc.project, doc.item)
    if not component_master:
        # Project BOM but not tracked - inform user
        frappe.msgprint(
            _("This BOM is linked to project <b>{0}</b> but is not tracked in Project Component Master. Procurement monitoring is not enabled for <b>{1}</b>.").format(
                doc.project, doc.item
            ),
            title=_("BOM Not Tracked for Procurement"),
            indicator="blue",
            alert=True
        )
        return  # Silent skip for processing

    # --- Backfill Missing BOM Version History ---
    # If version history is empty but BOMs exist, backfill them
    if not component_master.bom_version_history:
        _backfill_bom_version_history(doc.project, doc.item, doc.name)
        # Reload Component Master after backfill
        component_master = get_component_master(doc.project, doc.item)

    # --- BOM Version Change Detection ---
    old_bom = component_master.active_bom
    if old_bom and old_bom != doc.name:
        # A different BOM was active — this is a version change
        _handle_bom_version_change(doc.project, doc.item, old_bom, doc.name)
    elif not old_bom:
        # First BOM being linked — add initial version to history
        _add_initial_bom_version(doc.project, doc.item, doc.name)

    # Consolidate duplicate items in BOM (sum quantities)
    # If same item appears multiple times, we need total qty for bom_usage
    item_quantities = {}
    for item in doc.items:
        if item.item_code in item_quantities:
            item_quantities[item.item_code] += float(item.qty or 0)
        else:
            item_quantities[item.item_code] = float(item.qty or 0)

    # Process consolidated items
    for item_code, total_qty in item_quantities.items():
        add_or_update_bom_usage(
            project=doc.project,
            item_code=item_code,
            parent_bom=doc.name,
            qty_per_unit=total_qty
        )

    # Update BOM structure hash and related fields for the BOM item itself
    update_component_master_bom_fields(
        project=doc.project,
        item_code=doc.item,
        bom_name=doc.name
    )

    # Commit all Component Master updates to ensure calculations persist
    frappe.db.commit()


def on_bom_cancel(doc, method=None):
    """
    Called when a BOM is cancelled.
    Removes BOM Usage entries for all items in this BOM.
    Silent skip if not a project BOM or not tracked.

    BOM Version Handling:
    - If another active+default BOM exists for the same item+project,
      sets that as the new active_bom instead of clearing.
    - Populates bom_usage entries from the fallback BOM.
    """
    if not doc.project:
        return

    # Check if this BOM is tracked
    component_master = get_component_master(doc.project, doc.item)
    if not component_master:
        return  # Silent skip

    # Remove BOM usage entries for all child items in the BOM
    for item in doc.items:
        remove_bom_usage(
            project=doc.project,
            item_code=item.item_code,
            parent_bom=doc.name
        )

    # --- BOM Version Fallback ---
    # Find another active+default BOM for the same item+project
    fallback_bom = _find_fallback_bom(doc.project, doc.item, exclude_bom=doc.name)

    if fallback_bom:
        # Switch to fallback BOM
        update_component_master_bom_fields(
            project=doc.project,
            item_code=doc.item,
            bom_name=fallback_bom.name
        )

        # Populate bom_usage entries from the fallback BOM
        fallback_doc = frappe.get_doc("BOM", fallback_bom.name)
        for item in fallback_doc.items:
            add_or_update_bom_usage(
                project=doc.project,
                item_code=item.item_code,
                parent_bom=fallback_bom.name,
                qty_per_unit=item.qty
            )

        frappe.msgprint(
            _("BOM <b>{0}</b> was cancelled. Active BOM switched to <b>{1}</b> for item {2}.").format(
                doc.name, fallback_bom.name, frappe.bold(doc.item)
            ),
            title=_("BOM Version Fallback"),
            indicator="blue",
            alert=True
        )
    else:
        # No fallback — clear BOM fields
        clear_component_master_bom_fields(
            project=doc.project,
            item_code=doc.item
        )


def on_bom_update(doc, method=None):
    """
    Called when a BOM is updated after submission.
    Refreshes BOM Usage entries and checks for structure changes.
    Silent skip if not a project BOM or not tracked.
    """
    if not doc.project:
        return

    # Get the Component Master for this BOM's item
    component_master = get_component_master(doc.project, doc.item)
    if not component_master:
        return  # Silent skip - no Component Master exists

    # Calculate new BOM structure hash
    new_hash = calculate_bom_structure_hash(doc)
    old_hash = component_master.bom_structure_hash

    # If structure changed, flag for review
    if old_hash and new_hash != old_hash:
        frappe.msgprint(
            _("BOM structure has changed for <b>{0}</b>. Component Master <b>{1}</b> may need review.").format(
                doc.item, component_master.name
            ),
            title=_("BOM Structure Changed"),
            indicator="orange",
            alert=True
        )

    # Refresh BOM usage entries (remove old, add new)
    # This handles items added/removed from BOM
    refresh_bom_usage(doc)

    # Update hash and other BOM fields
    update_component_master_bom_fields(
        project=doc.project,
        item_code=doc.item,
        bom_name=doc.name
    )


# ==================== BOM Version Handling ====================

def _log_bom_version_change(project, item_code, old_bom_name, new_bom_name, remarks=None):
    """
    Log BOM version change to the bom_version_history child table.

    1. Captures procurement snapshot for the old version (before deactivation)
    2. Marks the old version as deactivated (sets deactivated_on, is_current=0)
    3. Adds the new version as current (is_current=1, activated_on=now)

    Args:
        project: Project name
        item_code: Item code of the assembly
        old_bom_name: Name of the previous active BOM
        new_bom_name: Name of the new BOM being activated
        remarks: Optional remarks for the version change
    """
    component_master = get_component_master(project, item_code)
    if not component_master:
        return

    now = frappe.utils.now_datetime()

    # Capture procurement snapshot for old BOM before deactivation
    procurement_snapshot = _capture_procurement_snapshot(project, old_bom_name)

    # Mark old version as deactivated and attach snapshot
    for row in component_master.bom_version_history:
        if row.bom_name == old_bom_name and row.is_current:
            row.deactivated_on = now
            row.is_current = 0
            row.procurement_snapshot = json.dumps(procurement_snapshot)
            break

    # Calculate new version number
    max_version = 0
    for row in component_master.bom_version_history:
        if row.version_number and row.version_number > max_version:
            max_version = row.version_number
    new_version_number = max_version + 1

    # Get structure hash for new BOM
    try:
        new_bom_doc = frappe.get_doc("BOM", new_bom_name)
        structure_hash = calculate_bom_structure_hash(new_bom_doc)
    except frappe.DoesNotExistError:
        structure_hash = None

    # Add new version to history
    component_master.append("bom_version_history", {
        "bom_name": new_bom_name,
        "version_number": new_version_number,
        "structure_hash": structure_hash,
        "activated_on": now,
        "is_current": 1,
        "change_remarks": remarks or ""
    })

    component_master.flags.ignore_validate = True
    component_master.flags.ignore_mandatory = True
    component_master.save(ignore_permissions=True)


def _capture_procurement_snapshot(project, bom_name):
    """
    Capture a snapshot of procurement status for all child items in a BOM.

    This is called when a BOM version is being deactivated, to preserve
    the procurement state at that point in time for audit/reconciliation.

    Args:
        project: Project name
        bom_name: BOM name to capture snapshot for

    Returns:
        dict: {
            "snapshot_time": "2026-02-02 10:30:00",
            "bom_name": "BOM-001",
            "child_items": [
                {
                    "item_code": "A00001",
                    "qty_per_unit": 2.0,
                    "bom_qty_required": 4.0,
                    "total_qty_limit": 4.0,
                    "mr_refs": ["MR-001", "MR-002"],
                    "mr_total_qty": 3.0,
                    "rfq_refs": ["RFQ-001"],
                    "rfq_total_qty": 2.0,
                    "po_refs": ["PO-001"],
                    "po_total_qty": 2.0,
                    "pr_refs": ["PR-001"],
                    "received_qty": 1.0
                },
                ...
            ]
        }
    """
    snapshot = {
        "snapshot_time": str(frappe.utils.now_datetime()),
        "bom_name": bom_name,
        "child_items": []
    }

    if not bom_name:
        return snapshot

    # Get BOM child items (consolidated)
    try:
        bom_doc = frappe.get_doc("BOM", bom_name)
    except frappe.DoesNotExistError:
        return snapshot

    # Consolidate duplicate items
    item_qty_map = {}
    for item in bom_doc.items:
        if item.item_code in item_qty_map:
            item_qty_map[item.item_code] += float(item.qty or 0)
        else:
            item_qty_map[item.item_code] = float(item.qty or 0)

    # For each child item, capture procurement data
    for item_code, qty_per_unit in item_qty_map.items():
        child_snapshot = {
            "item_code": item_code,
            "qty_per_unit": qty_per_unit,
            "bom_qty_required": 0,
            "total_qty_limit": 0,
            "mr_refs": [],
            "mr_total_qty": 0,
            "rfq_refs": [],
            "rfq_total_qty": 0,
            "po_refs": [],
            "po_total_qty": 0,
            "pr_refs": [],
            "received_qty": 0
        }

        # Get Component Master data
        child_cm = get_component_master(project, item_code)
        if child_cm:
            child_snapshot["bom_qty_required"] = float(child_cm.bom_qty_required or 0)
            child_snapshot["total_qty_limit"] = float(child_cm.total_qty_limit or 0)

        # Get Material Requests
        mrs = frappe.db.sql("""
            SELECT mr.name, mri.qty
            FROM `tabMaterial Request` mr
            INNER JOIN `tabMaterial Request Item` mri ON mri.parent = mr.name
            WHERE mri.item_code = %(item_code)s
            AND mr.custom_project_ = %(project)s
            AND mr.docstatus != 2
        """, {"item_code": item_code, "project": project}, as_dict=True)

        for mr in mrs:
            child_snapshot["mr_refs"].append(mr.name)
            child_snapshot["mr_total_qty"] += float(mr.qty or 0)

        # Get RFQs
        rfqs = frappe.db.sql("""
            SELECT rfq.name, rfqi.qty
            FROM `tabRequest for Quotation` rfq
            INNER JOIN `tabRequest for Quotation Item` rfqi ON rfqi.parent = rfq.name
            WHERE rfqi.item_code = %(item_code)s
            AND rfq.custom_project = %(project)s
            AND rfq.docstatus != 2
        """, {"item_code": item_code, "project": project}, as_dict=True)

        for rfq in rfqs:
            child_snapshot["rfq_refs"].append(rfq.name)
            child_snapshot["rfq_total_qty"] += float(rfq.qty or 0)

        # Get Purchase Orders
        pos = frappe.db.sql("""
            SELECT po.name, poi.qty
            FROM `tabPurchase Order` po
            INNER JOIN `tabPurchase Order Item` poi ON poi.parent = po.name
            WHERE poi.item_code = %(item_code)s
            AND po.project = %(project)s
            AND po.docstatus != 2
        """, {"item_code": item_code, "project": project}, as_dict=True)

        for po in pos:
            child_snapshot["po_refs"].append(po.name)
            child_snapshot["po_total_qty"] += float(po.qty or 0)

        # Get Purchase Receipts (received qty)
        prs = frappe.db.sql("""
            SELECT pr.name, pri.qty
            FROM `tabPurchase Receipt` pr
            INNER JOIN `tabPurchase Receipt Item` pri ON pri.parent = pr.name
            WHERE pri.item_code = %(item_code)s
            AND pr.project = %(project)s
            AND pr.docstatus = 1
        """, {"item_code": item_code, "project": project}, as_dict=True)

        for pr in prs:
            child_snapshot["pr_refs"].append(pr.name)
            child_snapshot["received_qty"] += float(pr.qty or 0)

        # De-duplicate refs (in case same doc appears multiple times)
        child_snapshot["mr_refs"] = list(set(child_snapshot["mr_refs"]))
        child_snapshot["rfq_refs"] = list(set(child_snapshot["rfq_refs"]))
        child_snapshot["po_refs"] = list(set(child_snapshot["po_refs"]))
        child_snapshot["pr_refs"] = list(set(child_snapshot["pr_refs"]))

        snapshot["child_items"].append(child_snapshot)

    return snapshot


def _add_initial_bom_version(project, item_code, bom_name):
    """
    Add the initial BOM version to history when a BOM is first linked.
    Called when active_bom was previously empty.

    Args:
        project: Project name
        item_code: Item code of the assembly
        bom_name: Name of the BOM being activated
    """
    component_master = get_component_master(project, item_code)
    if not component_master:
        return

    # Check if this BOM is already in history
    for row in component_master.bom_version_history:
        if row.bom_name == bom_name:
            return  # Already exists

    now = frappe.utils.now_datetime()

    # Get structure hash
    try:
        bom_doc = frappe.get_doc("BOM", bom_name)
        structure_hash = calculate_bom_structure_hash(bom_doc)
    except frappe.DoesNotExistError:
        structure_hash = None

    # Add as version 1
    component_master.append("bom_version_history", {
        "bom_name": bom_name,
        "version_number": 1,
        "structure_hash": structure_hash,
        "activated_on": now,
        "is_current": 1,
        "change_remarks": "Initial BOM version"
    })

    component_master.flags.ignore_validate = True
    component_master.flags.ignore_mandatory = True
    component_master.save(ignore_permissions=True)


def _backfill_bom_version_history(project, item_code, current_bom_name):
    """
    Backfill version history for existing BOMs that were created before Component Master.

    This handles the case where:
    1. BOMs were created manually (before Component Master existed)
    2. Component Master was created later via BOM Upload
    3. Need to retroactively add old BOMs to version history

    Args:
        project: Project name
        item_code: Item code of the assembly
        current_bom_name: Name of the BOM being submitted now
    """
    component_master = get_component_master(project, item_code)
    if not component_master:
        return

    # Get all submitted BOMs for this item+project (ordered by creation)
    all_boms = frappe.get_all(
        "BOM",
        filters={
            "item": item_code,
            "project": project,
            "docstatus": 1
        },
        fields=["name", "creation", "is_active", "is_default"],
        order_by="creation asc"
    )

    if not all_boms:
        return

    # Filter out BOMs already in version history
    existing_bom_names = {row.bom_name for row in component_master.bom_version_history}
    boms_to_add = [b for b in all_boms if b.name not in existing_bom_names]

    if not boms_to_add:
        return

    # Add old BOMs to version history
    version_num = 1
    for bom in boms_to_add:
        try:
            bom_doc = frappe.get_doc("BOM", bom.name)
            structure_hash = calculate_bom_structure_hash(bom_doc)
        except frappe.DoesNotExistError:
            structure_hash = None

        # Determine if this is the current BOM
        is_current = 1 if bom.name == current_bom_name else 0
        deactivated_on = None if is_current else bom.creation  # Use creation as deactivation placeholder

        component_master.append("bom_version_history", {
            "bom_name": bom.name,
            "version_number": version_num,
            "structure_hash": structure_hash,
            "activated_on": bom.creation,
            "deactivated_on": deactivated_on,
            "is_current": is_current,
            "change_remarks": f"Backfilled from existing BOM (created {bom.creation})"
        })

        version_num += 1

    component_master.flags.ignore_validate = True
    component_master.flags.ignore_mandatory = True
    component_master.save(ignore_permissions=True)

    # Log the backfill action
    frappe.msgprint(
        _("Backfilled {0} BOM version(s) to version history for item <b>{1}</b>.").format(
            len(boms_to_add), item_code
        ),
        title=_("BOM Version History Updated"),
        indicator="blue",
        alert=True
    )


def _handle_bom_version_change(project, item_code, old_bom_name, new_bom_name, remarks=None):
    """
    Handle switching from one BOM version to another.

    1. Logs version change to bom_version_history child table (with procurement snapshot)
    2. Removes old BOM's bom_usage entries from child Component Masters
    3. Alerts about:
       - Items REMOVED from BOM that have existing procurement
       - Items with QTY REDUCED that have over-procurement
    4. Informs user about the version change

    Args:
        project: Project name
        item_code: Item code of the assembly whose BOM is changing
        old_bom_name: Name of the previous active BOM
        new_bom_name: Name of the new BOM being activated
        remarks: Optional remarks for the version change
    """
    # Log the version change to history (includes procurement snapshot)
    _log_bom_version_change(project, item_code, old_bom_name, new_bom_name, remarks)

    try:
        old_bom_doc = frappe.get_doc("BOM", old_bom_name)
    except frappe.DoesNotExistError:
        return  # Old BOM doesn't exist anymore, nothing to clean up

    # Build qty map for old BOM (consolidate duplicates)
    old_item_qty = {}
    for item in old_bom_doc.items:
        if item.item_code in old_item_qty:
            old_item_qty[item.item_code] += float(item.qty or 0)
        else:
            old_item_qty[item.item_code] = float(item.qty or 0)

    old_items = set(old_item_qty.keys())

    # Remove bom_usage entries for old BOM from all child Component Masters
    for item_code_child in old_items:
        remove_bom_usage(
            project=project,
            item_code=item_code_child,
            parent_bom=old_bom_name
        )

    # Get new BOM items and quantities
    try:
        new_bom_doc = frappe.get_doc("BOM", new_bom_name)
        new_item_qty = {}
        for item in new_bom_doc.items:
            if item.item_code in new_item_qty:
                new_item_qty[item.item_code] += float(item.qty or 0)
            else:
                new_item_qty[item.item_code] = float(item.qty or 0)
        new_items = set(new_item_qty.keys())
    except frappe.DoesNotExistError:
        new_items = set()
        new_item_qty = {}

    # Collect all alerts
    removed_items_alerts = []
    qty_reduced_alerts = []

    # Check 1: Items REMOVED from BOM (in old but not in new)
    removed_items = old_items - new_items
    for removed_item in removed_items:
        mr_count = frappe.db.count(
            "Material Request Item",
            filters={
                "item_code": removed_item,
                "parenttype": "Material Request",
                "docstatus": ["<", 2],
            }
        )
        po_count = frappe.db.count(
            "Purchase Order Item",
            filters={
                "item_code": removed_item,
                "parenttype": "Purchase Order",
                "docstatus": ["<", 2],
            }
        )
        if mr_count or po_count:
            removed_items_alerts.append(
                f"<b>{removed_item}</b> ({mr_count} MR(s), {po_count} PO(s))"
            )

    # Check 2: Items with QTY REDUCED (in both BOMs but new qty < old qty)
    common_items = old_items & new_items
    for common_item in common_items:
        old_qty = old_item_qty.get(common_item, 0)
        new_qty = new_item_qty.get(common_item, 0)

        if new_qty < old_qty:
            # Qty reduced - check if existing procurement exceeds new limit
            # Get total qty already procured (MR + PO)
            mr_qty_result = frappe.db.sql("""
                SELECT COALESCE(SUM(mri.qty), 0) as total_qty
                FROM `tabMaterial Request` mr
                INNER JOIN `tabMaterial Request Item` mri ON mri.parent = mr.name
                WHERE mri.item_code = %(item_code)s
                AND mr.custom_project_ = %(project)s
                AND mr.docstatus != 2
            """, {"item_code": common_item, "project": project}, as_dict=True)

            po_qty_result = frappe.db.sql("""
                SELECT COALESCE(SUM(poi.qty), 0) as total_qty
                FROM `tabPurchase Order` po
                INNER JOIN `tabPurchase Order Item` poi ON poi.parent = po.name
                WHERE poi.item_code = %(item_code)s
                AND po.project = %(project)s
                AND po.docstatus != 2
            """, {"item_code": common_item, "project": project}, as_dict=True)

            total_procured = (mr_qty_result[0].total_qty if mr_qty_result else 0) + \
                            (po_qty_result[0].total_qty if po_qty_result else 0)

            # Get parent's project_qty to calculate new requirement
            parent_cm = get_component_master(project, item_code)
            parent_project_qty = float(parent_cm.project_qty or 1) if parent_cm else 1

            # New total requirement = new_qty * parent_project_qty
            new_requirement = new_qty * parent_project_qty
            old_requirement = old_qty * parent_project_qty

            if total_procured > new_requirement:
                over_qty = total_procured - new_requirement
                qty_reduced_alerts.append(
                    f"<b>{common_item}</b>: BOM qty {old_qty} → {new_qty} "
                    f"(requirement {old_requirement} → {new_requirement}). "
                    f"Procured: {total_procured}. "
                    f"<span style='color:red'><b>OVER by {over_qty}</b></span>"
                )

    # Show combined alerts if any
    if removed_items_alerts or qty_reduced_alerts:
        alert_parts = []

        if removed_items_alerts:
            alert_parts.append(
                _("<b>⚠️ Items REMOVED from BOM</b> (have existing procurement):<br>"
                  "<ul><li>{0}</li></ul>").format("</li><li>".join(removed_items_alerts))
            )

        if qty_reduced_alerts:
            alert_parts.append(
                _("<b>⚠️ Items with QTY REDUCED</b> (over-procurement detected):<br>"
                  "<ul><li>{0}</li></ul>").format("</li><li>".join(qty_reduced_alerts))
            )

        frappe.msgprint(
            _(
                "BOM version changed from <b>{0}</b> to <b>{1}</b> for item {2}.<br><br>"
                "<b>🔴 REVIEW REQUIRED:</b><br><br>"
                "{3}<br>"
                "Procurement snapshot saved in BOM Version History for audit.<br>"
                "Please review and adjust these procurement documents."
            ).format(
                old_bom_name,
                new_bom_name,
                frappe.bold(item_code),
                "<br>".join(alert_parts),
            ),
            title=_("BOM Version Change — Review Procurement"),
            indicator="red",
            alert=True
        )
        return

    # Simple version change notification (no items removed or no procurement impact)
    frappe.msgprint(
        _("Active BOM updated from <b>{0}</b> to <b>{1}</b> for item {2}.<br>"
          "Procurement snapshot saved in BOM Version History.").format(
            old_bom_name, new_bom_name, frappe.bold(item_code)
        ),
        title=_("BOM Version Updated"),
        indicator="blue",
        alert=True
    )


def _find_fallback_bom(project, item_code, exclude_bom):
    """
    Find another active+default BOM for the same item+project.
    Used when the current active BOM is cancelled.

    Args:
        project: Project name
        item_code: Item code
        exclude_bom: BOM name to exclude (the one being cancelled)

    Returns:
        dict with 'name' field, or None if no fallback found
    """
    # First try: active + default BOM for same item + project
    fallback = frappe.db.get_value(
        "BOM",
        {
            "item": item_code,
            "project": project,
            "docstatus": 1,
            "is_active": 1,
            "is_default": 1,
            "name": ["!=", exclude_bom],
        },
        ["name"],
        as_dict=True,
    )

    if fallback:
        return fallback

    # Second try: any active BOM for same item + project (not necessarily default)
    fallback = frappe.db.get_value(
        "BOM",
        {
            "item": item_code,
            "project": project,
            "docstatus": 1,
            "is_active": 1,
            "name": ["!=", exclude_bom],
        },
        ["name"],
        as_dict=True,
        order_by="modified desc",
    )

    return fallback


# ==================== Helper Functions ====================

def get_component_master(project, item_code):
    """
    Get Component Master for a project and item.
    Returns None if doesn't exist (silent skip pattern).
    """
    try:
        name = frappe.db.get_value(
            "Project Component Master",
            {"project": project, "item_code": item_code},
            "name"
        )
        if name:
            return frappe.get_doc("Project Component Master", name)
        return None
    except Exception:
        return None


def add_or_update_bom_usage(project, item_code, parent_bom, qty_per_unit, parent_item=None):
    """
    Add or update a BOM Usage entry in the Component Master.
    Silent skip if Component Master doesn't exist.

    Args:
        project: Project name
        item_code: Item code of the component (child item in BOM)
        parent_bom: BOM name that contains this component
        qty_per_unit: Quantity per unit of parent assembly
        parent_item: Item code of the parent assembly (optional, will fetch from BOM if not provided)
    """
    component_master = get_component_master(project, item_code)
    if not component_master:
        return  # Silent skip

    # Get parent item from BOM if not provided
    if not parent_item and parent_bom:
        parent_item = frappe.db.get_value("BOM", parent_bom, "item")

    # Get parent Component Master for hierarchy traversal
    parent_component = None
    parent_cm = None
    if parent_item:
        parent_cm = get_component_master(project, parent_item)
        if parent_cm:
            parent_component = parent_cm.name

    # Derive M-code and G-code from parent hierarchy
    m_code, g_code = _derive_codes_from_parent(parent_cm, parent_item)

    # Check if this BOM usage already exists
    existing_row = None
    for row in component_master.bom_usage:
        if row.parent_bom == parent_bom:
            existing_row = row
            break

    if existing_row:
        # Update existing row (qty, parent_component, m_code, g_code)
        has_changes = False
        if existing_row.qty_per_unit != qty_per_unit:
            existing_row.qty_per_unit = qty_per_unit
            has_changes = True
        if existing_row.parent_component != parent_component:
            existing_row.parent_component = parent_component
            has_changes = True
        if existing_row.m_code != m_code:
            existing_row.m_code = m_code
            has_changes = True
        if existing_row.g_code != g_code:
            existing_row.g_code = g_code
            has_changes = True

        if has_changes:
            # Note: Quantity calculations (bom_qty_required, total_qty_limit, etc.)
            # are performed at the end of BOM upload via recalculate_component_masters_for_project()
            component_master.flags.ignore_validate = True
            component_master.flags.ignore_mandatory = True
            component_master.save(ignore_permissions=True)

            frappe.msgprint(
                _("Updated BOM Usage in Component Master {0}").format(component_master.name),
                indicator="green",
                alert=True
            )
    else:
        # Add new row with all hierarchy fields
        component_master.append("bom_usage", {
            "parent_bom": parent_bom,
            "parent_component": parent_component,
            "m_code": m_code,
            "g_code": g_code,
            "qty_per_unit": qty_per_unit
        })

        # Note: Quantity calculations (bom_qty_required, total_qty_limit, etc.)
        # are performed at the end of BOM upload via recalculate_component_masters_for_project()
        component_master.flags.ignore_validate = True
        component_master.flags.ignore_mandatory = True
        component_master.save(ignore_permissions=True)

        frappe.msgprint(
            _("Added BOM Usage to Component Master {0}").format(component_master.name),
            indicator="green",
            alert=True
        )


def _derive_codes_from_parent(parent_cm, parent_item):
    """
    Derive M-code and G-code based on parent item and its Component Master.

    Hierarchy: Machine Code → M-Code → G-Code → D-Code/Raw Materials

    Rules:
    - If parent starts with "M" → m_code = parent_item, g_code = NULL
    - If parent starts with "G" → m_code = parent's m_code, g_code = parent_item
    - Otherwise → traverse parent_component chain to find nearest M and G

    Args:
        parent_cm: Parent Component Master (may be None)
        parent_item: Parent item code

    Returns:
        tuple: (m_code, g_code)
    """
    if not parent_item:
        return None, None

    # If parent is M-code (root assembly)
    if parent_item.startswith("M"):
        return parent_item, None

    # If parent is G-code (sub-assembly)
    if parent_item.startswith("G"):
        # Get M-code from parent CM or traverse
        m_code = None
        if parent_cm:
            # Try to get m_code from parent CM
            m_code = parent_cm.m_code
            if not m_code:
                # Traverse up to find M-code
                m_code = _traverse_for_m_code(parent_cm)
        return m_code, parent_item

    # Parent is below G-level (D-code, raw material, etc.)
    # Need to traverse up to find both M-code and G-code
    if parent_cm:
        m_code = parent_cm.m_code or _traverse_for_m_code(parent_cm)
        g_code = parent_cm.g_code or _traverse_for_g_code(parent_cm)
        return m_code, g_code

    return None, None


def _traverse_for_m_code(cm):
    """
    Traverse up the parent_component chain to find the M-code (item starting with M).
    """
    if not cm:
        return None

    visited = set()
    current = cm

    while current and current.name not in visited:
        visited.add(current.name)

        # Check if current item is M-code
        if current.item_code and current.item_code.startswith("M"):
            return current.item_code

        # Check if current CM has m_code set
        if current.m_code:
            return current.m_code

        # Move to parent
        if not current.parent_component:
            break
        try:
            current = frappe.get_doc("Project Component Master", current.parent_component)
        except frappe.DoesNotExistError:
            break

    return None


def _traverse_for_g_code(cm):
    """
    Traverse up the parent_component chain to find the G-code (item starting with G).
    """
    if not cm:
        return None

    visited = set()
    current = cm

    while current and current.name not in visited:
        visited.add(current.name)

        # Check if current item is G-code
        if current.item_code and current.item_code.startswith("G"):
            return current.item_code

        # Check if current CM has g_code set
        if current.g_code:
            return current.g_code

        # Move to parent
        if not current.parent_component:
            break
        try:
            current = frappe.get_doc("Project Component Master", current.parent_component)
        except frappe.DoesNotExistError:
            break

    return None


def remove_bom_usage(project, item_code, parent_bom):
    """
    Remove a BOM Usage entry from the Component Master.
    Silent skip if Component Master doesn't exist.
    """
    component_master = get_component_master(project, item_code)
    if not component_master:
        return  # Silent skip

    # Find and remove the row
    rows_to_remove = []
    for idx, row in enumerate(component_master.bom_usage):
        if row.parent_bom == parent_bom:
            rows_to_remove.append(idx)

    # Remove in reverse order to maintain indices
    for idx in reversed(rows_to_remove):
        component_master.remove(component_master.bom_usage[idx])

    if rows_to_remove:
        component_master.flags.ignore_validate = True
        component_master.flags.ignore_mandatory = True
        component_master.save(ignore_permissions=True)

        frappe.msgprint(
            _("Removed BOM Usage from Component Master {0}").format(component_master.name),
            indicator="blue",
            alert=True
        )


def refresh_bom_usage(bom_doc):
    """
    Refresh all BOM usage entries for a BOM.
    Removes entries for items no longer in BOM, adds/updates current items.
    """
    if not bom_doc.project:
        return

    # Get current item codes in the BOM
    current_items = {item.item_code: item.qty for item in bom_doc.items}

    # Find all Component Masters that reference this BOM
    component_masters = frappe.get_all(
        "Project Component Master",
        filters={"project": bom_doc.project},
        fields=["name", "item_code"]
    )

    for cm in component_masters:
        component_master = frappe.get_doc("Project Component Master", cm.name)

        # Check if this Component Master has a BOM usage entry for this BOM
        has_changes = False
        rows_to_remove = []

        for idx, row in enumerate(component_master.bom_usage):
            if row.parent_bom == bom_doc.name:
                # This Component Master references the updated BOM
                if cm.item_code in current_items:
                    # Item still in BOM - update qty if changed
                    if row.qty_per_unit != current_items[cm.item_code]:
                        row.qty_per_unit = current_items[cm.item_code]
                        has_changes = True
                else:
                    # Item no longer in BOM - mark for removal
                    rows_to_remove.append(idx)
                    has_changes = True

        # Remove obsolete rows
        for idx in reversed(rows_to_remove):
            component_master.remove(component_master.bom_usage[idx])

        # Save if changes made
        if has_changes:
            component_master.flags.ignore_validate = True
            component_master.flags.ignore_mandatory = True
            component_master.save(ignore_permissions=True)


def update_component_master_bom_fields(project, item_code, bom_name):
    """
    Update BOM-related fields in Component Master:
    - has_bom
    - active_bom
    - bom_structure_hash
    - Trigger quantity calculations
    """
    component_master = get_component_master(project, item_code)
    if not component_master:
        return  # Silent skip

    # Get the BOM document
    bom_doc = frappe.get_doc("BOM", bom_name)

    # Update fields
    component_master.has_bom = 1
    component_master.active_bom = bom_name
    component_master.bom_structure_hash = calculate_bom_structure_hash(bom_doc)

    component_master.flags.ignore_validate = True
    component_master.flags.ignore_mandatory = True
    component_master.save(ignore_permissions=True)

    # Note: Quantity calculations (bom_qty_required, total_qty_limit) are done
    # at the end of BOM upload via recalculate_component_masters_for_project()


def clear_component_master_bom_fields(project, item_code):
    """
    Clear BOM fields when BOM is cancelled.
    """
    component_master = get_component_master(project, item_code)
    if not component_master:
        return  # Silent skip

    component_master.has_bom = 0
    component_master.active_bom = None
    component_master.bom_structure_hash = None

    component_master.flags.ignore_validate = True
    component_master.flags.ignore_mandatory = True
    component_master.save(ignore_permissions=True)


def calculate_bom_structure_hash(bom_doc):
    """
    Calculate MD5 hash of BOM structure.
    Based on sorted list of (item_code, qty) tuples.
    """
    if not bom_doc.items:
        return None

    # Create list of (item_code, qty) tuples, sorted by item_code
    structure = sorted(
        [(item.item_code, float(item.qty)) for item in bom_doc.items],
        key=lambda x: x[0]
    )

    # Convert to JSON string and hash
    structure_str = json.dumps(structure, sort_keys=True)
    return hashlib.md5(structure_str.encode()).hexdigest()


def recalculate_component_masters_for_project(project):
    """
    Recalculate all Component Master quantities for a project.

    Call this AFTER frappe.db.commit() to ensure all BOM data is saved.
    This runs synchronously to ensure values are immediately available.

    Args:
        project: Project name

    Returns:
        dict: Summary of recalculations (updated count, errors)
    """
    component_masters = frappe.get_all(
        "Project Component Master",
        filters={"project": project},
        pluck="name"
    )

    updated = 0
    errors = []

    for cm_name in component_masters:
        try:
            cm = frappe.get_doc("Project Component Master", cm_name)

            # Calculate all quantities
            cm.calculate_bom_qty_required()
            cm.calculate_total_qty_limit()
            cm.calculate_procurement_totals()
            cm.update_procurement_status()

            # Use frappe.db.set_value to persist calculated fields (bypasses save() in hooks)
            frappe.db.set_value(cm.doctype, cm.name, {
                "bom_qty_required": cm.bom_qty_required,
                "total_qty_limit": cm.total_qty_limit,
                "total_qty_procured": cm.total_qty_procured,
                "procurement_balance": cm.procurement_balance,
                "procurement_status": cm.procurement_status
            }, update_modified=False)

            updated += 1

        except Exception as e:
            errors.append(f"{cm_name}: {str(e)}")
            frappe.log_error(f"Error recalculating {cm_name}: {str(e)}", "Component Master Recalculation")

    # Final commit to persist all db_set operations
    frappe.db.commit()

    return {
        "updated": updated,
        "total": len(component_masters),
        "errors": errors
    }


def _check_bom_version_blocking(project, old_bom_name):
    """
    Check if BOM version change should be blocked due to active procurement.

    Checks child items of the old BOM for active MR/RFQ/PO.
    This is used during BOM validation to prevent version changes when
    procurement is in progress.

    Args:
        project: Project name
        old_bom_name: Name of the currently active BOM

    Returns:
        dict: {
            "can_proceed": bool,
            "procurement_docs": [...]
        }
    """
    if not old_bom_name:
        return {
            "can_proceed": True,
            "procurement_docs": []
        }

    # Get all child items from old BOM
    old_bom_items = frappe.get_all(
        "BOM Item",
        filters={"parent": old_bom_name},
        fields=["item_code"]
    )

    procurement_docs = []

    # Check each child item for procurement
    for bom_item in old_bom_items:
        child_item = bom_item.item_code

        # Check Material Requests
        mrs = _get_material_requests(project, child_item)
        if mrs:
            for mr in mrs:
                procurement_docs.append({
                    "doctype": "Material Request",
                    "name": mr.name,
                    "status": mr.status or ("Draft" if mr.docstatus == 0 else "Submitted"),
                    "quantity": mr.qty,
                    "item_code": child_item,
                })

        # Check RFQs
        rfqs = _get_rfqs(project, child_item)
        if rfqs:
            for rfq in rfqs:
                procurement_docs.append({
                    "doctype": "Request for Quotation",
                    "name": rfq.name,
                    "status": rfq.status or ("Draft" if rfq.docstatus == 0 else "Submitted"),
                    "quantity": rfq.qty,
                    "item_code": child_item,
                })

        # Check Purchase Orders
        pos = _get_purchase_orders(project, child_item)
        if pos:
            for po in pos:
                procurement_docs.append({
                    "doctype": "Purchase Order",
                    "name": po.name,
                    "status": po.status or ("Draft" if po.docstatus == 0 else "Submitted"),
                    "quantity": po.qty,
                    "item_code": child_item,
                })

    # Block if any procurement exists
    can_proceed = len(procurement_docs) == 0

    return {
        "can_proceed": can_proceed,
        "procurement_docs": procurement_docs
    }


def _get_material_requests(project, item_code):
    """Get active (non-cancelled) Material Requests for the item in the project."""
    return frappe.db.sql("""
        SELECT
            mr.name, mr.docstatus, mr.status,
            mri.qty
        FROM `tabMaterial Request` mr
        INNER JOIN `tabMaterial Request Item` mri ON mri.parent = mr.name
        WHERE mri.item_code = %(item_code)s
        AND mr.custom_project_ = %(project)s
        AND mr.docstatus != 2
    """, {"item_code": item_code, "project": project}, as_dict=True)


def _get_rfqs(project, item_code):
    """Get active (non-cancelled) RFQs for the item in the project."""
    return frappe.db.sql("""
        SELECT
            rfq.name, rfq.docstatus, rfq.status,
            rfqi.qty
        FROM `tabRequest for Quotation` rfq
        INNER JOIN `tabRequest for Quotation Item` rfqi ON rfqi.parent = rfq.name
        WHERE rfqi.item_code = %(item_code)s
        AND rfq.custom_project = %(project)s
        AND rfq.docstatus != 2
    """, {"item_code": item_code, "project": project}, as_dict=True)


def _get_purchase_orders(project, item_code):
    """Get active (non-cancelled) Purchase Orders for the item in the project."""
    return frappe.db.sql("""
        SELECT
            po.name, po.docstatus, po.status,
            poi.qty
        FROM `tabPurchase Order` po
        INNER JOIN `tabPurchase Order Item` poi ON poi.parent = po.name
        WHERE poi.item_code = %(item_code)s
        AND po.project = %(project)s
        AND po.docstatus != 2
    """, {"item_code": item_code, "project": project}, as_dict=True)


# ==================== Utility Functions for Manual Fixes ====================

@frappe.whitelist()
def fix_procurement_bom_versions(component_master_name):
    """
    Utility function to backfill bom_version for existing procurement records.

    Use this to fix procurement records where bom_version is NULL.
    Looks up the parent BOM from bom_usage and sets it retroactively.

    Args:
        component_master_name: Name of the Component Master to fix

    Returns:
        dict: Summary of changes made
    """
    from clevertech.project_component_master.procurement_hooks import _get_bom_version_for_procurement

    cm = frappe.get_doc("Project Component Master", component_master_name)

    # Find procurement records with NULL bom_version
    null_count = 0
    updated_count = 0

    for row in cm.procurement_records:
        if not row.bom_version:
            null_count += 1

            # Get the correct BOM version
            bom_version = _get_bom_version_for_procurement(cm, cm.project)

            if bom_version:
                row.bom_version = bom_version
                updated_count += 1

    if updated_count > 0:
        cm.flags.ignore_validate = True
        cm.flags.ignore_mandatory = True
        cm.save(ignore_permissions=True)
        frappe.db.commit()

    return {
        "status": "success",
        "message": f"Updated {updated_count} of {null_count} procurement records with NULL bom_version",
        "null_count": null_count,
        "updated_count": updated_count,
        "bom_version_used": _get_bom_version_for_procurement(cm, cm.project) if updated_count > 0 else None
    }


@frappe.whitelist()
def fix_bom_version_history(component_master_name):
    """
    Utility function to manually fix BOM version history for a Component Master.

    Use this to retroactively fix cases where:
    - BOMs were created before Component Master existed
    - Version history is incomplete or incorrect

    Args:
        component_master_name: Name of the Component Master to fix

    Returns:
        dict: Summary of changes made
    """
    cm = frappe.get_doc("Project Component Master", component_master_name)

    if not cm.has_bom:
        return {
            "status": "skipped",
            "message": "Component Master does not have BOMs"
        }

    # Get all submitted BOMs for this item+project (ordered by creation)
    all_boms = frappe.get_all(
        "BOM",
        filters={
            "item": cm.item_code,
            "project": cm.project,
            "docstatus": 1
        },
        fields=["name", "creation", "is_active", "is_default"],
        order_by="creation asc"
    )

    if not all_boms:
        return {
            "status": "skipped",
            "message": "No submitted BOMs found for this item"
        }

    # Clear existing version history
    old_history = [(row.bom_name, row.version_number) for row in cm.bom_version_history]
    cm.bom_version_history = []

    # Rebuild version history from scratch
    version_num = 1
    for idx, bom in enumerate(all_boms):
        try:
            bom_doc = frappe.get_doc("BOM", bom.name)
            structure_hash = calculate_bom_structure_hash(bom_doc)
        except frappe.DoesNotExistError:
            structure_hash = None

        # Last BOM in the list is the most recent (current)
        is_last = (idx == len(all_boms) - 1)
        is_current = 1 if is_last else 0

        # Deactivation date: use next BOM's creation date, or None if current
        if is_last:
            deactivated_on = None
        else:
            deactivated_on = all_boms[idx + 1].creation

        cm.append("bom_version_history", {
            "bom_name": bom.name,
            "version_number": version_num,
            "structure_hash": structure_hash,
            "activated_on": bom.creation,
            "deactivated_on": deactivated_on,
            "is_current": is_current,
            "change_remarks": f"Rebuilt version history (originally created {bom.creation.strftime('%Y-%m-%d %H:%M')})"
        })

        version_num += 1

    # Update active_bom to the most recent BOM
    if all_boms:
        cm.active_bom = all_boms[-1].name

    cm.flags.ignore_validate = True
    cm.flags.ignore_mandatory = True
    cm.save(ignore_permissions=True)

    frappe.db.commit()

    return {
        "status": "success",
        "message": f"Rebuilt version history with {len(all_boms)} BOM(s)",
        "old_history": old_history,
        "new_history": [(row.bom_name, row.version_number) for row in cm.bom_version_history],
        "active_bom": cm.active_bom
    }
