#!/usr/bin/env python3
"""
Test script for debug_bom_quantities function
"""
import frappe
from clevertech.clevertech.doctype.bom_upload.bom_upload_enhanced import debug_bom_quantities

def test_debug():
    frappe.init(site='clevertech-uat.bharatbodh.com')
    frappe.connect()

    # Find the BOM Upload document with the Excel file
    bom_upload = frappe.get_all(
        "BOM Upload",
        filters={"bom_file": ["like", "%BomExport_V00000000015_00%"]},
        fields=["name", "bom_file"],
        limit=1
    )

    if not bom_upload:
        print("ERROR: Could not find BOM Upload document with the Excel file")
        return

    docname = bom_upload[0].name
    print(f"Found BOM Upload: {docname}")
    print(f"File: {bom_upload[0].bom_file}")
    print()

    # Call debug function for A00000006515
    print("Analyzing item A00000006515...")
    print("=" * 80)

    result = debug_bom_quantities(docname, "A00000006515")

    # Print results
    print(f"\n{result['tree_analysis']}")
    print()
    print("=" * 80)
    print(f"\nSUMMARY:")
    print(f"  Target Item: {result['target_item']}")
    print(f"  Excel Occurrences: {result['excel_occurrences']}")
    print(f"  Excel Total Qty: {result['excel_total_qty']}")
    print(f"  Parent Assemblies: {result['parents_count']}")
    print()

    # Show details for G00000054189 specifically
    for parent_data in result['occurrences_by_parent']:
        if parent_data['parent_item'] == 'G00000054189':
            print(f"\n🔍 SPECIFIC ANALYSIS FOR G00000054189:")
            print(f"   Occurrences: {len(parent_data['occurrences'])}")
            print(f"   Total Qty: {parent_data['total_qty']}")
            print(f"   BOM Items to Create: {parent_data['bom_items_count']}")
            print(f"\n   Individual Occurrences:")
            for i, occ in enumerate(parent_data['occurrences'], 1):
                print(f"     #{i}: Row {occ['row']}, Position {occ['position']}, Qty {occ['qty']}")
            break

    frappe.destroy()

if __name__ == "__main__":
    test_debug()
