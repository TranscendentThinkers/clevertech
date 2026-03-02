"""
Bulk Generation of Component Masters from Existing BOMs

Provides functionality to create Project Component Master records for all items
with BOMs in a project. This is useful for migrating existing projects into the
Component Master system.
"""

import frappe
from frappe import _
from clevertech.project_component_master.bom_hooks import (
    calculate_bom_structure_hash,
    add_or_update_bom_usage,
)


@frappe.whitelist()
def generate_component_masters_from_boms(project):
    """
    Generate Component Master records for all items with BOMs in a project.

    Args:
        project: Project name

    Returns:
        dict: Summary with created_count, skipped_count, and details list
    """
    if not frappe.has_permission("Project Component Master", "create"):
        frappe.throw(_("No permission to create Component Masters"))

    # Validate project exists
    if not frappe.db.exists("Project", project):
        frappe.throw(_("Project {0} does not exist").format(project))

    # Get all submitted BOMs for this project
    boms = frappe.get_all(
        "BOM",
        filters={
            "project": project,
            "docstatus": 1,  # Only submitted BOMs
            "is_active": 1,  # Only active BOMs
            "is_default": 1  # Only default BOMs for each item
        },
        fields=["name", "item", "item_name"],
        order_by="item"
    )

    if not boms:
        frappe.msgprint(
            _("No active BOMs found for project {0}").format(project),
            title=_("No BOMs Found"),
            indicator="orange"
        )
        return {
            "created_count": 0,
            "skipped_count": 0,
            "details": []
        }

    created_count = 0
    skipped_count = 0
    details = []

    for bom in boms:
        item_code = bom.item
        bom_name = bom.name

        # Check if Component Master already exists for this project + item
        existing = frappe.db.exists(
            "Project Component Master",
            {"project": project, "item_code": item_code}
        )

        if existing:
            skipped_count += 1
            details.append({
                "item_code": item_code,
                "bom": bom_name,
                "status": "Skipped - Already exists",
                "component_master": existing
            })
            continue

        # Create new Component Master
        try:
            component_master = frappe.get_doc({
                "doctype": "Project Component Master",
                "project": project,
                "item_code": item_code,
                "has_bom": 1,
                "active_bom": bom_name,
                "is_loose_item": 0,
                "loose_qty_required": 0,
                "design_status": "Design Released",
                "project_qty": 1,  # Default for cutover - user should review and update
                "created_from": "Cutover",
                "make_or_buy": "Make",  # Default for assemblies with BOMs
            })

            # Calculate and set BOM structure hash
            bom_doc = frappe.get_doc("BOM", bom_name)
            component_master.bom_structure_hash = calculate_bom_structure_hash(bom_doc)

            # Save with flags to skip validation during bulk creation
            component_master.flags.ignore_validate = True
            component_master.flags.ignore_mandatory = True
            component_master.insert(ignore_permissions=True)

            created_count += 1
            details.append({
                "item_code": item_code,
                "bom": bom_name,
                "status": "Created",
                "component_master": component_master.name
            })

        except Exception as e:
            frappe.log_error(
                title=f"Failed to create Component Master for {item_code}",
                message=frappe.get_traceback()
            )
            skipped_count += 1
            details.append({
                "item_code": item_code,
                "bom": bom_name,
                "status": f"Error: {str(e)}",
                "component_master": None
            })

    # Now populate BOM Usage tables by calling BOM hooks for each created Component Master
    if created_count > 0:
        populate_bom_usage_tables(project, boms)

    # Commit the transaction
    frappe.db.commit()

    # Show summary message
    message = _("Component Masters Generated:<br><br>")
    message += _("✓ Created: <b>{0}</b><br>").format(created_count)
    message += _("○ Skipped: <b>{0}</b><br>").format(skipped_count)
    message += _("━ Total BOMs: <b>{0}</b><br><br>").format(len(boms))

    if created_count > 0:
        message += _("<b>⚠ Important:</b> Default Project Quantities set to 1, Make/Buy set to 'Make'.<br>")
        message += _("Please review and update 'Project Qty Required' and 'Make / Buy' for each component as needed.")

    frappe.msgprint(
        message,
        title=_("Bulk Generation Complete"),
        indicator="green"
    )

    return {
        "created_count": created_count,
        "skipped_count": skipped_count,
        "details": details
    }


def populate_bom_usage_tables(project, boms):
    """
    Populate BOM Usage child tables for all Component Masters in the project.
    This simulates what the BOM hooks would have done if they existed when BOMs were created.

    Args:
        project: Project name
        boms: List of BOM dicts with name and item fields
    """
    for bom in boms:
        # Support both dict (from _link_boms_to_component_masters) and frappe._dict (from get_all)
        bom_name = bom["name"] if isinstance(bom, dict) else bom.name
        bom_doc = frappe.get_doc("BOM", bom_name)

        # Consolidate duplicate items in BOM (sum quantities)
        # Same logic as on_bom_submit in bom_hooks.py
        item_quantities = {}
        for item in bom_doc.items:
            if item.item_code in item_quantities:
                item_quantities[item.item_code] += float(item.qty or 0)
            else:
                item_quantities[item.item_code] = float(item.qty or 0)

        # Process consolidated items
        for item_code, total_qty in item_quantities.items():
            add_or_update_bom_usage(
                project=project,
                item_code=item_code,
                parent_bom=bom_name,
                qty_per_unit=total_qty
            )
