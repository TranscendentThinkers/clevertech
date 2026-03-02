"""
Utility functions for Project Component Master management.

Phase 5 Implementation: Machine Code Cascade (2026-02-02)
- Retroactive population of machine_code for existing Component Masters
- User manually sets machine_code on root Component Masters
- This module cascades machine_code to all descendants
"""

import frappe
from frappe import _
from clevertech.project_component_master.bulk_generation import populate_bom_usage_tables


@frappe.whitelist()
def update_component_data(project):
    """
    Cascade machine_code, rebuild parent_component links, rebuild BOM usage, and backfill procurement records.

    Workflow:
    1. Backfill parent_component links from BOM structure
    2. User manually enters machine_code on ROOT Component Masters
    3. This function cascades machine_code to all descendants
    4. Rebuilds BOM Usage tables for entire project
    5. Backfills procurement records (MR, RFQ, PO, PR) for all Component Masters
    6. Recalculates quantities and updates procurement status

    Args:
        project: Project name

    Returns:
        dict: {
            "parent_links_updated": int,
            "machine_code_updated": int,
            "bom_usage_rebuilt": int,
            "procurement_added": int,
            "procurement_skipped": int,
            "summary": str,
            "has_errors": bool,
            "errors": list
        }
    """
    # Step 0: Backfill parent_component links from BOM structure
    parent_links_updated = 0
    errors = []
    try:
        parent_links_updated = backfill_parent_components(project)
    except Exception as e:
        frappe.log_error(
            title=f"Failed to backfill parent_component for {project}",
            message=frappe.get_traceback()
        )
        errors.append(f"Parent backfill: {str(e)}")

    # Step 1: Find all root Component Masters (parent_component IS NULL)
    roots = frappe.get_all(
        "Project Component Master",
        filters={
            "project": project,
            "parent_component": ["is", "not set"],  # Root = no parent
            "has_bom": 1
        },
        fields=["name", "item_code", "machine_code"]
    )

    if not roots:
        return {
            "summary": _("Parent links updated: <b>{0}</b><br>No root Component Masters found for machine code cascade.").format(parent_links_updated),
            "parent_links_updated": parent_links_updated,
            "machine_code_updated": 0,
            "bom_usage_rebuilt": 0,
            "has_errors": False,
            "errors": errors
        }

    # Step 2: Validate all roots have machine_code
    missing_machine_code = [r.item_code for r in roots if not r.machine_code]

    if missing_machine_code:
        error_msg = _(
            "Please enter machine_code for these root components first:<br><br>"
            "<b>{0}</b><br><br>"
            "Then run this button again."
        ).format("<br>".join(missing_machine_code))

        frappe.throw(error_msg, title=_("Machine Code Missing"))

    # Step 3: Cascade machine_code from each root to its descendants
    machine_code_updated = 0

    for root in roots:
        try:
            count = cascade_machine_code_recursive(root.name, root.machine_code)
            machine_code_updated += count
        except Exception as e:
            frappe.log_error(
                title=f"Failed to cascade machine_code for {root.item_code}",
                message=frappe.get_traceback()
            )
            errors.append(f"{root.item_code}: {str(e)}")

    # Step 4: Rebuild BOM Usage tables
    bom_usage_rebuilt = 0
    try:
        boms = frappe.get_all(
            "BOM",
            filters={"project": project, "docstatus": 1, "is_active": 1},
            fields=["name", "item"]
        )

        if boms:
            populate_bom_usage_tables(project, boms)
            bom_usage_rebuilt = len(boms)

            # Recalculate total_qty_limit for all Component Masters after BOM usage rebuild
            component_masters = frappe.get_all(
                "Project Component Master",
                filters={"project": project},
                fields=["name"]
            )

            for cm in component_masters:
                cm_doc = frappe.get_doc("Project Component Master", cm.name)
                # Trigger calculation by calling the method directly
                cm_doc.calculate_bom_qty_required()
                cm_doc.calculate_total_qty_limit()
                cm_doc.calculate_procurement_totals()
                cm_doc.update_procurement_status()
                # Save with calculation results
                cm_doc.flags.ignore_validate = True
                cm_doc.save(ignore_permissions=True)

    except Exception as e:
        frappe.log_error(
            title=f"Failed to rebuild BOM usage for {project}",
            message=frappe.get_traceback()
        )
        errors.append(f"BOM Usage rebuild: {str(e)}")

    # Step 5: Backfill procurement records (MR, RFQ, PO, PR)
    procurement_added = 0
    procurement_skipped = 0
    try:
        result = backfill_procurement_records(project)
        procurement_added = result["added"]
        procurement_skipped = result["skipped"]
        if result["errors"]:
            errors.extend(result["errors"])
    except Exception as e:
        frappe.log_error(
            title=f"Failed to backfill procurement records for {project}",
            message=frappe.get_traceback()
        )
        errors.append(f"Procurement backfill: {str(e)}")

    # Step 6: Commit and return summary
    frappe.db.commit()

    summary = _(
        "✓ Parent links updated: <b>{0}</b> Component Masters<br>"
        "✓ Roots processed: <b>{1}</b><br>"
        "✓ Machine codes updated: <b>{2}</b> Component Masters<br>"
        "✓ BOM usage rebuilt: <b>{3}</b> BOMs<br>"
        "✓ Procurement records added: <b>{4}</b> (skipped {5} existing)<br>"
    ).format(parent_links_updated, len(roots), machine_code_updated, bom_usage_rebuilt, procurement_added, procurement_skipped)

    if errors:
        summary += _("<br>⚠ Errors encountered:<br>• {0}").format("<br>• ".join(errors))

    return {
        "parent_links_updated": parent_links_updated,
        "machine_code_updated": machine_code_updated,
        "bom_usage_rebuilt": bom_usage_rebuilt,
        "procurement_added": procurement_added,
        "procurement_skipped": procurement_skipped,
        "summary": summary,
        "has_errors": len(errors) > 0,
        "errors": errors
    }


