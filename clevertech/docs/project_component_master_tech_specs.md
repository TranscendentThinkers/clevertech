# Project Component Master - Technical Specifications

## Document Purpose
Complete technical specifications for implementing the Project Component Master system as an enhancement to the existing BOM Upload functionality.

**Approach:** Add NEW button, keep existing logic untouched, create pluggable enhancement.

---

## Table of Contents
1. [New DocTypes](#new-doctypes)
2. [Enhanced BOM Upload](#enhanced-bom-upload)
3. [Validation Hooks](#validation-hooks)
4. [Reports](#reports)
5. [Test Cases](#test-cases)
6. [Database Schema](#database-schema)
7. [API Specifications](#api-specifications)

---

## Procurement Document Tracking Strategy

**Documents Tracked in Procurement Records:**

| Document | Tracked? | Rationale |
|----------|----------|-----------|
| **Material Request** | ✅ Yes | Procurement intent, quantity validation baseline |
| **Request for Quotation** | ✅ Yes | Quote request sent, timeline tracking |
| **Supplier Quotation** | ❌ No | Multiple quotes per RFQ creates noise. Use separate comparison report. |
| **Purchase Order** | ✅ Yes | Actual commitment with rate, legally binding |
| **Purchase Receipt** | ✅ Yes | Physical receipt confirmation, closes procurement loop |

**Why This Selection:**
- **Clean Timeline:** MR → RFQ → PO → PR (4 key milestones)
- **No Quote Noise:** One RFQ can have 3-5 Supplier Quotations. Tracking all creates clutter.
- **Separate Analysis:** Supplier Quotations accessed via standard ERPNext quotation comparison (linked to RFQ)
- **Quantity Control:** Material Request quantities validated against `total_qty_limit`

---

## 1. New DocTypes

### 1.1 Project Component Master

**File Location:** `clevertech/doctype/project_component_master/project_component_master.json`

**Complete JSON Definition:**

```json
{
 "actions": [],
 "allow_rename": 0,
 "autoname": "format:PCM-{project}-{####}",
 "creation": "2026-01-26 00:00:00.000000",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "section_identification",
  "project",
  "item_code",
  "item_name",
  "description",
  "column_break_1",
  "component_image",
  "section_hierarchy",
  "parent_component",
  "bom_level",
  "column_break_2",
  "has_bom",
  "active_bom",
  "section_loose_item",
  "is_loose_item",
  "loose_item_reason",
  "column_break_3",
  "can_be_converted_to_bom",
  "bom_conversion_status",
  "section_budget",
  "budgeted_rate",
  "budgeted_rate_calculated",
  "column_break_4",
  "target_delivery_date",
  "lead_time_days",
  "section_procurement",
  "loose_qty_required",
  "bom_qty_required",
  "total_qty_limit",
  "column_break_5",
  "total_qty_procured",
  "procurement_balance",
  "procurement_status",
  "section_status",
  "design_status",
  "bom_structure_hash",
  "column_break_6",
  "remarks",
  "section_procurement_records",
  "procurement_records",
  "section_bom_usage",
  "bom_usage"
 ],
 "fields": [
  {
   "fieldname": "section_identification",
   "fieldtype": "Section Break",
   "label": "Component Identification"
  },
  {
   "fieldname": "project",
   "fieldtype": "Link",
   "label": "Project",
   "options": "Project",
   "reqd": 1,
   "in_list_view": 1,
   "in_standard_filter": 1
  },
  {
   "fieldname": "item_code",
   "fieldtype": "Link",
   "label": "Item Code",
   "options": "Item",
   "reqd": 1,
   "in_list_view": 1,
   "in_standard_filter": 1
  },
  {
   "fieldname": "item_name",
   "fieldtype": "Data",
   "label": "Item Name",
   "fetch_from": "item_code.item_name",
   "read_only": 1,
   "in_list_view": 1
  },
  {
   "fieldname": "description",
   "fieldtype": "Text",
   "label": "Description",
   "fetch_from": "item_code.description"
  },
  {
   "fieldname": "column_break_1",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "component_image",
   "fieldtype": "Attach Image",
   "label": "Component Image",
   "description": "Upload image/photo of the component for visual reference"
  },
  {
   "fieldname": "section_hierarchy",
   "fieldtype": "Section Break",
   "label": "Hierarchy"
  },
  {
   "fieldname": "parent_component",
   "fieldtype": "Link",
   "label": "Parent Component",
   "options": "Project Component Master",
   "description": "Auto-populated from BOM upload"
  },
  {
   "fieldname": "bom_level",
   "fieldtype": "Int",
   "label": "BOM Level",
   "default": "0",
   "description": "0=top level, 1=first child, 2=second child..."
  },
  {
   "fieldname": "column_break_2",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "has_bom",
   "fieldtype": "Check",
   "label": "Has BOM",
   "default": "0",
   "read_only": 1,
   "description": "Auto-set if this component has its own BOM"
  },
  {
   "fieldname": "active_bom",
   "fieldtype": "Link",
   "label": "Active BOM",
   "options": "BOM",
   "depends_on": "eval:doc.has_bom==1",
   "description": "Current active BOM for this component"
  },
  {
   "fieldname": "section_loose_item",
   "fieldtype": "Section Break",
   "label": "Loose Item Configuration",
   "collapsible": 1
  },
  {
   "fieldname": "is_loose_item",
   "fieldtype": "Check",
   "label": "Is Loose Item",
   "default": "0",
   "description": "Raw material procured outside BOM structure"
  },
  {
   "fieldname": "loose_item_reason",
   "fieldtype": "Small Text",
   "label": "Loose Item Reason",
   "depends_on": "eval:doc.is_loose_item==1",
   "description": "Why procured as loose item (long lead time, design pending, etc.)"
  },
  {
   "fieldname": "column_break_3",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "can_be_converted_to_bom",
   "fieldtype": "Check",
   "label": "Can be Converted to BOM",
   "default": "0",
   "depends_on": "eval:doc.is_loose_item==1",
   "description": "Allow this loose item to be used in BOMs"
  },
  {
   "fieldname": "bom_conversion_status",
   "fieldtype": "Select",
   "label": "BOM Conversion Status",
   "options": "\nNot Applicable\nPending Conversion\nConverted to BOM\nPartial",
   "default": "Not Applicable",
   "depends_on": "eval:doc.is_loose_item==1",
   "description": "Partial = used in some BOMs, still loose in others"
  },
  {
   "fieldname": "section_budget",
   "fieldtype": "Section Break",
   "label": "Budget & Timeline"
  },
  {
   "fieldname": "budgeted_rate",
   "fieldtype": "Currency",
   "label": "Budgeted Rate",
   "description": "Target cost per unit for this component"
  },
  {
   "fieldname": "budgeted_rate_calculated",
   "fieldtype": "Currency",
   "label": "Budgeted Rate (Calculated)",
   "read_only": 1,
   "description": "Auto-calculated from child components"
  },
  {
   "fieldname": "column_break_4",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "target_delivery_date",
   "fieldtype": "Date",
   "label": "Target Delivery Date"
  },
  {
   "fieldname": "lead_time_days",
   "fieldtype": "Int",
   "label": "Lead Time (Days)"
  },
  {
   "fieldname": "section_procurement",
   "fieldtype": "Section Break",
   "label": "Procurement Tracking"
  },
  {
   "fieldname": "loose_qty_required",
   "fieldtype": "Float",
   "label": "Loose Qty Required",
   "depends_on": "eval:doc.is_loose_item==1",
   "description": "Manually entered qty for loose procurement",
   "precision": "2"
  },
  {
   "fieldname": "bom_qty_required",
   "fieldtype": "Float",
   "label": "BOM Qty Required",
   "read_only": 1,
   "description": "Auto-calculated from all BOMs using this item",
   "precision": "2"
  },
  {
   "fieldname": "total_qty_limit",
   "fieldtype": "Float",
   "label": "Total Qty Limit",
   "read_only": 1,
   "description": "MAX(loose_qty, bom_qty) - hard procurement limit",
   "precision": "2"
  },
  {
   "fieldname": "column_break_5",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "total_qty_procured",
   "fieldtype": "Float",
   "label": "Total Qty Procured",
   "read_only": 1,
   "description": "Sum of all procurement quantities",
   "precision": "2"
  },
  {
   "fieldname": "procurement_balance",
   "fieldtype": "Float",
   "label": "Procurement Balance",
   "read_only": 1,
   "description": "total_qty_limit - total_qty_procured",
   "precision": "2"
  },
  {
   "fieldname": "procurement_status",
   "fieldtype": "Select",
   "label": "Procurement Status",
   "options": "\nNot Started\nIn Progress\nCompleted\nOver-procured",
   "read_only": 1,
   "description": "Auto-calculated based on procurement records",
   "in_list_view": 1,
   "in_standard_filter": 1
  },
  {
   "fieldname": "section_status",
   "fieldtype": "Section Break",
   "label": "Status"
  },
  {
   "fieldname": "design_status",
   "fieldtype": "Select",
   "label": "Design Status",
   "options": "\nDraft\nDesign Released\nProcurement Ready\nObsolete",
   "default": "Draft",
   "in_list_view": 1,
   "in_standard_filter": 1
  },
  {
   "fieldname": "bom_structure_hash",
   "fieldtype": "Text",
   "label": "BOM Structure Hash",
   "read_only": 1,
   "hidden": 1,
   "description": "Hash of BOM structure for change detection"
  },
  {
   "fieldname": "column_break_6",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "remarks",
   "fieldtype": "Text",
   "label": "Remarks"
  },
  {
   "fieldname": "section_procurement_records",
   "fieldtype": "Section Break",
   "label": "Procurement Records"
  },
  {
   "fieldname": "procurement_records",
   "fieldtype": "Table",
   "label": "Procurement Records",
   "options": "Component Procurement Record",
   "description": "Track all procurement documents for this component"
  },
  {
   "fieldname": "section_bom_usage",
   "fieldtype": "Section Break",
   "label": "BOM Usage"
  },
  {
   "fieldname": "bom_usage",
   "fieldtype": "Table",
   "label": "BOM Usage",
   "options": "Component BOM Usage",
   "description": "Track all BOMs where this component is used"
  }
 ],
 "index_web_pages_for_search": 1,
 "links": [],
 "modified": "2026-01-26 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Clevertech",
 "name": "Project Component Master",
 "naming_rule": "Expression",
 "owner": "Administrator",
 "permissions": [
  {
   "create": 1,
   "delete": 1,
   "email": 1,
   "export": 1,
   "print": 1,
   "read": 1,
   "report": 1,
   "role": "System Manager",
   "share": 1,
   "write": 1
  },
  {
   "create": 1,
   "email": 1,
   "export": 1,
   "print": 1,
   "read": 1,
   "report": 1,
   "role": "Manufacturing Manager",
   "share": 1,
   "write": 1
  },
  {
   "email": 1,
   "export": 1,
   "print": 1,
   "read": 1,
   "report": 1,
   "role": "Purchase User",
   "share": 1
  }
 ],
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": [],
 "track_changes": 1,
 "unique_fields": ["project", "item_code"]
}
```

---

### 1.2 Component Procurement Record (Child Table)

**File Location:** `clevertech/doctype/component_procurement_record/component_procurement_record.json`

```json
{
 "actions": [],
 "creation": "2026-01-26 00:00:00.000000",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "document_type",
  "document_name",
  "quantity",
  "column_break_1",
  "rate",
  "amount",
  "date",
  "column_break_2",
  "status",
  "procurement_source"
 ],
 "fields": [
  {
   "fieldname": "document_type",
   "fieldtype": "Select",
   "label": "Document Type",
   "options": "Material Request\nRequest for Quotation\nPurchase Order\nPurchase Receipt",
   "reqd": 1,
   "in_list_view": 1,
   "description": "Track MR, RFQ, PO, PR only. Supplier Quotations handled via separate report."
  },
  {
   "fieldname": "document_name",
   "fieldtype": "Dynamic Link",
   "label": "Document Name",
   "options": "document_type",
   "reqd": 1,
   "in_list_view": 1
  },
  {
   "fieldname": "quantity",
   "fieldtype": "Float",
   "label": "Quantity",
   "reqd": 1,
   "in_list_view": 1,
   "precision": "2"
  },
  {
   "fieldname": "column_break_1",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "rate",
   "fieldtype": "Currency",
   "label": "Rate"
  },
  {
   "fieldname": "amount",
   "fieldtype": "Currency",
   "label": "Amount",
   "read_only": 1,
   "description": "quantity * rate"
  },
  {
   "fieldname": "date",
   "fieldtype": "Date",
   "label": "Date",
   "in_list_view": 1
  },
  {
   "fieldname": "column_break_2",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "status",
   "fieldtype": "Data",
   "label": "Status",
   "read_only": 1,
   "description": "Fetched from linked document"
  },
  {
   "fieldname": "procurement_source",
   "fieldtype": "Select",
   "label": "Procurement Source",
   "options": "\nLoose Item\nBOM Item",
   "description": "Whether this procurement was for loose item or from BOM"
  }
 ],
 "istable": 1,
 "modified": "2026-01-26 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Clevertech",
 "name": "Component Procurement Record",
 "owner": "Administrator"
}
```

---

### 1.3 Component BOM Usage (Child Table)

**File Location:** `clevertech/doctype/component_bom_usage/component_bom_usage.json`

```json
{
 "actions": [],
 "creation": "2026-01-26 00:00:00.000000",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "parent_bom",
  "parent_item",
  "qty_per_unit",
  "column_break_1",
  "total_qty_required"
 ],
 "fields": [
  {
   "fieldname": "parent_bom",
   "fieldtype": "Link",
   "label": "Parent BOM",
   "options": "BOM",
   "in_list_view": 1
  },
  {
   "fieldname": "parent_item",
   "fieldtype": "Link",
   "label": "Parent Item",
   "options": "Item",
   "fetch_from": "parent_bom.item",
   "in_list_view": 1,
   "read_only": 1
  },
  {
   "fieldname": "qty_per_unit",
   "fieldtype": "Float",
   "label": "Qty per Unit",
   "in_list_view": 1,
   "description": "Qty of this component per unit of parent",
   "precision": "2"
  },
  {
   "fieldname": "column_break_1",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "total_qty_required",
   "fieldtype": "Float",
   "label": "Total Qty Required",
   "description": "If project requires N units of parent, this is N * qty_per_unit",
   "precision": "2"
  }
 ],
 "istable": 1,
 "modified": "2026-01-26 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Clevertech",
 "name": "Component BOM Usage",
 "owner": "Administrator"
}
```

---

## 2. Enhanced BOM Upload

### 2.1 Modified DocType

**File Location:** `clevertech/doctype/bom_upload/bom_upload.json`

**Add New Button:**
```json
{
  "fieldname": "create_boms_with_validation",
  "fieldtype": "Button",
  "label": "Create BOMs with Validation"
}
```

**Updated field_order:**
```json
"field_order": [
  "project",
  "section_break_tgxf",
  "bom_file",
  "column_break_prdz",
  "create_boms",
  "create_boms_with_validation"
]
```

---

### 2.2 New Server-Side Functions

**File Location:** `clevertech/doctype/bom_upload/bom_upload_enhanced.py`

**CRITICAL: Does NOT modify existing bom_upload.py. Imports functions from it.**
**(See Decision 12 in context doc for rationale)**

**Imports from existing BOM Upload module:**
```python
from clevertech.clevertech.doctype.bom_upload.bom_upload import (
    parse_rows,             # Excel worksheet → list of row dicts
    build_tree,             # Row list → nested tree (uses "level" field)
    ensure_item_exists,     # Create Item master if missing (idempotent)
    create_bom_recursive,   # Bottom-up BOM creation + child linking (idempotent)
)
```

#### Function: `create_boms_with_validation(docname)`

```python
@frappe.whitelist()
def create_boms_with_validation(docname):
    """
    Enhanced BOM creation with validation and Component Master integration.

    CRITICAL SEQUENCE (see Decision 11 & 12 in context doc):
    - Items created FIRST (Link field dependency for Component Masters)
    - Component Masters created BEFORE BOMs (needed for blocking/analysis)
    - active_bom set AFTER BOM creation (linked back)
    - Reuses existing BOM Upload functions via imports (no code duplication)

    Args:
        docname (str): BOM Upload document name

    Returns:
        dict: Analysis results or creation summary
    """
    doc = frappe.get_doc("BOM Upload", docname)

    # Step 1: Parse Excel (reuse existing logic)
    file_doc = frappe.get_doc("File", {"file_url": doc.bom_file})
    content = file_doc.get_content()

    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = wb.active

    rows = parse_rows(ws)
    tree = build_tree(rows)

    # Step 2: Create Items for all assemblies (nodes with children)
    # Items must exist BEFORE Component Masters (item_code is a Link field to Item)
    # ensure_item_exists() is idempotent — skips if Item already exists
    ensure_items_for_assemblies(tree)

    # Step 3: Create Component Masters FIRST for new assemblies
    # (active_bom=null at this stage, set later after BOM creation)
    create_component_masters_for_new_items(tree, doc.project)

    # Step 4: Analyze upload (now Component Masters exist for blocking checks)
    analysis = analyze_upload(tree, doc.project)

    # Step 5: Check for blocking issues
    if analysis['loose_blocked']:
        return {
            "status": "blocked",
            "reason": "loose_items_not_enabled",
            "analysis": analysis,
            "message": "Enable 'Can be converted to BOM' for loose items first"
        }

    if analysis['changed_components']:
        return {
            "status": "requires_resolution",
            "analysis": analysis,
            "message": "Some components have changed. Review and resolve before proceeding."
        }

    # Step 6: Create BOMs bottom-up (reuse existing logic)
    #   create_bom_recursive() internally calls ensure_item_exists() again
    #   for ALL nodes (including leaf items) — harmless, idempotent
    # Step 7: Link active_bom back to Component Masters
    # Step 8: BOM on_submit hooks auto-populate BOM Usage tables
    return create_boms_and_link_components(tree, doc.project, analysis)
```

#### Helper: `ensure_items_for_assemblies(tree)`

```python
def ensure_items_for_assemblies(tree):
    """
    Walk tree and create Item masters for assembly nodes (nodes with children).
    Must run BEFORE Component Master creation since item_code is a Link field.

    Uses ensure_item_exists() from existing BOM Upload module (idempotent).
    Leaf items are handled later by create_bom_recursive().
    """
    for node in tree:
        if node.get("children"):
            ensure_item_exists(node["item_code"], node.get("description"), node.get("uom"))
            # Recurse into children that are also assemblies
            ensure_items_for_assemblies(node["children"])
```

**Signature:**
- **Input:** `docname` (str) - BOM Upload document name
- **Output:** dict with keys:
  - `status`: "success" | "blocked" | "requires_resolution"
  - `analysis`: Analysis results (if blocked/requires resolution)
  - `created`: Count of BOMs created
  - `skipped`: Count of BOMs skipped
  - `failed`: Count of failures
  - `errors`: List of error messages
  - `component_masters_created`: Count of Component Masters created

---

#### Function: `analyze_upload(tree, project)`

```python
def analyze_upload(tree, project):
    """
    Analyze upload tree for new, unchanged, changed, and blocked components.

    Args:
        tree (list): Hierarchical component tree
        project (str): Project name

    Returns:
        dict: Analysis results with categorized components
    """
    all_components = flatten_tree(tree)
    graph = build_dependency_graph(all_components)

    categorized = {
        'new': [],
        'unchanged': [],
        'changed': [],
        'loose_blocked': []
    }

    for item_code, data in graph.items():
        status, details = determine_component_status(
            item_code,
            data['node'],
            project
        )
        data['status'] = status
        data['details'] = details
        categorized[status].append(item_code)

    # Find blocking dependencies
    changed_set = set(categorized['changed'])
    loose_blocked_set = set(categorized['loose_blocked'])
    blocked_by_changes = find_blocked_ancestors(
        graph,
        changed_set,
        loose_blocked_set
    )

    # Build result
    can_create = []
    for item_code in categorized['new'] + categorized['unchanged']:
        if item_code not in blocked_by_changes:
            can_create.append(graph[item_code]['node'])

    return {
        'can_create': can_create,
        'changed_components': [graph[ic] for ic in categorized['changed']],
        'loose_blocked': [graph[ic] for ic in categorized['loose_blocked']],
        'blocked_by_dependencies': blocked_by_changes,
        'summary': {
            'total': len(all_components),
            'new': len(categorized['new']),
            'unchanged': len(categorized['unchanged']),
            'changed': len(categorized['changed']),
            'loose_blocked': len(categorized['loose_blocked']),
            'can_create': len(can_create),
            'blocked': len(blocked_by_changes)
        }
    }
```

**Signature:**
- **Input:**
  - `tree` (list): Tree structure from build_tree()
  - `project` (str): Project name
- **Output:** dict with keys:
  - `can_create`: List of nodes safe to create
  - `changed_components`: List of changed component data
  - `loose_blocked`: List of loose items blocking creation
  - `blocked_by_dependencies`: Dict mapping blocked items to reasons
  - `summary`: Summary statistics

---

#### Function: `determine_component_status(item_code, node, project)`

```python
def determine_component_status(item_code, node, project):
    """
    Determine if component is new, unchanged, or changed.

    Args:
        item_code (str): Item code
        node (dict): Component node from tree
        project (str): Project name

    Returns:
        tuple: (status, details) where status is one of:
               'new', 'unchanged', 'changed', 'loose_blocked'
    """
    component_master = frappe.db.get_value(
        "Project Component Master",
        {"project": project, "item_code": item_code},
        ["name", "is_loose_item", "can_be_converted_to_bom",
         "bom_structure_hash", "active_bom"],
        as_dict=True
    )

    if not component_master:
        return "new", {"first_time": True}

    # Check loose item blocking
    if component_master.is_loose_item and not component_master.can_be_converted_to_bom:
        return "loose_blocked", {
            "component_master": component_master.name,
            "message": f"Loose item {item_code} not enabled for BOM conversion"
        }

    # Check for BOM changes
    if not component_master.active_bom:
        return "changed", {
            "change_type": "new_bom",
            "component_master": component_master.name
        }

    # Compare BOM structures
    new_hash = calculate_bom_structure_hash(node['children'])
    existing_hash = component_master.bom_structure_hash

    if new_hash != existing_hash:
        procurement_docs = get_procurement_documents(project, item_code)
        return "changed", {
            "change_type": "bom_structure",
            "component_master": component_master.name,
            "old_bom": component_master.active_bom,
            "old_hash": existing_hash,
            "new_hash": new_hash,
            "procurement_status": procurement_docs
        }

    return "unchanged", {
        "component_master": component_master.name,
        "bom": component_master.active_bom
    }
```

**Signature:**
- **Input:**
  - `item_code` (str): Item code
  - `node` (dict): Component data
  - `project` (str): Project name
- **Output:** tuple (status, details)
  - `status`: "new" | "unchanged" | "changed" | "loose_blocked"
  - `details`: dict with contextual information

---

#### Function: `calculate_bom_structure_hash(children)`

```python
import hashlib

def calculate_bom_structure_hash(children):
    """
    Create hash of BOM structure for comparison.

    Args:
        children (list): List of child components

    Returns:
        str: MD5 hash of sorted (item_code, qty) tuples
    """
    structure = sorted(
        [(child['item_code'], float(child['qty'])) for child in children],
        key=lambda x: x[0]
    )
    return hashlib.md5(str(structure).encode()).hexdigest()
```

**Signature:**
- **Input:** `children` (list): Child component list
- **Output:** str (MD5 hash)

---

#### Function: `create_or_update_component_master(node, project)`

```python
def create_or_update_component_master(node, project):
    """
    Create or update Project Component Master entry for a component.

    Args:
        node (dict): Component node from tree
        project (str): Project name

    Returns:
        dict: {'created': bool, 'name': str, 'doc': Document}
    """
    existing = frappe.db.exists("Project Component Master", {
        "project": project,
        "item_code": node['item_code']
    })

    if existing:
        doc = frappe.get_doc("Project Component Master", existing)
        doc.bom_level = node['level']
        doc.has_bom = 1 if node['children'] else 0
        doc.bom_structure_hash = calculate_bom_structure_hash(node['children'])
        doc.save(ignore_permissions=True)
        return {'created': False, 'name': doc.name, 'doc': doc}

    else:
        doc = frappe.get_doc({
            "doctype": "Project Component Master",
            "project": project,
            "item_code": node['item_code'],
            "item_name": node['description'],
            "description": node['description'],
            "bom_level": node['level'],
            "has_bom": 1 if node['children'] else 0,
            "is_loose_item": 0,
            "design_status": "Design Released",
            "bom_structure_hash": calculate_bom_structure_hash(node['children'])
        })
        doc.insert(ignore_permissions=True)
        return {'created': True, 'name': doc.name, 'doc': doc}
```

**Signature:**
- **Input:**
  - `node` (dict): Component data
  - `project` (str): Project name
- **Output:** dict with keys 'created', 'name', 'doc'

---

#### Function: `find_blocked_ancestors(graph, changed_set, loose_blocked_set)`

```python
def find_blocked_ancestors(graph, changed_set, loose_blocked_set):
    """
    Find all components blocked by changed or loose-blocked children.

    Args:
        graph (dict): Dependency graph {item_code: {node, children, status}}
        changed_set (set): Set of changed item codes
        loose_blocked_set (set): Set of loose-blocked item codes

    Returns:
        dict: Mapping of blocked item codes to list of blocking reasons
    """
    blocked = {}

    for item_code, data in graph.items():
        if data['status'] in ['new', 'unchanged']:
            blocking_children = []

            for child_code in data['children']:
                if child_code in changed_set:
                    blocking_children.append({
                        'item': child_code,
                        'reason': 'BOM structure changed'
                    })
                elif child_code in loose_blocked_set:
                    blocking_children.append({
                        'item': child_code,
                        'reason': 'Loose item conversion not enabled'
                    })
                # Check if child is already blocked
                elif child_code in blocked:
                    blocking_children.append({
                        'item': child_code,
                        'reason': f'Depends on blocked component'
                    })

            if blocking_children:
                blocked[item_code] = blocking_children

    return blocked
```

**Signature:**
- **Input:**
  - `graph` (dict): Dependency graph
  - `changed_set` (set): Changed item codes
  - `loose_blocked_set` (set): Loose-blocked item codes
- **Output:** dict mapping blocked items to reasons

---

### 2.3 Client-Side Enhancement

**File Location:** `clevertech/doctype/bom_upload/bom_upload.js`

**Add New Button Handler:**

```javascript
frappe.ui.form.on('BOM Upload', {
    create_boms_with_validation(frm) {
        if (!frm.doc.bom_file) {
            frappe.msgprint("Please attach a BOM Excel file first.");
            return;
        }

        frappe.call({
            method: 'clevertech.clevertech.doctype.bom_upload.bom_upload_enhanced.create_boms_with_validation',
            args: {
                docname: frm.doc.name
            },
            freeze: true,
            freeze_message: __('Analyzing BOM upload...'),
            callback(r) {
                if (!r.message) {
                    frappe.msgprint({
                        title: __('Error'),
                        message: __('No response from server'),
                        indicator: 'red'
                    });
                    return;
                }

                const result = r.message;

                if (result.status === 'blocked') {
                    show_loose_items_blocked_dialog(result);
                }
                else if (result.status === 'requires_resolution') {
                    show_change_resolution_dialog(result.analysis, frm);
                }
                else if (result.status === 'success') {
                    show_upload_success(result);
                    frm.reload_doc();
                }
            },
            error(r) {
                frappe.msgprint({
                    title: __('Error'),
                    message: __('Failed to process BOM upload. Check error log.'),
                    indicator: 'red'
                });
            }
        });
    }
});

function show_loose_items_blocked_dialog(data) {
    let html = `
        <div class="alert alert-danger">
            <h5><i class="fa fa-lock"></i> Loose Items Blocking BOM Creation</h5>
            <p>The following loose items must have "Can be converted to BOM" enabled first:</p>
            <ul>
                ${data.analysis.loose_blocked.map(item => `
                    <li>
                        <b>${item.node.item_code}</b> - ${item.details.message}
                        <br><small>Go to Project Component Master to enable conversion</small>
                    </li>
                `).join('')}
            </ul>
        </div>
    `;

    frappe.msgprint({
        title: __('Upload Blocked'),
        message: html,
        indicator: 'red',
        primary_action: {
            label: __('Open Component Master List'),
            action: function() {
                frappe.set_route('List', 'Project Component Master', {
                    'project': data.analysis.loose_blocked[0].node.project,
                    'is_loose_item': 1
                });
            }
        }
    });
}

function show_change_resolution_dialog(analysis, frm) {
    let changed_components = analysis.changed_components;
    let blocked_components = analysis.blocked_by_dependencies;

    let html = `
        <div class="bom-change-resolution">
            <h5><i class="fa fa-warning"></i> BOM Upload Analysis</h5>

            <div class="summary" style="margin: 15px 0;">
                <table class="table table-bordered table-sm">
                    <tr class="text-success">
                        <td><i class="fa fa-check"></i> Can Create Immediately:</td>
                        <td><b>${analysis.summary.can_create}</b> components</td>
                    </tr>
                    <tr class="text-warning">
                        <td><i class="fa fa-exclamation-triangle"></i> Changed Components:</td>
                        <td><b>${analysis.summary.changed}</b> components</td>
                    </tr>
                    <tr class="text-danger">
                        <td><i class="fa fa-ban"></i> Blocked by Dependencies:</td>
                        <td><b>${analysis.summary.blocked}</b> components</td>
                    </tr>
                </table>
            </div>

            ${changed_components.length > 0 ? `
                <div class="changed-components" style="margin-bottom: 20px;">
                    <h6 class="text-warning">
                        <i class="fa fa-exclamation-triangle"></i>
                        Changed Components Requiring Resolution:
                    </h6>
                    ${changed_components.map((comp, idx) => `
                        <div class="card mb-3" style="border-left: 3px solid #ffa00a;">
                            <div class="card-body">
                                <h6>[${idx+1}/${changed_components.length}] ${comp.node.item_code}</h6>
                                <p><b>Change Type:</b> ${comp.details.change_type}</p>
                                <p><b>Old BOM:</b>
                                    ${comp.details.old_bom ?
                                        `<a href="/app/bom/${comp.details.old_bom}">${comp.details.old_bom}</a>`
                                        : 'None'}
                                </p>
                                ${comp.details.procurement_status && comp.details.procurement_status.length > 0 ? `
                                    <div class="alert alert-warning">
                                        <b><i class="fa fa-warning"></i> Active Procurement:</b>
                                        <ul style="margin: 5px 0 0 20px;">
                                            ${comp.details.procurement_status.map(doc =>
                                                `<li>${doc.doctype}: ${doc.name} (${doc.status})</li>`
                                            ).join('')}
                                        </ul>
                                    </div>
                                ` : ''}
                                <p class="text-muted">
                                    <small>
                                        <i class="fa fa-info-circle"></i>
                                        Action: Deactivate old BOM manually, then re-run upload
                                    </small>
                                </p>
                            </div>
                        </div>
                    `).join('')}
                </div>
            ` : ''}

            ${Object.keys(blocked_components).length > 0 ? `
                <div class="blocked-components">
                    <h6 class="text-danger">
                        <i class="fa fa-ban"></i> Components Blocked by Dependencies:
                    </h6>
                    <ul>
                        ${Object.entries(blocked_components).map(([item, reasons]) => `
                            <li>
                                <b>${item}</b>
                                <ul style="margin-left: 20px;">
                                    ${reasons.map(r => `
                                        <li>${r.item}: ${r.reason}</li>
                                    `).join('')}
                                </ul>
                            </li>
                        `).join('')}
                    </ul>
                </div>
            ` : ''}

            <hr>
            <div class="alert alert-info">
                <h6><i class="fa fa-lightbulb-o"></i> Next Steps:</h6>
                <ol style="margin: 10px 0 0 20px;">
                    <li>Review changed components above</li>
                    <li>Deactivate old BOMs in BOM List</li>
                    <li>Re-run "Create BOMs with Validation" to complete upload</li>
                </ol>
            </div>
        </div>
    `;

    let d = new frappe.ui.Dialog({
        title: __('BOM Changes Detected - Resolution Required'),
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'analysis_html',
                options: html
            }
        ],
        size: 'large',
        primary_action_label: __('Open BOM List'),
        primary_action: function() {
            frappe.set_route('List', 'BOM', {
                'item': ['in', changed_components.map(c => c.node.item_code)],
                'is_active': 1
            });
            d.hide();
        }
    });

    d.show();
}

function show_upload_success(result) {
    let html = `
        <div class="alert alert-success">
            <h5><i class="fa fa-check-circle"></i> BOM Upload Complete</h5>
            <table class="table table-sm" style="margin-top: 15px;">
                <tr>
                    <td><i class="fa fa-plus-circle text-success"></i> BOMs Created:</td>
                    <td><b>${result.created}</b></td>
                </tr>
                <tr>
                    <td><i class="fa fa-minus-circle text-muted"></i> Skipped (Unchanged):</td>
                    <td><b>${result.skipped}</b></td>
                </tr>
                <tr>
                    <td><i class="fa fa-times-circle text-danger"></i> Failed:</td>
                    <td><b>${result.failed}</b></td>
                </tr>
                <tr class="text-primary">
                    <td><i class="fa fa-cube"></i> Component Masters Created:</td>
                    <td><b>${result.component_masters_created}</b></td>
                </tr>
            </table>
            ${result.errors && result.errors.length > 0 ? `
                <hr>
                <h6 class="text-danger">Errors:</h6>
                <ul>${result.errors.map(e => `<li>${e}</li>`).join('')}</ul>
            ` : ''}
        </div>
    `;

    frappe.msgprint({
        title: __('Success'),
        message: html,
        indicator: 'green'
    });
}
```

---

## 3. Event Hooks and Validation

### 3.0 BOM Event Hooks (✅ IMPLEMENTED)

**File Location:** `clevertech/project_component_master/bom_hooks.py`

**Purpose:** Auto-populate BOM Usage child table when BOMs are submitted, cancelled, or updated.

**Implementation Status:** ✅ Complete (2026-01-26)

**Key Functions:**

```python
def on_bom_submit(doc, method=None):
    """
    Called when BOM is submitted.
    - Shows info message if project BOM is not tracked in Component Master
    - Updates BOM Usage table for all child items
    - Sets has_bom, active_bom, and bom_structure_hash fields
    - Uses silent skip pattern for non-project BOMs
    """

def on_bom_cancel(doc, method=None):
    """
    Called when BOM is cancelled.
    - Removes BOM Usage entries for all child items
    - Clears has_bom, active_bom, bom_structure_hash fields
    - Silent skip if not tracked
    """

def on_bom_update(doc, method=None):
    """
    Called when BOM is updated after submission.
    - Detects structure changes via hash comparison
    - Shows orange alert if structure changed
    - Refreshes BOM Usage entries (adds new, removes obsolete)
    """
```

**Design Patterns:**

1. **Silent Skip Pattern:**
   - Only processes BOMs with `project` field populated
   - Only updates Component Masters that exist
   - No errors for non-tracked BOMs or items

2. **Info Messages for Untracked BOMs:**
   - Blue (info level) message when project BOM is not tracked
   - Helps catch accidental omissions
   - Non-intrusive, not blocking

3. **Hash-Based Change Detection:**
   - MD5 hash of sorted (item_code, qty) tuples
   - Fast comparison for structure changes
   - Alerts user when BOM structure modified

**Helper Functions:**

- `get_component_master()`: Fetch Component Master by project + item
- `add_or_update_bom_usage()`: Add/update BOM Usage row
- `remove_bom_usage()`: Remove BOM Usage row
- `refresh_bom_usage()`: Sync BOM Usage with current BOM items
- `update_component_master_bom_fields()`: Update has_bom, active_bom, hash
- `clear_component_master_bom_fields()`: Clear BOM fields on cancel
- `calculate_bom_structure_hash()`: Calculate MD5 hash

**Hook Registration:** See hooks.py section below (lines 1340-1344)

---

### 3.1 Material Request Validation

**File Location:** `clevertech/project_component_master/material_request_validation.py`

```python
import frappe
from frappe import _

def validate_material_request_qty(doc, method):
    """
    Validate MR quantities against Project Component Master limits.

    Hook: Material Request validate event

    Args:
        doc (Document): Material Request document
        method (str): Hook method name (not used)
    """
    if not doc.project:
        return  # No project, skip validation

    for item in doc.items:
        validate_item_qty(doc.project, item.item_code, item.qty, doc.name)


def validate_item_qty(project, item_code, mr_qty, mr_name):
    """
    Validate individual item quantity against Component Master limit.

    Args:
        project (str): Project name
        item_code (str): Item code
        mr_qty (float): Requested quantity in MR
        mr_name (str): MR document name (for exclusion in existing qty calc)

    Raises:
        frappe.ValidationError: If quantity exceeds limit
    """
    component = frappe.db.get_value(
        "Project Component Master",
        {"project": project, "item_code": item_code},
        ["name", "total_qty_limit", "total_qty_procured", "procurement_balance",
         "is_loose_item", "loose_qty_required", "bom_qty_required",
         "bom_conversion_status"],
        as_dict=True
    )

    if not component:
        return  # Item not in Component Master, no restriction

    # Get existing MR quantities (excluding current MR if updating)
    existing_mr_qty = frappe.db.sql("""
        SELECT COALESCE(SUM(mri.qty), 0)
        FROM `tabMaterial Request Item` mri
        INNER JOIN `tabMaterial Request` mr ON mri.parent = mr.name
        WHERE mr.project = %s
        AND mri.item_code = %s
        AND mr.docstatus < 2
        AND mr.name != %s
    """, (project, item_code, mr_name))[0][0] or 0

    total_procurement = existing_mr_qty + mr_qty

    # Hard limit check
    if total_procurement > component.total_qty_limit:
        frappe.throw(
            _("Cannot add {0} units of {1} to Material Request.<br><br>"
              "<b>Procurement Limit Exceeded:</b><br>"
              "<table class='table table-bordered' style='width: auto; margin-top: 10px;'>"
              "<tr><td>Total Limit:</td><td style='text-align: right;'><b>{2}</b></td></tr>"
              "<tr><td>Existing MRs:</td><td style='text-align: right;'>{3}</td></tr>"
              "<tr><td>This MR:</td><td style='text-align: right;'>{4}</td></tr>"
              "<tr class='text-danger'><td>Total:</td><td style='text-align: right;'><b>{5}</b></td></tr>"
              "<tr class='text-success'><td>Max Allowed:</td><td style='text-align: right;'><b>{6}</b></td></tr>"
              "</table>"
              "<br><small><i class='fa fa-info-circle'></i> "
              "Update quantity limit in Project Component Master if needed</small>").format(
                  mr_qty,
                  frappe.bold(item_code),
                  component.total_qty_limit,
                  existing_mr_qty,
                  mr_qty,
                  total_procurement,
                  max(0, component.total_qty_limit - existing_mr_qty)
              ),
            title="Procurement Limit Exceeded"
        )

    # Warning for loose item over-procurement
    if component.is_loose_item and component.bom_conversion_status == "Converted to BOM":
        loose_qty = component.loose_qty_required or 0
        bom_qty = component.bom_qty_required or 0

        if loose_qty > bom_qty:
            frappe.msgprint(
                _("<div class='alert alert-warning'>"
                  "<i class='fa fa-exclamation-triangle'></i> <b>Note:</b> "
                  "Item {0} was procured as loose item (<b>{1} units</b>) "
                  "but BOM requires only <b>{2} units</b>. "
                  "Current MR adds <b>{3} units</b> (Total limit: <b>{4}</b>)"
                  "</div>").format(
                      frappe.bold(item_code),
                      loose_qty,
                      bom_qty,
                      mr_qty,
                      component.total_qty_limit
                  ),
                indicator="orange",
                title="Over-procurement Warning"
            )
```

**Hook Registration in hooks.py:**

```python
doc_events = {
    "BOM": {
        "on_submit": "clevertech.project_component_master.bom_hooks.on_bom_submit",
        "on_cancel": "clevertech.project_component_master.bom_hooks.on_bom_cancel",
        "on_update_after_submit": "clevertech.project_component_master.bom_hooks.on_bom_update"
    },
    "Material Request": {
        "validate": "clevertech.project_component_master.material_request_validation.validate_material_request_qty",
        "on_submit": "clevertech.project_component_master.procurement_hooks.on_mr_submit",
        "on_cancel": "clevertech.project_component_master.procurement_hooks.on_mr_cancel"
    },
    "Request for Quotation": {
        "on_submit": "clevertech.project_component_master.procurement_hooks.on_rfq_submit",
        "on_cancel": "clevertech.project_component_master.procurement_hooks.on_rfq_cancel"
    },
    "Purchase Order": {
        "on_submit": "clevertech.project_component_master.procurement_hooks.on_po_submit",
        "on_cancel": "clevertech.project_component_master.procurement_hooks.on_po_cancel"
    },
    "Purchase Receipt": {
        "on_submit": "clevertech.project_component_master.procurement_hooks.on_pr_submit",
        "on_cancel": "clevertech.project_component_master.procurement_hooks.on_pr_cancel"
    }
}
```

**Note:** Supplier Quotations are NOT tracked in Procurement Records. Use standard ERPNext quotation comparison report linked to RFQ instead.

---

### 3.2 Project Component Master Auto-Calculations

**File Location:** `clevertech/doctype/project_component_master/project_component_master.py`

```python
import frappe
from frappe.model.document import Document

class ProjectComponentMaster(Document):

    def before_save(self):
        """Calculate auto-fields before saving"""
        self.calculate_bom_qty_required()
        self.calculate_total_qty_limit()
        self.calculate_procurement_totals()
        self.update_procurement_status()
        self.calculate_budgeted_rate_rollup()
        self.update_bom_conversion_status()

    def calculate_bom_qty_required(self):
        """Calculate total BOM qty needed across all parent assemblies.

        Multiplies qty_per_unit by the parent assembly's project_qty
        to get actual project requirement per BOM usage row.

        BUG (Phase 4): Currently sums raw qty_per_unit without multiplication.
        FIX (Phase 4B): Lookup parent's project_qty, multiply, store in total_qty_required.
        """
        total = 0
        for usage in self.bom_usage:
            # Phase 4B fix: multiply by parent assembly's project_qty
            parent_item = usage.parent_item
            if not parent_item and usage.parent_bom:
                parent_item = frappe.db.get_value("BOM", usage.parent_bom, "item")

            parent_project_qty = 1  # default for cutover or missing data
            if parent_item:
                parent_project_qty = frappe.db.get_value(
                    "Project Component Master",
                    {"project": self.project, "item_code": parent_item},
                    "project_qty"
                ) or 1

            qty_required = (usage.qty_per_unit or 0) * parent_project_qty
            usage.total_qty_required = qty_required
            total += qty_required
        self.bom_qty_required = total

    def calculate_total_qty_limit(self):
        """MAX(loose_qty, bom_qty) - hard procurement limit"""
        loose = self.loose_qty_required or 0
        bom = self.bom_qty_required or 0
        self.total_qty_limit = max(loose, bom)

    def calculate_procurement_totals(self):
        """Sum all procurement records"""
        total = 0
        for record in self.procurement_records:
            if record.document_type in ["Material Request", "Purchase Order"]:
                total += record.quantity or 0
        self.total_qty_procured = total
        self.procurement_balance = self.total_qty_limit - total

    def update_procurement_status(self):
        """Auto-set status based on quantities"""
        if self.total_qty_procured == 0:
            self.procurement_status = "Not Started"
        elif self.total_qty_procured >= self.total_qty_limit:
            if self.total_qty_procured > self.total_qty_limit:
                self.procurement_status = "Over-procured"
            else:
                self.procurement_status = "Completed"
        else:
            self.procurement_status = "In Progress"

    def calculate_budgeted_rate_rollup(self):
        """Roll up budgets from child components"""
        if not self.has_bom or not self.active_bom:
            return

        bom = frappe.get_doc("BOM", self.active_bom)
        total = 0

        for item in bom.items:
            # Check if child is also a managed component
            child_budget = frappe.db.get_value(
                "Project Component Master",
                {"project": self.project, "item_code": item.item_code},
                "budgeted_rate"
            )

            if child_budget:
                total += child_budget * item.qty
            else:
                # Use item's last purchase rate
                last_rate = frappe.db.get_value(
                    "Item",
                    item.item_code,
                    "last_purchase_rate"
                ) or 0
                total += last_rate * item.qty

        self.budgeted_rate_calculated = total

    def update_bom_conversion_status(self):
        """Update conversion status for loose items"""
        if not self.is_loose_item:
            self.bom_conversion_status = "Not Applicable"
            return

        if not self.can_be_converted_to_bom:
            self.bom_conversion_status = "Pending Conversion"
        elif len(self.bom_usage) == 0:
            self.bom_conversion_status = "Pending Conversion"
        elif len(self.bom_usage) == 1:
            self.bom_conversion_status = "Converted to BOM"
        else:
            self.bom_conversion_status = "Partial"
```

---

## 4. Reports

### 4.1 Component Procurement Status Report

**File Location:** `clevertech/report/component_procurement_status/component_procurement_status.json`

```json
{
 "add_total_row": 0,
 "columns": [],
 "creation": "2026-01-26 00:00:00.000000",
 "disable_prepared_report": 0,
 "disabled": 0,
 "docstatus": 0,
 "doctype": "Report",
 "filters": [],
 "idx": 0,
 "is_standard": "Yes",
 "json": "{}",
 "letter_head": "",
 "modified": "2026-01-26 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Clevertech",
 "name": "Component Procurement Status",
 "owner": "Administrator",
 "prepared_report": 0,
 "ref_doctype": "Project Component Master",
 "report_name": "Component Procurement Status",
 "report_type": "Script Report",
 "roles": [
  {
   "role": "System Manager"
  },
  {
   "role": "Manufacturing Manager"
  },
  {
   "role": "Purchase User"
  }
 ]
}
```

**File Location:** `clevertech/report/component_procurement_status/component_procurement_status.py`

```python
import frappe

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {
            "label": "Project",
            "fieldname": "project",
            "fieldtype": "Link",
            "options": "Project",
            "width": 150
        },
        {
            "label": "Component Code",
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 150
        },
        {
            "label": "Component Name",
            "fieldname": "item_name",
            "fieldtype": "Data",
            "width": 200
        },
        {
            "label": "BOM Level",
            "fieldname": "bom_level",
            "fieldtype": "Int",
            "width": 80
        },
        {
            "label": "Parent Component",
            "fieldname": "parent_component",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": "Has BOM",
            "fieldname": "has_bom",
            "fieldtype": "Check",
            "width": 80
        },
        {
            "label": "Is Loose Item",
            "fieldname": "is_loose_item",
            "fieldtype": "Check",
            "width": 100
        },
        {
            "label": "Design Status",
            "fieldname": "design_status",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": "Budgeted Rate",
            "fieldname": "budgeted_rate",
            "fieldtype": "Currency",
            "width": 120
        },
        {
            "label": "Qty Limit",
            "fieldname": "total_qty_limit",
            "fieldtype": "Float",
            "width": 100,
            "precision": 2
        },
        {
            "label": "Qty Procured",
            "fieldname": "total_qty_procured",
            "fieldtype": "Float",
            "width": 100,
            "precision": 2
        },
        {
            "label": "Balance",
            "fieldname": "procurement_balance",
            "fieldtype": "Float",
            "width": 100,
            "precision": 2
        },
        {
            "label": "Procurement Status",
            "fieldname": "procurement_status",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": "Active BOM",
            "fieldname": "active_bom",
            "fieldtype": "Link",
            "options": "BOM",
            "width": 150
        },
        {
            "label": "Target Date",
            "fieldname": "target_delivery_date",
            "fieldtype": "Date",
            "width": 100
        }
    ]

def get_data(filters):
    conditions = ["1=1"]

    if filters.get("project"):
        conditions.append(f"pcm.project = '{filters.get('project')}'")

    if filters.get("procurement_status"):
        conditions.append(f"pcm.procurement_status = '{filters.get('procurement_status')}'")

    if filters.get("is_loose_item"):
        conditions.append("pcm.is_loose_item = 1")

    if filters.get("design_status"):
        conditions.append(f"pcm.design_status = '{filters.get('design_status')}'")

    where_clause = " AND ".join(conditions)

    data = frappe.db.sql(f"""
        SELECT
            pcm.project,
            pcm.item_code,
            pcm.item_name,
            pcm.bom_level,
            pcm.parent_component,
            pcm.has_bom,
            pcm.is_loose_item,
            pcm.design_status,
            pcm.budgeted_rate,
            pcm.total_qty_limit,
            pcm.total_qty_procured,
            pcm.procurement_balance,
            pcm.procurement_status,
            pcm.active_bom,
            pcm.target_delivery_date
        FROM `tabProject Component Master` pcm
        WHERE {where_clause}
        ORDER BY pcm.project, pcm.bom_level, pcm.item_code
    """, as_dict=1)

    return data
```

**File Location:** `clevertech/report/component_procurement_status/component_procurement_status.js`

```javascript
frappe.query_reports["Component Procurement Status"] = {
    "filters": [
        {
            "fieldname": "project",
            "label": __("Project"),
            "fieldtype": "Link",
            "options": "Project",
            "reqd": 0
        },
        {
            "fieldname": "procurement_status",
            "label": __("Procurement Status"),
            "fieldtype": "Select",
            "options": "\nNot Started\nIn Progress\nCompleted\nOver-procured"
        },
        {
            "fieldname": "design_status",
            "label": __("Design Status"),
            "fieldtype": "Select",
            "options": "\nDraft\nDesign Released\nProcurement Ready\nObsolete"
        },
        {
            "fieldname": "is_loose_item",
            "label": __("Loose Items Only"),
            "fieldtype": "Check"
        }
    ],

    "formatter": function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        // Color-code procurement status
        if (column.fieldname == "procurement_status") {
            if (value == "Not Started") {
                value = `<span class="indicator-pill gray">${value}</span>`;
            } else if (value == "In Progress") {
                value = `<span class="indicator-pill yellow">${value}</span>`;
            } else if (value == "Completed") {
                value = `<span class="indicator-pill green">${value}</span>`;
            } else if (value == "Over-procured") {
                value = `<span class="indicator-pill red">${value}</span>`;
            }
        }

        // Highlight negative balance
        if (column.fieldname == "procurement_balance" && data.procurement_balance < 0) {
            value = `<span style="color: red; font-weight: bold;">${value}</span>`;
        }

        return value;
    }
};
```

---

## 5. Test Cases

### 5.1 Unit Tests

**File Location:** `clevertech/doctype/project_component_master/test_project_component_master.py`

```python
import frappe
import unittest
from clevertech.clevertech.doctype.bom_upload.bom_upload_enhanced import (
    calculate_bom_structure_hash,
    determine_component_status,
    analyze_upload
)

class TestProjectComponentMaster(unittest.TestCase):

    def setUp(self):
        """Set up test data"""
        self.test_project = "TEST-PROJ-001"
        self.test_item = "TEST-MOTOR-001"

        # Create test project if not exists
        if not frappe.db.exists("Project", self.test_project):
            frappe.get_doc({
                "doctype": "Project",
                "project_name": self.test_project
            }).insert()

        # Create test item if not exists
        if not frappe.db.exists("Item", self.test_item):
            frappe.get_doc({
                "doctype": "Item",
                "item_code": self.test_item,
                "item_name": "Test Motor Assembly",
                "item_group": "All Item Groups",
                "stock_uom": "Nos"
            }).insert()

    def tearDown(self):
        """Clean up test data"""
        # Delete test component master
        frappe.db.sql("""
            DELETE FROM `tabProject Component Master`
            WHERE project = %s
        """, self.test_project)
        frappe.db.commit()

    def test_calculate_bom_structure_hash(self):
        """Test BOM structure hash calculation"""
        children1 = [
            {"item_code": "ITEM-A", "qty": 2},
            {"item_code": "ITEM-B", "qty": 1}
        ]

        children2 = [
            {"item_code": "ITEM-B", "qty": 1},
            {"item_code": "ITEM-A", "qty": 2}
        ]

        children3 = [
            {"item_code": "ITEM-A", "qty": 3},  # Different qty
            {"item_code": "ITEM-B", "qty": 1}
        ]

        hash1 = calculate_bom_structure_hash(children1)
        hash2 = calculate_bom_structure_hash(children2)
        hash3 = calculate_bom_structure_hash(children3)

        # Same structure (order doesn't matter)
        self.assertEqual(hash1, hash2)

        # Different structure (qty changed)
        self.assertNotEqual(hash1, hash3)

    def test_component_master_creation(self):
        """Test creating Project Component Master"""
        doc = frappe.get_doc({
            "doctype": "Project Component Master",
            "project": self.test_project,
            "item_code": self.test_item,
            "bom_level": 0,
            "is_loose_item": 0,
            "design_status": "Design Released"
        })
        doc.insert()

        # Verify created
        self.assertTrue(frappe.db.exists("Project Component Master", doc.name))

        # Clean up
        doc.delete()

    def test_loose_qty_calculation(self):
        """Test procurement quantity limit calculation"""
        doc = frappe.get_doc({
            "doctype": "Project Component Master",
            "project": self.test_project,
            "item_code": self.test_item,
            "is_loose_item": 1,
            "loose_qty_required": 100,
            "bom_qty_required": 150
        })
        doc.insert()

        # total_qty_limit should be MAX(100, 150) = 150
        self.assertEqual(doc.total_qty_limit, 150)

        # Update loose qty to be higher
        doc.loose_qty_required = 200
        doc.save()

        # total_qty_limit should be MAX(200, 150) = 200
        self.assertEqual(doc.total_qty_limit, 200)

        # Clean up
        doc.delete()

    def test_procurement_status_calculation(self):
        """Test procurement status auto-calculation"""
        doc = frappe.get_doc({
            "doctype": "Project Component Master",
            "project": self.test_project,
            "item_code": self.test_item,
            "loose_qty_required": 100,
            "bom_qty_required": 0
        })
        doc.insert()

        # Initially not started
        self.assertEqual(doc.procurement_status, "Not Started")

        # Add procurement record
        doc.append("procurement_records", {
            "document_type": "Material Request",
            "document_name": "MR-TEST-001",
            "quantity": 50,
            "procurement_source": "Loose Item"
        })
        doc.save()

        # Should be in progress
        self.assertEqual(doc.procurement_status, "In Progress")
        self.assertEqual(doc.total_qty_procured, 50)
        self.assertEqual(doc.procurement_balance, 50)

        # Add more procurement to complete
        doc.append("procurement_records", {
            "document_type": "Material Request",
            "document_name": "MR-TEST-002",
            "quantity": 50,
            "procurement_source": "Loose Item"
        })
        doc.save()

        # Should be completed
        self.assertEqual(doc.procurement_status, "Completed")
        self.assertEqual(doc.total_qty_procured, 100)
        self.assertEqual(doc.procurement_balance, 0)

        # Add over-procurement
        doc.append("procurement_records", {
            "document_type": "Material Request",
            "document_name": "MR-TEST-003",
            "quantity": 20,
            "procurement_source": "Loose Item"
        })
        doc.save()

        # Should be over-procured
        self.assertEqual(doc.procurement_status, "Over-procured")
        self.assertEqual(doc.total_qty_procured, 120)
        self.assertEqual(doc.procurement_balance, -20)

        # Clean up
        doc.delete()

    def test_unique_constraint(self):
        """Test unique constraint on project + item_code"""
        doc1 = frappe.get_doc({
            "doctype": "Project Component Master",
            "project": self.test_project,
            "item_code": self.test_item,
            "bom_level": 0
        })
        doc1.insert()

        # Try to create duplicate
        doc2 = frappe.get_doc({
            "doctype": "Project Component Master",
            "project": self.test_project,
            "item_code": self.test_item,
            "bom_level": 1
        })

        with self.assertRaises(frappe.DuplicateEntryError):
            doc2.insert()

        # Clean up
        doc1.delete()

# Run tests
if __name__ == "__main__":
    unittest.main()
```

---

### 5.2 Integration Tests

**File Location:** `clevertech/doctype/bom_upload/test_bom_upload_enhanced.py`

```python
import frappe
import unittest
import os
from openpyxl import Workbook
from io import BytesIO
from clevertech.clevertech.doctype.bom_upload.bom_upload_enhanced import (
    create_boms_with_validation,
    analyze_upload
)

class TestBOMUploadEnhanced(unittest.TestCase):

    def setUp(self):
        """Set up test data"""
        self.test_project = "TEST-PROJ-002"

        if not frappe.db.exists("Project", self.test_project):
            frappe.get_doc({
                "doctype": "Project",
                "project_name": self.test_project
            }).insert()

    def tearDown(self):
        """Clean up"""
        frappe.db.sql("""
            DELETE FROM `tabProject Component Master`
            WHERE project = %s
        """, self.test_project)
        frappe.db.commit()

    def create_test_excel(self, data):
        """Create test Excel file"""
        wb = Workbook()
        ws = wb.active

        # Headers (row 1-2)
        ws['A1'] = 'Position'
        ws['C1'] = 'Code'
        ws['D1'] = 'Description'
        ws['E1'] = 'Qty'
        ws['AR1'] = 'Level'

        # Data (starting row 3)
        for idx, row in enumerate(data, start=3):
            ws[f'A{idx}'] = row.get('position', '')
            ws[f'C{idx}'] = row.get('item_code', '')
            ws[f'D{idx}'] = row.get('description', '')
            ws[f'E{idx}'] = row.get('qty', 1)
            ws[f'AM{idx}'] = 'Nos'
            ws[f'AR{idx}'] = row.get('level', 0)

        # Save to BytesIO
        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        return buffer

    def test_new_component_upload(self):
        """Test uploading completely new components"""
        data = [
            {'position': '1', 'item_code': 'ASM-001', 'description': 'Assembly 1', 'level': 0, 'qty': 1},
            {'position': '1.1', 'item_code': 'PART-001', 'description': 'Part 1', 'level': 1, 'qty': 2}
        ]

        excel_buffer = self.create_test_excel(data)

        # Create file
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": "test_bom.xlsx",
            "content": excel_buffer.getvalue(),
            "is_private": 1
        })
        file_doc.save()

        # Create BOM Upload
        upload_doc = frappe.get_doc({
            "doctype": "BOM Upload",
            "project": self.test_project,
            "bom_file": file_doc.file_url
        })
        upload_doc.insert()

        # Run upload with validation
        result = create_boms_with_validation(upload_doc.name)

        # Verify
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['created'], 1)  # Only ASM-001 (has children)
        self.assertEqual(result['component_masters_created'], 1)

        # Verify Component Master created
        self.assertTrue(frappe.db.exists("Project Component Master", {
            "project": self.test_project,
            "item_code": "ASM-001"
        }))

        # Clean up
        file_doc.delete()
        upload_doc.delete()

    def test_loose_item_blocking(self):
        """Test that loose items without conversion enabled block upload"""
        # Create loose item Component Master
        loose_component = frappe.get_doc({
            "doctype": "Project Component Master",
            "project": self.test_project,
            "item_code": "BEARING-001",
            "is_loose_item": 1,
            "can_be_converted_to_bom": 0,  # Not enabled
            "loose_qty_required": 100
        })
        loose_component.insert()

        # Upload BOM using this loose item
        data = [
            {'position': '1', 'item_code': 'MOTOR-001', 'description': 'Motor', 'level': 0, 'qty': 1},
            {'position': '1.1', 'item_code': 'BEARING-001', 'description': 'Bearing', 'level': 1, 'qty': 2}
        ]

        excel_buffer = self.create_test_excel(data)

        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": "test_loose.xlsx",
            "content": excel_buffer.getvalue(),
            "is_private": 1
        })
        file_doc.save()

        upload_doc = frappe.get_doc({
            "doctype": "BOM Upload",
            "project": self.test_project,
            "bom_file": file_doc.file_url
        })
        upload_doc.insert()

        # Run upload
        result = create_boms_with_validation(upload_doc.name)

        # Should be blocked
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['reason'], 'loose_items_not_enabled')

        # Clean up
        loose_component.delete()
        file_doc.delete()
        upload_doc.delete()

    def test_bom_change_detection(self):
        """Test detection of BOM structure changes"""
        # First upload
        data1 = [
            {'position': '1', 'item_code': 'GEARBOX-001', 'description': 'Gearbox', 'level': 0, 'qty': 1},
            {'position': '1.1', 'item_code': 'GEAR-001', 'description': 'Gear', 'level': 1, 'qty': 2}
        ]

        excel_buffer1 = self.create_test_excel(data1)
        file_doc1 = frappe.get_doc({
            "doctype": "File",
            "file_name": "test_v1.xlsx",
            "content": excel_buffer1.getvalue(),
            "is_private": 1
        })
        file_doc1.save()

        upload_doc1 = frappe.get_doc({
            "doctype": "BOM Upload",
            "project": self.test_project,
            "bom_file": file_doc1.file_url
        })
        upload_doc1.insert()

        result1 = create_boms_with_validation(upload_doc1.name)
        self.assertEqual(result1['status'], 'success')

        # Second upload with changed BOM
        data2 = [
            {'position': '1', 'item_code': 'GEARBOX-001', 'description': 'Gearbox', 'level': 0, 'qty': 1},
            {'position': '1.1', 'item_code': 'GEAR-001', 'description': 'Gear', 'level': 1, 'qty': 3},  # Qty changed!
            {'position': '1.2', 'item_code': 'SHAFT-001', 'description': 'Shaft', 'level': 1, 'qty': 1}  # New item!
        ]

        excel_buffer2 = self.create_test_excel(data2)
        file_doc2 = frappe.get_doc({
            "doctype": "File",
            "file_name": "test_v2.xlsx",
            "content": excel_buffer2.getvalue(),
            "is_private": 1
        })
        file_doc2.save()

        upload_doc2 = frappe.get_doc({
            "doctype": "BOM Upload",
            "project": self.test_project,
            "bom_file": file_doc2.file_url
        })
        upload_doc2.insert()

        result2 = create_boms_with_validation(upload_doc2.name)

        # Should require resolution
        self.assertEqual(result2['status'], 'requires_resolution')
        self.assertEqual(len(result2['analysis']['changed_components']), 1)
        self.assertEqual(result2['analysis']['changed_components'][0]['node']['item_code'], 'GEARBOX-001')

        # Clean up
        file_doc1.delete()
        file_doc2.delete()
        upload_doc1.delete()
        upload_doc2.delete()

# Run tests
if __name__ == "__main__":
    unittest.main()
```

---

### 5.3 Material Request Validation Tests

**File Location:** `clevertech/project_component_master/test_material_request_validation.py`

```python
import frappe
import unittest
from frappe.exceptions import ValidationError

class TestMaterialRequestValidation(unittest.TestCase):

    def setUp(self):
        """Set up test data"""
        self.test_project = "TEST-PROJ-003"
        self.test_item = "TEST-BEARING-001"

        # Create project
        if not frappe.db.exists("Project", self.test_project):
            frappe.get_doc({
                "doctype": "Project",
                "project_name": self.test_project
            }).insert()

        # Create item
        if not frappe.db.exists("Item", self.test_item):
            frappe.get_doc({
                "doctype": "Item",
                "item_code": self.test_item,
                "item_name": "Test Bearing",
                "item_group": "All Item Groups",
                "stock_uom": "Nos"
            }).insert()

        # Create Component Master with limit
        self.component = frappe.get_doc({
            "doctype": "Project Component Master",
            "project": self.test_project,
            "item_code": self.test_item,
            "loose_qty_required": 100,
            "bom_qty_required": 0
        })
        self.component.insert()

    def tearDown(self):
        """Clean up"""
        self.component.delete()
        frappe.db.commit()

    def test_within_limit(self):
        """Test MR creation within limit"""
        mr = frappe.get_doc({
            "doctype": "Material Request",
            "project": self.test_project,
            "material_request_type": "Purchase",
            "transaction_date": frappe.utils.today(),
            "items": [{
                "item_code": self.test_item,
                "qty": 50,
                "schedule_date": frappe.utils.today()
            }]
        })

        # Should not raise error
        mr.insert()
        self.assertTrue(mr.name)

        # Clean up
        mr.delete()

    def test_exact_limit(self):
        """Test MR creation at exact limit"""
        mr = frappe.get_doc({
            "doctype": "Material Request",
            "project": self.test_project,
            "material_request_type": "Purchase",
            "transaction_date": frappe.utils.today(),
            "items": [{
                "item_code": self.test_item,
                "qty": 100,  # Exact limit
                "schedule_date": frappe.utils.today()
            }]
        })

        # Should not raise error
        mr.insert()
        self.assertTrue(mr.name)

        # Clean up
        mr.delete()

    def test_exceeds_limit(self):
        """Test MR creation exceeding limit"""
        mr = frappe.get_doc({
            "doctype": "Material Request",
            "project": self.test_project,
            "material_request_type": "Purchase",
            "transaction_date": frappe.utils.today(),
            "items": [{
                "item_code": self.test_item,
                "qty": 150,  # Exceeds limit of 100
                "schedule_date": frappe.utils.today()
            }]
        })

        # Should raise error
        with self.assertRaises(ValidationError):
            mr.insert()

    def test_cumulative_limit(self):
        """Test cumulative MR quantities"""
        # First MR for 60 units
        mr1 = frappe.get_doc({
            "doctype": "Material Request",
            "project": self.test_project,
            "material_request_type": "Purchase",
            "transaction_date": frappe.utils.today(),
            "items": [{
                "item_code": self.test_item,
                "qty": 60,
                "schedule_date": frappe.utils.today()
            }]
        })
        mr1.insert()

        # Second MR for 30 units (total 90, within limit)
        mr2 = frappe.get_doc({
            "doctype": "Material Request",
            "project": self.test_project,
            "material_request_type": "Purchase",
            "transaction_date": frappe.utils.today(),
            "items": [{
                "item_code": self.test_item,
                "qty": 30,
                "schedule_date": frappe.utils.today()
            }]
        })
        mr2.insert()  # Should succeed

        # Third MR for 20 units (total 110, exceeds limit)
        mr3 = frappe.get_doc({
            "doctype": "Material Request",
            "project": self.test_project,
            "material_request_type": "Purchase",
            "transaction_date": frappe.utils.today(),
            "items": [{
                "item_code": self.test_item,
                "qty": 20,
                "schedule_date": frappe.utils.today()
            }]
        })

        with self.assertRaises(ValidationError):
            mr3.insert()  # Should fail

        # Clean up
        mr1.delete()
        mr2.delete()

# Run tests
if __name__ == "__main__":
    unittest.main()
```

---

## 6. Database Schema

### 6.1 Tables Created

**tabProject Component Master:**
```sql
CREATE TABLE `tabProject Component Master` (
  `name` varchar(140) NOT NULL,
  `creation` datetime(6) DEFAULT NULL,
  `modified` datetime(6) DEFAULT NULL,
  `modified_by` varchar(140) DEFAULT NULL,
  `owner` varchar(140) DEFAULT NULL,
  `docstatus` int(1) NOT NULL DEFAULT 0,
  `idx` int(8) NOT NULL DEFAULT 0,
  `project` varchar(140) DEFAULT NULL,
  `item_code` varchar(140) DEFAULT NULL,
  `item_name` varchar(140) DEFAULT NULL,
  `description` text,
  `component_image` text,
  `parent_component` varchar(140) DEFAULT NULL,
  `bom_level` int(11) DEFAULT 0,
  `has_bom` int(1) DEFAULT 0,
  `active_bom` varchar(140) DEFAULT NULL,
  `is_loose_item` int(1) DEFAULT 0,
  `loose_item_reason` text,
  `can_be_converted_to_bom` int(1) DEFAULT 0,
  `bom_conversion_status` varchar(140) DEFAULT NULL,
  `budgeted_rate` decimal(18,2) DEFAULT NULL,
  `budgeted_rate_calculated` decimal(18,2) DEFAULT NULL,
  `target_delivery_date` date DEFAULT NULL,
  `lead_time_days` int(11) DEFAULT NULL,
  `loose_qty_required` decimal(18,2) DEFAULT NULL,
  `bom_qty_required` decimal(18,2) DEFAULT NULL,
  `total_qty_limit` decimal(18,2) DEFAULT NULL,
  `total_qty_procured` decimal(18,2) DEFAULT NULL,
  `procurement_balance` decimal(18,2) DEFAULT NULL,
  `procurement_status` varchar(140) DEFAULT NULL,
  `design_status` varchar(140) DEFAULT NULL,
  `bom_structure_hash` text,
  `remarks` text,
  PRIMARY KEY (`name`),
  UNIQUE KEY `unique_project_item` (`project`,`item_code`),
  KEY `project` (`project`),
  KEY `item_code` (`item_code`),
  KEY `procurement_status` (`procurement_status`),
  KEY `design_status` (`design_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**tabComponent Procurement Record:**
```sql
CREATE TABLE `tabComponent Procurement Record` (
  `name` varchar(140) NOT NULL,
  `creation` datetime(6) DEFAULT NULL,
  `modified` datetime(6) DEFAULT NULL,
  `modified_by` varchar(140) DEFAULT NULL,
  `owner` varchar(140) DEFAULT NULL,
  `docstatus` int(1) NOT NULL DEFAULT 0,
  `parent` varchar(140) DEFAULT NULL,
  `parentfield` varchar(140) DEFAULT NULL,
  `parenttype` varchar(140) DEFAULT NULL,
  `idx` int(8) NOT NULL DEFAULT 0,
  `document_type` varchar(140) DEFAULT NULL,
  `document_name` varchar(140) DEFAULT NULL,
  `quantity` decimal(18,2) DEFAULT NULL,
  `rate` decimal(18,2) DEFAULT NULL,
  `amount` decimal(18,2) DEFAULT NULL,
  `date` date DEFAULT NULL,
  `status` varchar(140) DEFAULT NULL,
  `procurement_source` varchar(140) DEFAULT NULL,
  PRIMARY KEY (`name`),
  KEY `parent` (`parent`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**tabComponent BOM Usage:**
```sql
CREATE TABLE `tabComponent BOM Usage` (
  `name` varchar(140) NOT NULL,
  `creation` datetime(6) DEFAULT NULL,
  `modified` datetime(6) DEFAULT NULL,
  `modified_by` varchar(140) DEFAULT NULL,
  `owner` varchar(140) DEFAULT NULL,
  `docstatus` int(1) NOT NULL DEFAULT 0,
  `parent` varchar(140) DEFAULT NULL,
  `parentfield` varchar(140) DEFAULT NULL,
  `parenttype` varchar(140) DEFAULT NULL,
  `idx` int(8) NOT NULL DEFAULT 0,
  `parent_bom` varchar(140) DEFAULT NULL,
  `parent_item` varchar(140) DEFAULT NULL,
  `qty_per_unit` decimal(18,2) DEFAULT NULL,
  `total_qty_required` decimal(18,2) DEFAULT NULL,
  PRIMARY KEY (`name`),
  KEY `parent` (`parent`),
  KEY `parent_bom` (`parent_bom`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 7. API Specifications

### 7.1 REST API Endpoints

**Create BOMs with Validation:**
```
POST /api/method/clevertech.clevertech.doctype.bom_upload.bom_upload_enhanced.create_boms_with_validation
Content-Type: application/json

Request Body:
{
    "docname": "BOM-UPLOAD-00001"
}

Response (Success):
{
    "message": {
        "status": "success",
        "created": 10,
        "skipped": 5,
        "failed": 0,
        "errors": [],
        "component_masters_created": 8
    }
}

Response (Blocked):
{
    "message": {
        "status": "blocked",
        "reason": "loose_items_not_enabled",
        "analysis": {...}
    }
}

Response (Requires Resolution):
{
    "message": {
        "status": "requires_resolution",
        "analysis": {
            "changed_components": [...],
            "blocked_by_dependencies": {...},
            "summary": {...}
        }
    }
}
```

---

## 8. Implementation Checklist

### Phase 1: DocTypes ✅ (2026-01-26)
- [x] Create Project Component Master doctype
- [x] Create Component Procurement Record child table
- [x] Create Component BOM Usage child table
- [x] Test DocType creation and saving

### Phase 1A: BOM Event Hooks ✅ (2026-01-26)
- [x] Implement on_bom_submit hook
- [x] Implement on_bom_cancel hook
- [x] Implement on_bom_update hook
- [x] Implement calculate_bom_structure_hash() function
- [x] Register BOM hooks in hooks.py
- **File:** `project_component_master/bom_hooks.py`

### Phase 2A: Bulk Generation ✅ (2026-01-27)
- [x] Create generate_component_masters_from_boms() whitelisted function
- [x] Create populate_bom_usage_tables() helper
- [x] Reuse calculate_bom_structure_hash from bom_hooks (no duplication)
- [x] Add "Generate Component Masters" button on Project form
- [x] Register Project in doctype_js in hooks.py
- [x] Test on project SMR260001 (24 Component Masters created)
- **Files:**
  - `project_component_master/bulk_generation.py`
  - `public/js/project.js`

### Phase 2: BOM Upload Enhancement ✅ (2026-01-27)
- [x] Create bom_upload_enhanced.py module
- [x] Implement create_boms_with_validation() whitelisted entry point
- [x] Implement ensure_items_for_assemblies() — walks tree, creates Items before CMs
- [x] Implement create_component_masters_for_new_items() — creates CMs with active_bom=null
- [x] Implement analyze_upload() — categorizes components as new/unchanged/changed/blocked
- [x] Implement _determine_component_status() — hash comparison + loose item check
- [x] Implement _build_dependency_graph() — maps item_code to node/children/status
- [x] Implement _find_blocked_ancestors() — iterative blocking propagation up tree
- [x] Implement create_boms_and_link_components() — creates BOMs + links active_bom back
- [x] Implement calculate_tree_structure_hash() — MD5 hash for Excel tree nodes
- [x] Implement _serialize_analysis() — safe JSON serialization for client
- [x] Add `create_boms_with_validation` Button field to bom_upload.json
- [x] Implement client-side button handler in bom_upload.js
- [x] Implement _show_loose_items_blocked_dialog() — red blocked dialog
- [x] Implement _show_change_resolution_dialog() — orange change detection dialog
- [x] Implement _show_upload_success() — green success dialog
- **Files:**
  - `clevertech/doctype/bom_upload/bom_upload_enhanced.py` — Server logic
  - `clevertech/doctype/bom_upload/bom_upload.js` — Button handler + dialogs
  - `clevertech/doctype/bom_upload/bom_upload.json` — New button field

### Phase 3: Procurement Hooks ✅ (2026-01-27)
- [x] Create procurement_hooks.py module
- [x] Implement on_mr_submit / on_mr_cancel — Material Request tracking
- [x] Implement on_rfq_submit / on_rfq_cancel — RFQ tracking
- [x] Implement on_po_submit / on_po_cancel — Purchase Order tracking
- [x] Implement on_pr_submit / on_pr_cancel — Purchase Receipt tracking
- [x] Implement _add_procurement_records() — common add helper (idempotent)
- [x] Implement _remove_procurement_records() — common remove helper
- [x] Implement _get_project_from_doc() — extracts project from various doctypes
- [x] Implement _get_items_from_doc() — extracts item rows from various doctypes
- [x] Register all hooks in hooks.py (list syntax for multi-handler events)
- **File:** `project_component_master/procurement_hooks.py`

### Phase 3A: Material Request Validation ✅ (2026-01-27)
- [x] Create material_request_validation.py module
- [x] Implement validate_material_request_qty() — validate hook on MR
- [x] Implement _validate_item_qty() — per-item check against total_qty_limit
- [x] Hard block with detailed table (limit, existing MRs, this MR, max allowed)
- [x] Warning for loose item over-procurement (loose > BOM qty)
- [x] Register validate hook in hooks.py (list with existing validate handler)
- **File:** `project_component_master/material_request_validation.py`

### Phase 4: Auto-Calculations ✅ (2026-01-27)
- [x] Implement before_save() in ProjectComponentMaster class
- [x] Implement calculate_bom_qty_required() — sum from bom_usage child table (**Bug: missing project_qty multiplication — see Phase 4B**)
- [x] Implement calculate_total_qty_limit() — MAX(loose, bom)
- [x] Implement calculate_procurement_totals() — sum MR + PO from procurement_records
- [x] Implement update_procurement_status() — Not Started / In Progress / Completed / Over-procured
- [x] Implement calculate_budgeted_rate_rollup() — child budgets + leaf last_purchase_rate
- [x] Implement update_bom_conversion_status() — Not Applicable / Pending / Converted / Partial
- **File:** `clevertech/doctype/project_component_master/project_component_master.py`

### Phase 4B: Project Quantity Multiplication ⏳ (Pending — Decision 13)
- [ ] Add `project_qty` field to `project_component_master.json` (Float, editable, in Hierarchy section)
- [ ] Fix `calculate_bom_qty_required()` — multiply `qty_per_unit × parent_project_qty`, store in `total_qty_required`
- [ ] Update `bom_upload_enhanced.py` — walk tree top-down after upload, set `project_qty` on each Component Master (root qty from Excel, children = parent × qty)
- [ ] Update `bulk_generation.py` — set `project_qty = 1` as default for cutover-created Component Masters
- **Files:** `project_component_master.json`, `project_component_master.py`, `bom_upload_enhanced.py`, `bulk_generation.py`

### Phase 4A: Hooks Registration ✅ (2026-01-27)
- [x] Register procurement hooks for MR, RFQ, PO, PR in hooks.py
- [x] Register MR validation hook in hooks.py
- [x] Use list syntax for Purchase Receipt on_submit (existing + new handler)
- [x] Use list syntax for Material Request validate (existing + new handler)
- [x] Create project_component_master/__init__.py module package
- **File:** `hooks.py`

### Phase 5: Reports ⏳ (Pending)
- [ ] Create Component Procurement Status report
- [ ] Implement report Python logic
- [ ] Implement report JavaScript filters/formatters
- [ ] Test report with various filters

### Phase 6: Testing ⏳ (Pending)
- [ ] Write unit tests for Project Component Master
- [ ] Write integration tests for BOM Upload Enhanced
- [ ] Write tests for Material Request validation
- [ ] Run all tests and fix issues

### Phase 7: Documentation ⏳ (Pending)
- [ ] Create user guide for new workflow
- [ ] Document loose item workflow
- [ ] Document change resolution process
- [ ] Create video tutorials

---

**Document Version:** 1.5
**Date:** 2026-01-27
**Status:** Phases 1–4A Complete. Phase 4B (project_qty multiplication) pending — critical fix for bom_qty_required. Reports and testing pending.
**Estimated Effort:** 40-60 hours (est. 30-35 hours completed)
