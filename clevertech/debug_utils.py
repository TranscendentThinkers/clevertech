import frappe
import json

def check_orphaned_items():
    """Check how many items have bom_level > 1 (not root) but no parent_component

    Note: In this system, level 1 = root, level 2 = first children, etc.
    """
    project_name = 'SMR240004'

    data = frappe.db.sql("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN parent_component IS NULL AND bom_level > 1 THEN 1 ELSE 0 END) as orphaned,
            SUM(CASE WHEN bom_level = 1 THEN 1 ELSE 0 END) as roots,
            SUM(CASE WHEN bom_level > 1 THEN 1 ELSE 0 END) as children
        FROM `tabProject Component Master`
        WHERE project = %s
    """, (project_name,), as_dict=True)

    print(f"\n=== Project {project_name} Statistics ===")
    print(f"Total Component Masters: {data[0]['total']}")
    print(f"Roots (level=1): {data[0]['roots']}")
    print(f"Children (level>1): {data[0]['children']}")
    print(f"Orphaned (level>1 but no parent): {data[0]['orphaned']}")

    # Get sample orphaned items
    orphaned = frappe.db.sql("""
        SELECT name, item_code, bom_level, has_bom, active_bom
        FROM `tabProject Component Master`
        WHERE project = %s
        AND parent_component IS NULL
        AND bom_level > 1
        ORDER BY bom_level
        LIMIT 10
    """, (project_name,), as_dict=True)

    print(f"\n=== Sample Orphaned Items ===")
    for item in orphaned:
        print(f"\n{item.name}")
        print(f"  Item: {item.item_code}")
        print(f"  Level: {item.bom_level}")
        print(f"  Has BOM: {item.has_bom}")

    return data

def debug_parent_backfill():
    """Debug why parent_component backfilling isn't working for A00000006456"""

    project_name = 'SMR240004'
    item_code = 'A00000006456'

    print(f"\n=== Debugging parent backfill for {item_code} ===")

    # Get the Component Master
    cm = frappe.db.get_value(
        "Project Component Master",
        {"project": project_name, "item_code": item_code},
        ["name", "parent_component", "bom_level", "has_bom", "active_bom"],
        as_dict=True
    )

    print(f"\nComponent Master: {cm.name}")
    print(f"  Current parent_component: {cm.parent_component or 'NULL'}")
    print(f"  BOM Level: {cm.bom_level}")
    print(f"  Has BOM: {cm.has_bom}")
    print(f"  Active BOM: {cm.active_bom or 'None'}")

    # Find which BOMs contain this item
    print(f"\n=== BOMs containing {item_code} ===")
    bom_items = frappe.db.sql("""
        SELECT bi.parent as bom_name, bi.qty, bom.item as parent_item
        FROM `tabBOM Item` bi
        INNER JOIN `tabBOM` bom ON bom.name = bi.parent
        WHERE bi.item_code = %s
        AND bom.docstatus = 1
        AND bom.is_active = 1
        AND bom.project = %s
    """, (item_code, project_name), as_dict=True)

    print(f"Found {len(bom_items)} BOM(s) containing this item:")
    for bi in bom_items:
        print(f"\n  BOM: {bi.bom_name}")
        print(f"    Parent Item: {bi.parent_item}")
        print(f"    Qty: {bi.qty}")

        # Check if parent item has a Component Master
        parent_cm = frappe.db.get_value(
            "Project Component Master",
            {"project": project_name, "item_code": bi.parent_item},
            ["name", "active_bom"],
            as_dict=True
        )

        if parent_cm:
            print(f"    Parent CM: {parent_cm.name}")
            print(f"    Parent Active BOM: {parent_cm.active_bom or 'None'}")
            print(f"    Match: {parent_cm.active_bom == bi.bom_name}")
        else:
            print(f"    ❌ No Component Master found for parent item {bi.parent_item}")

    return bom_items

def check_pcm_data():
    """Check M-Code and G-Code traversal for project SMR240004"""

    project_name = 'SMR240004'

    print(f"\n=== Checking hierarchy for project '{project_name}' ===")

    # Get all records with their parent relationships
    data = frappe.db.sql("""
        SELECT
            pcm.name,
            pcm.item_code,
            pcm.parent_component,
            pcm.bom_level
        FROM `tabProject Component Master` pcm
        WHERE pcm.project = %s
        ORDER BY pcm.bom_level, pcm.item_code
        LIMIT 20
    """, (project_name,), as_dict=True)

    print(f"Found {len(data)} records (showing first 20)")
    for row in data:
        item_code = row.get('item_code') or ''
        prefix = ''
        if item_code.startswith('M'):
            prefix = ' [M-CODE]'
        elif item_code.startswith('G'):
            prefix = ' [G-CODE]'

        print(f"\n{row.get('name')}{prefix}")
        print(f"  Item Code: {item_code}")
        print(f"  Parent: {row.get('parent_component') or 'None (root)'}")
        print(f"  BOM Level: {row.get('bom_level')}")

    # Test the get_ancestor_code logic manually
    print(f"\n=== Testing M-Code and G-Code lookup ===")

    # Build parent lookup
    parent_lookup = {}
    all_records = frappe.db.sql("""
        SELECT name, item_code, parent_component
        FROM `tabProject Component Master`
        WHERE project = %s
    """, (project_name,), as_dict=True)

    for r in all_records:
        parent_lookup[r.name] = {"item_code": r.item_code, "parent_component": r.parent_component}

    print(f"Built parent lookup with {len(parent_lookup)} records")

    # Test traversal for a few records
    test_records = data[:5]  # Test first 5 records
    for rec in test_records:
        m_code = get_ancestor_code_local(rec.name, "M", parent_lookup)
        g_code = get_ancestor_code_local(rec.name, "G", parent_lookup)
        print(f"\n{rec.item_code}:")
        print(f"  M-Code: {m_code or 'Not found'}")
        print(f"  G-Code: {g_code or 'Not found'}")

    return data

def get_ancestor_code_local(component_master, prefix, parent_lookup, max_depth=20):
    """Local version of get_ancestor_code for testing"""
    current = component_master
    depth = 0

    while current and depth < max_depth:
        data = parent_lookup.get(current)
        if not data:
            break

        item_code = data.get("item_code") or ""
        if item_code.startswith(prefix):
            return item_code

        current = data.get("parent_component")
        depth += 1

    return None
