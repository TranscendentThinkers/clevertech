import frappe
from frappe import _

def before_insert(doc, method):
    # create hashable structure for new BOM items
    new_items = sorted(
        [(row.item_code, float(row.qty)) for row in doc.items],
        key=lambda x: x[0]
    )

    # fetch existing BOMs with same main item + project
    existing_boms = frappe.get_all(
        "BOM",
        filters={
            "item": doc.item,
            "project": doc.project,
            "is_active": 1
        },
        fields=["name"]
    )

    for bom in existing_boms:
        existing_items = frappe.get_all(
            "BOM Item",
            filters={"parent": bom.name},
            fields=["item_code", "qty"]
        )

        existing_items_struct = sorted(
            [(row.item_code, float(row.qty)) for row in existing_items],
            key=lambda x: x[0]
        )

        # Compare structure
        if new_items == existing_items_struct:
            frappe.throw(
                _("Duplicate BOM found: <b>{0}</b> with same item, project, and items")
                .format(bom.name)
            )