def cascade_machine_code_recursive(component_master_name, machine_code):
    """
    Recursively cascade machine_code to all descendants via parent_component chain.

    Args:
        component_master_name: Name of Component Master (starting point)
        machine_code: Machine code to cascade

    Returns:
        int: Count of Component Masters updated
    """
    # Find all direct children
    children = frappe.get_all(
        "Project Component Master",
        filters={"parent_component": component_master_name},
        fields=["name"]
    )

    updated_count = 0

    for child in children:
        # Update machine_code (overwrites existing value - root is source of truth)
        frappe.db.set_value(
            "Project Component Master",
            child.name,
            "machine_code",
            machine_code,
            update_modified=False  # Don't update modified timestamp
        )
        updated_count += 1

        # Recursively cascade to this child's children
        updated_count += cascade_machine_code_recursive(child.name, machine_code)

    return updated_count


def backfill_procurement_records(project):
    """
    Backfill procurement records for all Component Masters in a project.
    Scans existing MRs, RFQs, POs, and PRs and adds them to Component Master procurement_records.

    This is idempotent - existing records are skipped.

    Args:
        project: Project name

    Returns:
        dict: {"added": int, "skipped": int, "errors": list}
    """
    added = 0
    skipped = 0
    errors = []

    # Document types to scan with their field configurations
    # (doctype, item_doctype, date_field, has_rate, project_field)
    doc_types = [
        ("Material Request", "Material Request Item", "transaction_date", False, "project"),
        ("Request for Quotation", "Request for Quotation Item", "transaction_date", False, "project_name"),
        ("Purchase Order", "Purchase Order Item", "transaction_date", True, "project"),
        ("Purchase Receipt", "Purchase Receipt Item", "posting_date", True, "project"),
    ]

    for doc_type, item_doctype, date_field, has_rate, project_field in doc_types:
        try:
            # Find all submitted documents with items linked to this project
            docs = frappe.get_all(
                doc_type,
                filters={"docstatus": 1},  # Submitted only
                fields=["name", date_field, "docstatus"],
                order_by="creation"
            )

            for doc_data in docs:
                # Get items from this document that are linked to the project
                # MR and RFQ items don't have rate field
                item_fields = ["item_code", "qty", project_field]
                if has_rate:
                    item_fields.append("rate")

                items = frappe.get_all(
                    item_doctype,
                    filters={
                        "parent": doc_data.name,
                        project_field: project
                    },
                    fields=item_fields
                )

                if not items:
                    continue  # No items for this project

                for item in items:
                    # Find Component Master
                    cm_name = frappe.db.get_value(
                        "Project Component Master",
                        {"project": project, "item_code": item.item_code},
                        "name"
                    )

                    if not cm_name:
                        continue  # Item not tracked

                    cm = frappe.get_doc("Project Component Master", cm_name)

                    # Check if record already exists (idempotent)
                    already_exists = False
                    for row in cm.procurement_records:
                        if row.document_type == doc_type and row.document_name == doc_data.name:
                            already_exists = True
                            break

                    if already_exists:
                        skipped += 1
                        continue

                    # Determine procurement source
                    procurement_source = "Loose Item" if cm.is_loose_item else "BOM Item"

                    # Get status
                    status_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}
                    status = status_map.get(doc_data.docstatus, "Unknown")

                    # Get rate (only PO and PR have rate)
                    rate = item.get("rate", 0) or 0
                    qty = item.qty or 0

                    # Get date from the appropriate field
                    doc_date = doc_data.get(date_field) or frappe.utils.today()

                    # Add the record
                    cm.append("procurement_records", {
                        "document_type": doc_type,
                        "document_name": doc_data.name,
                        "quantity": qty,
                        "rate": rate,
                        "amount": qty * rate,
                        "date": doc_date,
                        "status": status,
                        "procurement_source": procurement_source,
                        "bom_version": cm.active_bom,
                    })

                    cm.flags.ignore_validate = True
                    cm.flags.ignore_mandatory = True
                    cm.save(ignore_permissions=True)
                    added += 1

        except Exception as e:
            frappe.log_error(
                title=f"Failed to backfill {doc_type} for {project}",
                message=frappe.get_traceback()
            )
            errors.append(f"{doc_type}: {str(e)}")

    return {"added": added, "skipped": skipped, "errors": errors}


