# BOM Upload - Existing Code Study

## Document Purpose
This document analyzes the existing BOM Upload functionality to understand the current implementation before adding our enhanced "Create BOMs with Project Component Master" feature.

---

## Current Architecture

### File Structure
```
clevertech/doctype/bom_upload/
├── bom_upload.py          # Server-side logic
├── bom_upload.js          # Client-side button handler
└── bom_upload.json        # DocType definition
```

---

## DocType Structure

### BOM Upload (bom_upload.json)

**Fields:**
- `project` (Link → Project) - Required for associating BOM with project
- `bom_file` (Attach) - Excel file from PE2 export
- `create_boms` (Button) - Triggers BOM creation

**Permissions:**
- System Manager: Full access

**Current Limitations:**
- No fields to track upload status
- No fields to store analysis results
- No history of previous uploads

---

## Client-Side Logic (bom_upload.js)

### Button Click Handler

**Location:** [bom_upload.js:2-54](bom_upload.js#L2-L54)

**Flow:**
```javascript
1. Validate bom_file is attached
2. Call server method: create_boms(docname)
3. Show freeze message: "Creating BOMs..."
4. Display results:
   - BOMs Created: N
   - BOMs Skipped: N
   - Failed: N
   - Errors: [list]
5. Reload form
```

**Key Characteristics:**
- Simple validation (file exists)
- Synchronous operation (blocks UI)
- Basic success/error messaging
- No pre-upload analysis
- No change detection

---

## Server-Side Logic (bom_upload.py)

### Entry Point: `create_boms(docname)`

**Location:** [bom_upload.py:11-14](bom_upload.py#L11-L14)

```python
@frappe.whitelist()
def create_boms(docname):
    doc = frappe.get_doc("BOM Upload", docname)
    return _create_boms(doc)
```

**Purpose:** Whitelisted API endpoint, fetches document and delegates to internal function.

---

### Core Function: `_create_boms(doc)`

**Location:** [bom_upload.py:17-49](bom_upload.py#L17-L49)

**Flow:**
```python
1. Load Excel file from attached file_url
2. Parse workbook using openpyxl
3. Extract rows from worksheet
4. Build hierarchical tree
5. For each root node:
   - Create BOM recursively
   - Track created/skipped/failed counts
6. Return summary dict
```

**Return Structure:**
```python
{
    "created": int,
    "skipped": int,
    "failed": int,
    "errors": [string]
}
```

---

## Excel Parsing

### Helper Functions

#### `clean_code(code)` - [bom_upload.py:54-57](bom_upload.py#L54-L57)
```python
# Removes dots and strips whitespace from item codes
# PE2 export sometimes includes dots that ERPNext doesn't handle well
```

#### `to_float(val, default=0)` - [bom_upload.py:60-64](bom_upload.py#L60-L64)
```python
# Safe float conversion with default fallback
# Handles Excel cells with non-numeric content
```

#### `normalize_uom(uom)` - [bom_upload.py:67-71](bom_upload.py#L67-L71)
```python
# Maps Italian UOM names to ERPNext standards
# NUMERI → Nos, PEZZI → Nos, METRI → Meter
```

---

### Main Parser: `parse_rows(ws)`

**Location:** [bom_upload.py:76-104](bom_upload.py#L76-L104)

**Excel Column Mapping:**
| Column | Data | Notes |
|--------|------|-------|
| A | Position | Fallback to column B if A is empty |
| B | Position (alternate) | |
| C | Item Code (raw) | **Required** - row skipped if empty |
| D | Description | |
| E | Quantity | Defaults to 1 if invalid |
| G | Revision | |
| AC | Material | |
| AD | Part Number | |
| AE | Weight | Defaults to 0 if invalid |
| AF | Manufacturer | |
| AL | Treatment (Tipo Trattamento) | |
| AM | UOM | Normalized (NUMERI→Nos, etc.) |
| AR | Level | **Critical for hierarchy** |

**Start Row:** 3 (rows 1-2 assumed to be headers)

**Output Structure:**
```python
[
    {
        "position": str,
        "item_code": str,         # Cleaned (dots removed)
        "description": str,
        "qty": float,
        "revision": str,
        "material": str,
        "part_number": str,
        "weight": float,
        "manufacturer": str,
        "treatment": str,
        "uom": str,               # Normalized
        "level": int,             # Hierarchy depth
        "children": []            # Populated by build_tree
    },
    ...
]
```

---

## Hierarchy Building

### `build_tree(rows)`

**Location:** [bom_upload.py:109-126](bom_upload.py#L109-L126)

**Algorithm:** Stack-based tree construction

**Logic:**
```python
stack = []      # Current path in tree
roots = []      # Top-level components

For each row:
    1. Pop from stack while stack top level >= current level
       (moving back up the tree)

    2. If stack not empty:
          Add current row as child of stack top
       Else:
          Add current row as root

    3. Push current row onto stack
```

**Example:**
```
Input rows:
Level 0: Machine
Level 1: Motor
Level 2: Shaft
Level 2: Bearing
Level 1: Gearbox
Level 2: Gear

Output tree:
Machine
├── Motor
│   ├── Shaft
│   └── Bearing
└── Gearbox
    └── Gear
```

**Key Insight:** Uses implicit hierarchy from level numbers, not explicit parent references.

---

## Item Creation

### `ensure_item_exists(item_code, description, uom)`

**Location:** [bom_upload.py:131-150](bom_upload.py#L131-L150)

**Logic:**
```python
1. Check if Item exists (by item_code)
2. If not exists:
   - Create Item with:
     * item_code = item_code
     * item_name = description or item_code
     * item_group = "All Item Groups"
     * stock_uom = uom or "Nos"
     * is_stock_item = 1
     * is_purchase_item = 1
     * is_sales_item = 0
   - Insert with ignore_permissions=True
3. If exists: Do nothing
```

**Characteristics:**
- Idempotent (safe to call multiple times)
- No validation of existing item properties
- Doesn't update existing items
- Generic item group assignment

---

## BOM Creation

### `create_bom_recursive(node, project, root_level=None)`

**Location:** [bom_upload.py:154-220](bom_upload.py#L154-L220)

**Algorithm:** Bottom-up recursive BOM creation

**Flow:**
```python
1. Ensure item exists for current node

2. Recursively create BOMs for all children that have sub-assemblies
   (Children with their own children need their BOMs created first)

3. Check if BOM already exists:
   - Query: item = node['item_code'], is_active=1, is_default=1
   - If exists: Return False (skip)

4. Create BOM:
   - Item: node['item_code']
   - Quantity: 1 (always)
   - Project: project
   - is_active: 1
   - is_default: 1

5. Add children as BOM Items:
   - Ensure each child item exists
   - Create BOM Item with:
     * item_code, qty, uom
     * custom_position, custom_revision_no
     * custom_material, custom_part_number
     * custom_weight, custom_manufacturer
     * custom_tipo_trattamento
     * custom_level_of_bom: 1 (always)
   - If child has BOM: Set bom_no reference

6. Insert and Submit BOM

7. Return True (created) or False (skipped)
```

**Key Points:**

#### Bottom-Up Creation
```
Create order for: Machine → Motor → Shaft
1. Create Shaft (no children)
2. Create Motor (references Shaft BOM)
3. Create Machine (references Motor BOM)
```

#### BOM Linking
```python
if child["children"]:  # Child is sub-assembly
    child_bom = get active/default BOM for child
    bom_item["bom_no"] = child_bom  # Link to child's BOM
```

#### Custom Fields
All PE2 metadata stored in custom BOM Item fields:
- Position, Revision, Material
- Part Number, Weight, Manufacturer
- Treatment (Tipo Trattamento)

#### Existing BOM Check
```python
# SIMPLE EXISTENCE CHECK - NO CONTENT COMPARISON
existing = frappe.db.exists("BOM", {
    "item": node["item_code"],
    "is_active": 1,
    "is_default": 1
})
if existing:
    return False  # Skip silently
```

**Critical Limitation:** No detection of BOM structure changes!

---

## Current Behavior Summary

### What Works Well
1. ✓ **Robust Excel Parsing**
   - Handles Italian PE2 export format
   - Flexible position field (A or B)
   - Safe type conversions
   - UOM normalization

2. ✓ **Correct Hierarchy Building**
   - Stack-based algorithm efficient and correct
   - Handles arbitrary depth
   - Preserves level information

3. ✓ **Bottom-Up BOM Creation**
   - Child BOMs created before parents
   - Proper BOM linking (bom_no references)
   - Preserves PE2 metadata in custom fields

4. ✓ **Idempotent Operations**
   - Safe to re-run (skips existing)
   - Doesn't break existing data

### What's Missing

#### 1. Change Detection
```python
# Current: Only checks existence
existing = frappe.db.exists("BOM", {...})

# Needed: Compare BOM structure
old_structure = get_bom_items(existing_bom)
new_structure = node['children']
if old_structure != new_structure:
    alert_user_of_changes()
```

#### 2. Procurement Tracking
- No visibility into which components procured
- No prevention of duplicate procurement
- No loose item integration

#### 3. Version Management
- Old BOM silently skipped (no version created)
- No audit trail of changes
- No way to track "why was this skipped?"

#### 4. Budget/Timeline
- No cost estimates
- No target delivery dates
- No variance tracking

#### 5. Dependency Analysis
- Doesn't find which BOMs affected by changes
- Can't block dependent BOMs
- No impact analysis

#### 6. Pre-Upload Validation
- No analysis before creating BOMs
- Can't preview changes
- All-or-nothing operation

---

## Reusable Components for Enhancement

### Can Reuse As-Is ✓

1. **Excel Parsing Logic**
   ```python
   parse_rows(ws)       # Columns, types, cleaning
   clean_code()
   to_float()
   normalize_uom()
   ```

2. **Tree Building**
   ```python
   build_tree(rows)     # Stack-based hierarchy
   ```

3. **Item Creation**
   ```python
   ensure_item_exists() # Idempotent item creation
   ```

4. **BOM Creation Core**
   ```python
   create_bom_recursive()  # Can wrap with validation
   ```

### Need to Wrap/Enhance 🔧

1. **BOM Existence Check**
   ```python
   # Current: Simple existence
   # Enhanced: Check + compare structure
   existing = check_bom_exists_and_compare(node, project)
   ```

2. **Upload Entry Point**
   ```python
   # Current: _create_boms() - direct creation
   # Enhanced: analyze_and_create_boms() - validation first
   ```

### Need to Add ➕

1. **Analysis Layer**
   ```python
   analyze_upload(tree, project)
   # Returns: new, unchanged, changed, blocked
   ```

2. **Change Detection**
   ```python
   calculate_bom_structure_hash(children)
   compare_bom_structures(existing, new)
   ```

3. **Dependency Tracking**
   ```python
   find_ancestors(graph, item_code)
   build_dependency_graph(tree)
   ```

4. **Component Master Integration**
   ```python
   create_or_update_component_master(node, project)
   validate_loose_item_conversion(item_code, project)
   ```

---

## Integration Points for New Button

### Option 1: Parallel Function (Recommended)

**Add new button:** "Create with Validation"

```python
# New function
@frappe.whitelist()
def create_boms_with_validation(docname):
    doc = frappe.get_doc("BOM Upload", docname)

    # Step 1: Use existing parsing
    file_doc = frappe.get_doc("File", {"file_url": doc.bom_file})
    content = file_doc.get_content()
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = wb.active

    rows = parse_rows(ws)        # ✓ Reuse
    tree = build_tree(rows)       # ✓ Reuse

    # Step 2: NEW - Analysis layer
    analysis = analyze_upload(tree, doc.project)

    # Step 3: NEW - Validation
    if analysis['requires_resolution']:
        return analysis  # Return to client for dialog

    # Step 4: NEW - Create Component Masters
    for node in analysis['can_create']:
        create_or_update_component_master(node, doc.project)

    # Step 5: Use existing BOM creation
    results = {"created": 0, "skipped": 0, "failed": 0, "errors": []}
    for node in analysis['can_create']:
        try:
            created_flag = create_bom_recursive(node, doc.project)  # ✓ Reuse
            # ... track results
        except Exception as e:
            # ... handle errors

    return results

# Keep existing function unchanged
@frappe.whitelist()
def create_boms(docname):
    # Original logic stays exactly as-is
    ...
```

**Benefits:**
- Zero risk to existing functionality
- Easy A/B testing
- Gradual migration path
- Can remove old button later

---

## Custom Fields Identified

### Existing Custom Fields on BOM Item
These are already in use and populated by current code:

```python
bom_item = {
    "custom_position": child["position"],          # From Excel column A/B
    "custom_revision_no": child["revision"],       # From Excel column G
    "custom_material": child["material"],          # From Excel column AC
    "custom_part_number": child["part_number"],    # From Excel column AD
    "custom_weight": child["weight"],              # From Excel column AE
    "custom_manufacturer": child["manufacturer"],  # From Excel column AF
    "custom_tipo_trattamento": child["treatment"], # From Excel column AL
    "custom_level_of_bom": 1                       # Always 1 (direct child)
}
```

**Note:** Our enhancement should preserve these fields when creating BOMs.

---

## Error Handling

### Current Approach
```python
try:
    created_flag = create_bom_recursive(node, doc.project)
    if created_flag:
        created += 1
    else:
        skipped += 1
except Exception as e:
    failed += 1
    errors.append(f"{node['item_code']} → {str(e)}")
```

**Characteristics:**
- Per-component error isolation
- Doesn't fail entire upload if one component fails
- Collects all errors for reporting

**Enhancement Needed:**
- Distinguish error types (validation vs system error)
- Provide actionable error messages
- Track which specific validation failed

---

## Performance Considerations

### Current Implementation
- **Single-threaded:** Processes components sequentially
- **Recursive:** Deep call stack for nested BOMs
- **Database per component:** Multiple queries per BOM

### Typical Load
- 500 components per project
- 4-6 levels deep
- ~10-20 root assemblies

### Performance Bottlenecks
1. BOM existence checks (N queries)
2. Item existence checks (N queries)
3. BOM submission (triggers standard validations)

### Optimization Opportunities
1. Batch item existence checks
2. Cache BOM lookups
3. Defer commit until end (transactions)

**For Enhancement:** Consider batch operations for Component Master creation.

---

## Testing Coverage Gaps

### Current Testing
Based on code, appears to have minimal test coverage:
- [test_bom_upload.py](test_bom_upload.py) exists but likely empty

### What Should Be Tested
1. **Excel Parsing**
   - Various column formats
   - Missing data handling
   - Type conversions
   - UOM normalization

2. **Tree Building**
   - Various hierarchy depths
   - Level number gaps (e.g., 0 → 2 skip 1)
   - Single item (no children)

3. **BOM Creation**
   - New items
   - Existing items
   - Existing BOMs (skip behavior)
   - BOM linking (sub-assemblies)

4. **Error Cases**
   - Invalid Excel format
   - Missing project
   - Duplicate item codes at same level
   - Circular references (A→B→A)

---

## Summary: Enhancement Strategy

### Keep Unchanged ✓
- Excel parsing logic (columns, types, cleaning)
- Tree building algorithm
- Item creation function
- BOM creation core logic
- Error handling pattern

### Wrap with Validation 🔧
- BOM existence check → Add structure comparison
- Upload flow → Add analysis phase

### Add New 🆕
- Project Component Master creation
- Change detection logic
- Dependency analysis
- Loose item validation
- Material Request quantity control

### New Button Flow
```
User clicks "Create with Validation"
    ↓
1. Parse Excel (reuse parse_rows, build_tree)
    ↓
2. Analyze upload (NEW)
   - Compare with existing Component Masters
   - Detect changes (hash comparison)
   - Find dependencies
   - Check loose item status
    ↓
3. If issues found → Return analysis (show dialog)
   If clear → Proceed to step 4
    ↓
4. Create Component Masters (NEW)
    ↓
5. Create BOMs (reuse create_bom_recursive)
    ↓
6. Update Component Masters with BOM references (NEW)
    ↓
7. Return detailed results
```

---

## Next Steps

1. ✅ **Code Study Complete** (this document)
2. 🔲 **Tech Specs:** Define new functions and DocTypes
3. 🔲 **Implementation:** Add new button and logic
4. 🔲 **Testing:** Write comprehensive tests
5. 🔲 **Documentation:** User guide for new workflow

---

**Document Version:** 1.0
**Date:** 2026-01-26
**Status:** Complete - Ready for Tech Specs
