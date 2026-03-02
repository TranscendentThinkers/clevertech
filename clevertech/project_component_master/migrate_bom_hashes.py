"""
Migration Script: Backfill BOM Structure Hashes

This script calculates and stores the `custom_bom_structure_hash` field
for all existing submitted BOMs that don't have a hash yet.

Usage:
    bench --site <site_name> execute clevertech.project_component_master.migrate_bom_hashes.migrate_bom_hashes

Or from bench console:
    from clevertech.project_component_master.migrate_bom_hashes import migrate_bom_hashes
    migrate_bom_hashes()
"""

import frappe
import hashlib
import json


def migrate_bom_hashes(dry_run=False):
    """
    Backfill BOM structure hash for all existing submitted BOMs.

    Args:
        dry_run: If True, only report what would be updated without making changes

    Returns:
        dict: Summary of migration results
    """
    print("Starting BOM hash migration...")

    # Get all submitted BOMs without hash
    boms = frappe.get_all(
        "BOM",
        filters={
            "docstatus": 1,
            "custom_bom_structure_hash": ["in", [None, ""]]
        },
        fields=["name"],
        order_by="creation asc"
    )

    total = len(boms)
    print(f"Found {total} BOMs without hash")

    if total == 0:
        print("No BOMs to migrate.")
        return {"total": 0, "updated": 0, "skipped": 0, "errors": []}

    updated = 0
    skipped = 0
    errors = []

    for i, bom_data in enumerate(boms, 1):
        try:
            bom_name = bom_data.name

            # Get BOM items
            items = frappe.get_all(
                "BOM Item",
                filters={"parent": bom_name},
                fields=["item_code", "qty"]
            )

            if not items:
                print(f"  [{i}/{total}] {bom_name} - No items, skipping")
                skipped += 1
                continue

            # Calculate hash
            structure = sorted(
                [(item.item_code, float(item.qty or 0)) for item in items],
                key=lambda x: x[0]
            )
            structure_str = json.dumps(structure, sort_keys=True)
            hash_value = hashlib.md5(structure_str.encode()).hexdigest()

            if dry_run:
                print(f"  [{i}/{total}] {bom_name} - Would set hash: {hash_value[:8]}...")
            else:
                # Store hash
                frappe.db.set_value(
                    "BOM", bom_name,
                    "custom_bom_structure_hash", hash_value,
                    update_modified=False
                )
                print(f"  [{i}/{total}] {bom_name} - Hash set: {hash_value[:8]}...")

            updated += 1

            # Commit every 100 BOMs to avoid long transactions
            if not dry_run and updated % 100 == 0:
                frappe.db.commit()
                print(f"  Committed {updated} updates...")

        except Exception as e:
            error_msg = f"{bom_data.name}: {str(e)}"
            errors.append(error_msg)
            print(f"  [{i}/{total}] ERROR: {error_msg}")

    # Final commit
    if not dry_run:
        frappe.db.commit()

    # Summary
    print("\n" + "=" * 50)
    print("Migration Complete!")
    print(f"  Total BOMs processed: {total}")
    print(f"  Updated: {updated}")
    print(f"  Skipped (no items): {skipped}")
    print(f"  Errors: {len(errors)}")

    if errors:
        print("\nErrors:")
        for err in errors[:10]:  # Show first 10 errors
            print(f"  - {err}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors")

    return {
        "total": total,
        "updated": updated,
        "skipped": skipped,
        "errors": errors
    }


def check_migration_status():
    """
    Check how many BOMs have/don't have hashes.

    Usage:
        bench --site <site_name> execute clevertech.project_component_master.migrate_bom_hashes.check_migration_status
    """
    total = frappe.db.count("BOM", {"docstatus": 1})
    with_hash = frappe.db.count("BOM", {
        "docstatus": 1,
        "custom_bom_structure_hash": ["not in", [None, ""]]
    })
    without_hash = total - with_hash

    print(f"\nBOM Hash Migration Status:")
    print(f"  Total submitted BOMs: {total}")
    print(f"  With hash: {with_hash}")
    print(f"  Without hash: {without_hash}")
    print(f"  Coverage: {(with_hash/total*100) if total > 0 else 0:.1f}%")

    return {
        "total": total,
        "with_hash": with_hash,
        "without_hash": without_hash
    }
