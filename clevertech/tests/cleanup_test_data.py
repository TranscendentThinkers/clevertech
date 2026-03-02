"""One-time cleanup of leftover test data. Run via: bench execute clevertech.tests.cleanup_test_data.cleanup"""

import frappe


def cleanup():
    proj = frappe.db.get_value("Project", {"project_name": "TEST-G-CODE-VALIDATION"}, "name")
    print(f"Project: {proj}")

    # SAFETY CHECK 1: Project must exist
    if not proj:
        print("No test project found, nothing to clean up.")
        return

    # SAFETY CHECK 2: Project name MUST contain "TEST" (case-insensitive)
    if "TEST" not in proj.upper():
        print(f"SAFETY CHECK FAILED: Project '{proj}' does not contain 'TEST'. Aborting cleanup.")
        return

    # SAFETY CHECK 3: Project name must match exactly
    actual_name = frappe.db.get_value("Project", proj, "project_name")
    if actual_name != "TEST-G-CODE-VALIDATION":
        print(f"SAFETY CHECK FAILED: Project name mismatch. Expected 'TEST-G-CODE-VALIDATION', got '{actual_name}'. Aborting.")
        return

    print(f"Safety checks passed. Proceeding with cleanup for project: {proj}")

    # MRs
    for mr in frappe.db.get_all("Material Request", {"custom_project_": proj}, pluck="name"):
        doc = frappe.get_doc("Material Request", mr)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc("Material Request", mr, force=True)
        print(f"Deleted MR: {mr}")

    # CMs
    for cm in frappe.db.get_all("Project Component Master", {"project": proj}, pluck="name"):
        frappe.delete_doc("Project Component Master", cm, force=True)
        print(f"Deleted CM: {cm}")

    # BOMs
    test_items = [
        "MT4000084237", "MT4000084238", "GT3000012345", "GT3000067890",
        "GT3000099999", "DT0000054321", "DT0000054322", "DT0000054323",
    ]
    for ic in test_items:
        for bom in frappe.db.get_all("BOM", {"item": ic, "docstatus": 1}, pluck="name"):
            frappe.get_doc("BOM", bom).cancel()
        for bom in frappe.db.get_all("BOM", {"item": ic}, pluck="name"):
            frappe.delete_doc("BOM", bom, force=True)
            print(f"Deleted BOM: {bom}")

    # BOM Upload
    for bu in frappe.db.get_all("BOM Upload", {"project": proj}, pluck="name"):
        frappe.delete_doc("BOM Upload", bu, force=True)
        print(f"Deleted BOM Upload: {bu}")

    # Items - ONLY delete items explicitly created by tests
    # SAFETY CHECK: Only delete items matching test patterns
    all_items = test_items + ["AT0000012345", "AT0000099999"]  # Updated to AT prefix
    for ic in all_items:
        if frappe.db.exists("Item", ic):
            # Additional safety: verify item was created recently (within 24 hours)
            item_created = frappe.db.get_value("Item", ic, "creation")
            if item_created:
                age_hours = (frappe.utils.now_datetime() - item_created).total_seconds() / 3600
                if age_hours > 24:
                    print(f"SKIPPED Item {ic}: Created {age_hours:.1f}h ago (>24h), likely not from current test run")
                    continue
            frappe.delete_doc("Item", ic, force=True)
            print(f"Deleted Item: {ic}")

    # Cost Centers
    for cc in frappe.db.get_all("Cost Center", {"cost_center_name": ["like", "Test MT4000084%"]}, pluck="name"):
        frappe.delete_doc("Cost Center", cc, force=True)
        print(f"Deleted CC: {cc}")

    # Project
    frappe.delete_doc("Project", proj, force=True)
    print(f"Deleted Project: {proj}")

    frappe.db.commit()
    print("Cleanup complete")
