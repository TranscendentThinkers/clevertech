import frappe

def before_save(doc, method):
    if doc.items:
        doc.items = sorted(doc.items, key=lambda x: (x.item_name or '').lower())
        for i, item in enumerate(doc.items, start=1):
            item.idx = i
