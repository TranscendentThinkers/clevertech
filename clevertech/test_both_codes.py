"""
Test to verify both original and enhanced code behavior with the Excel file
"""

import sys
sys.path.insert(0, '/home/bharatbodh/bharatbodh-bench/apps/frappe')
import frappe

# Simulate the tree structure from the Excel
def simulate_tree_from_excel():
    """
    Simulates what parse_rows + build_tree produces from the Excel
    """
    # Based on actual Excel data:
    # Row 5: A00000006515 (Level=1, 2 dots)
    # Row 6: A00000008674 (Level=4, 2 dots) -> becomes child because 4 > 1

    rows = [
        {"item_code": "M00000027264", "level": 1, "children": []},
        {"item_code": "G00000048830", "level": 1, "children": []},
        {"item_code": "A00000006515", "level": 1, "children": []},  # Will get children
        {"item_code": "A00000008674", "level": 4, "children": []},  # Becomes child
    ]

    # Simulate build_tree logic
    stack = []
    roots = []

    for row in rows:
        while stack and stack[-1]["level"] >= row["level"]:
            stack.pop()

        if stack:
            stack[-1]["children"].append(row)
        else:
            roots.append(row)

        stack.append(row)

    return roots

def test_original_behavior():
    """
    Test what original create_bom_recursive would do
    """
    print("=" * 80)
    print("ORIGINAL CODE BEHAVIOR TEST")
    print("=" * 80)

    tree = simulate_tree_from_excel()

    # Find A00000006515
    a_node = next((n for n in tree if n["item_code"] == "A00000006515"), None)

    if not a_node:
        # Check if it's a child
        for root in tree:
            if root.get("children"):
                a_node = next((c for c in root["children"] if c["item_code"] == "A00000006515"), None)
                if a_node:
                    break

    if a_node:
        print(f"\nA00000006515 found:")
        print(f"  Level: {a_node['level']}")
        print(f"  Children: {len(a_node.get('children', []))}")

        if a_node.get("children"):
            print(f"\n  Children list:")
            for child in a_node["children"]:
                print(f"    - {child['item_code']} (Level={child['level']})")

            # Original code logic (line 735 in bom_upload.py)
            will_create_bom = len(a_node["children"]) > 0
            print(f"\n  Will create BOM? {will_create_bom}")
            print(f"  Reason: {'Has children' if will_create_bom else 'No children'}")
        else:
            print(f"\n  Will create BOM? False")
            print(f"  Reason: No children")

if __name__ == "__main__":
    test_original_behavior()