def backfill_parent_components(project):
    """
    Backfill parent_component links for all Component Masters in a project
    based on the BOM structure.

    Logic:
    - For each Component Master with an active_bom
    - Get all items from that BOM
    - Find the corresponding Component Master for each BOM item
    - Set that Component Master's parent_component to point to this Component Master

    Args:
        project: Project name

    Returns:
        int: Number of parent_component links updated
    """
    updated_count = 0

    # Get all Component Masters with active BOMs
    component_masters = frappe.get_all(
        "Project Component Master",
        filters={
            "project": project,
            "has_bom": 1,
            "active_bom": ["is", "set"]
        },
        fields=["name", "item_code", "active_bom"]
    )

    for cm in component_masters:
        # Get all items from this BOM
        bom_items = frappe.get_all(
            "BOM Item",
            filters={"parent": cm.active_bom},
            fields=["item_code", "qty"]
        )

        for bom_item in bom_items:
            # Find the Component Master for this BOM item
            child_cm_name = frappe.db.get_value(
                "Project Component Master",
                {"project": project, "item_code": bom_item.item_code},
                "name"
            )

            if not child_cm_name:
                # BOM item doesn't have a Component Master (might be purchased item)
                continue

            # Get current parent_component value
            current_parent = frappe.db.get_value(
                "Project Component Master",
                child_cm_name,
                "parent_component"
            )

            # Update if different or not set
            if current_parent != cm.name:
                frappe.db.set_value(
                    "Project Component Master",
                    child_cm_name,
                    "parent_component",
                    cm.name,
                    update_modified=False
                )
                updated_count += 1

    return updated_count
