# QC Print Format — Implementation Notes

## Why we moved away from the standard Frappe print format

The standard Frappe print format uses **wkhtmltopdf** to generate PDFs server-side.
It worked but had several pain points:

- Footer position was controlled by `--footer-html` flag — reliable but hard to debug
- Adding a rich-text Notes field with images caused layout instability
- Blank extra page appeared due to Frappe injecting a hidden `#footer-html` div into the DOM
- Hard to iterate quickly — every change required a page reload + PDF download

We replaced it with a **browser-based HTML approach**: a Python function generates
the full HTML and sends it to the browser as a Blob URL. The browser's native
print-to-PDF handles layout and page breaks.

---

## Architecture

### Backend — `quality_clearance.py`

```python
@frappe.whitelist()
def get_qc_print_html(doc_name):
    ...
    return """<!DOCTYPE html>..."""
```

- Decorated with `@frappe.whitelist()` so it is callable from JS via `frappe.call()`
- Fetches the **QC Letter Head** from DB for header and footer HTML
- Renders the footer Jinja template with `frappe.render_template(lh.footer, {"doc": doc})`
- Returns a complete, self-contained HTML string

### Frontend — `quality_clearance.js`

```javascript
frappe.call({
    method: 'clevertech...quality_clearance.get_qc_print_html',
    args: { doc_name: frm.doc.name },
    callback: function(r) {
        const blob = new Blob([r.message], { type: 'text/html' });
        const url = URL.createObjectURL(blob);
        window.open(url, '_blank');
        setTimeout(() => URL.revokeObjectURL(url), 10000);
    }
});
```

- Opens the HTML in a new browser tab via a Blob URL
- `window.addEventListener('load', () => window.print())` in the HTML auto-opens the print dialog

---

## Key CSS Learnings

### 1. Repeating header on every page — use `<thead>`

Put the letter head inside `<thead>` of a full-page outer table.
The browser natively repeats `<thead>` at the top of every printed page.

```html
<table class="outer-table">
  <thead><tr><td class="header-cell">{letter_head_content}</td></tr></thead>
  <tbody><tr><td class="content-cell">{main content}</td></tr></tbody>
</table>
```

Do NOT use `position: fixed` for the header — Chrome's `position: fixed` in print
is relative to the **content area** (after @page margins), not the paper edge.
Attempting `@page { margin-top: 45mm }` to make room for a fixed header causes
content to hide behind the header.

### 2. Footer strategy — dual approach based on Notes content

**Problem**: A `position: fixed` footer overlaps images in Notes. A `<tfoot>` footer
follows content but doesn't pin to page bottom on short pages.

**Solution**: detect whether Notes has images at render time and choose the strategy:

| Notes content | Footer strategy | Behaviour |
|---|---|---|
| Has `<img>` tags | `<tfoot>` in outer table | Footer follows content, never overlaps images |
| Text only | `position: fixed; bottom: 8mm` | Footer always pinned to page bottom |

```python
has_images_in_notes = "<img" in (doc.notes or "")
if has_images_in_notes:
    footer_tfoot = f"<tfoot>..."
    content_padding_bottom = "5mm"
else:
    footer_fixed = f'<div class="page-footer">...'
    content_padding_bottom = "70mm"  # prevent content flowing under fixed footer
```

### 3. Page numbers — `@page @bottom-center`

```css
@page {
    size: A4;
    margin: 0 15mm 8mm 15mm;
    @bottom-center {
        content: "Page " counter(page) " of " counter(pages);
        font-size: 9px;
    }
}
```

Chrome 131+ supports text/counters in `@page` margin boxes natively.

### 4. Images in Notes not loading in Blob URL tab

Frappe stores uploaded images as relative paths (`/files/image.png`).
In a Blob URL context the origin is `blob:`, so relative paths don't resolve.

Fix: add `<base href="{site_url}">` in the HTML `<head>`.

### 5. Oversized pasted images compress all fonts

If a user pastes a screenshot (e.g., 1920×1080px) into the Notes rich text field,
the browser scales down the entire page layout to fit the wide image — shrinking
all fonts proportionally.

Fix:
```css
.content-cell img { max-width: 100%; height: auto; }
```

### 6. Footer table row height sync between two side-by-side tables

The letter head footer has two inner tables side-by-side (Clevertech left, supplier right).
Because they are separate `<table>` elements, their row heights are independent.

Clevertech's company name ("CLEVERTECH PACKAGING AUTOMATION SOLUTIONS PVT. LTD." = 51 chars)
wraps to 2 lines at the available width → 3 lines total including "FOR".
Short supplier names stay at 1 line → 2 lines total → rows are misaligned.

**This was fine in wkhtmltopdf** because wkhtmltopdf's WebKit rendered the Clevertech
name at a slightly wider effective width where it fit on one line — both cells had
2 lines and matched naturally. Chrome's font metrics are slightly tighter, causing
the wrap.

Fix: post-process the rendered footer HTML to inject `<br>` tags into the supplier cell
when the supplier name is shorter than 45 chars (won't wrap like Clevertech):

```python
_sname = doc.supplier_name or ""
if len(_sname) < 45:
    _marker = 'colspan="4"'
    _idx1 = footer_html.find(_marker)
    if _idx1 >= 0:
        _idx2 = footer_html.find(_marker, _idx1 + len(_marker))
        if _idx2 >= 0:
            _close = footer_html.find("</td>", _idx2)
            if _close >= 0:
                footer_html = footer_html[:_close] + "<br><br>" + footer_html[_close:]
```

The first `colspan="4"` = Clevertech cell. The second = supplier cell.

---

## Vendor name "None" in GRN-based QCs

For GRN-based QCs, `doc.supplier_name` was not populated at save time.

Fix in `get_items_from_grn()`:
```python
grn = frappe.get_doc("Purchase Receipt", self.grn_name)
self.supplier = grn.supplier
self.supplier_name = grn.supplier_name
```

Also added a fallback chain in `get_qc_print_html()`:
```python
supplier_name = html.escape(
    doc.supplier_name
    or frappe.db.get_value("Purchase Receipt", doc.grn_name, "supplier_name")
    or frappe.db.get_value("Supplier", doc.supplier, "supplier_name")
    or ""
)
```

---

## What did NOT work (and why)

| Approach | Why it failed |
|---|---|
| `position: fixed` header | Chrome fixed elements in print are relative to content area, not paper. Header only shows on page 1. |
| `@page { margin-top: 45mm }` to make room for fixed header | Content table hidden behind header — content area starts after margin, fixed element starts at top of content area. |
| `@page { margin-bottom: 70mm }` to prevent fixed footer overlap | Content still fills full content height; fixed footer overlaps bottom content regardless. |
| Paged.js polyfill for `position: running()` | Works but significant dependency. Overkill for this use case. |
| CSS `min-height` on `<td>` | Not reliably supported on table cells. Use `height` (acts as min-height) or inject `<br>` content. |
