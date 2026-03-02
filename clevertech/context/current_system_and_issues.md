## Current System & Limitations

### Existing BOM Upload Logic

**What it does:**
```python
1. Parse Excel file (specific column mapping from PE2 export)
2. Build hierarchical tree structure from "level" column
3. Create Item masters if they don't exist
4. Create BOMs recursively (bottom-up approach)
5. Skip if BOM exists (simple existence check)
```

**Critical Limitations:**

#### Limitation 1: Blind Skipping
```python
# Current logic
existing = frappe.db.exists("BOM", {
    "item": item_code,
    "is_active": 1,
    "is_default": 1
})

if existing:
    return False  # Skip, no questions asked
```

**Problem:** If Motor-Assembly BOM changed from 3 child items to 5 child items, system silently skips it. Procurement happens with outdated BOM.

#### Limitation 2: No Change Detection
- No comparison of BOM structure
- No alerting when components change
- No tracking of what changed (added/removed/qty modified)

#### Limitation 3: No Procurement Tracking
- Can't see which components have procurement initiated
- No prevention of duplicate procurement
- No visibility into "loose items" that later get added to BOMs

#### Limitation 4: No Version Management
- When BOM changes, old BOM just replaced
- No audit trail of versions
- Procurement documents may reference obsolete BOMs

#### Limitation 5: No Budget/Timeline Tracking
- No way to set target costs per component
- No target delivery dates
- No rolled-up cost estimates for assemblies

#### Limitation 6: Loose Item Gap
**Scenario:**
```
Day 1: Bearing (long lead time) → Procure 100 units as "loose item"
Day 30: Motor-Assembly BOM uploaded → Requires Bearing × 50 units
       → System creates new Material Request for 50 units
       → Result: 150 units procured (50 excess!)
```

No mechanism to track that Bearing was already procured outside BOM context.

### Known Issues & Root Cause Analysis

#### Issue 1: BOM Upload Excel Format Inconsistency (2026-02-01)

**Symptom:**
- BOM Upload creating BOMs for raw materials (e.g., BOM-A00000006515-001 created for an RM item)
- Incorrect parent-child hierarchies
- File: `/files/BomExport_V00000000015_00_lds4la.xlsx` failed

**Root Cause:**
The existing `bom_upload.py` (inherited code, not modified) uses **hardcoded column mappings** from the PE2 Excel export:

```python
# Line 541 in bom_upload.py - CRITICAL column
"level": int(ws[f"AR{r}"].value or 0),  # Column AR = hierarchy level
```

**Excel format has changed:**

| Column | Working File (sample_input) | Broken File (BomExport_V00) |
|--------|----------------------------|----------------------------|
| **AQ** | _(unknown)_ | ✅ **LivelloBom** (Level: 1, 2, 3) |
| **AR** | ✅ **LivelloBom** | ❌ **QtaTotale** (Total Qty) |

**Impact:**
- Code reads Column AR expecting BOM level (0, 1, 2, 3...)
- Gets `QtaTotale` (quantity values) instead
- `build_tree()` function creates **completely wrong hierarchy**:
  - Raw materials assigned children → BOMs created incorrectly
  - Assemblies treated as leaf items → No BOM created
  - Parent-child relationships broken

**All Hardcoded Column Mappings in bom_upload.py:**

| Column | Field | Purpose |
|--------|-------|---------|
| A | position | Item position |
| B | position (alt) | Fallback if A empty |
| C | item_code | **Primary identifier** |
| D | description | Item description |
| E | qty | Quantity |
| G | revision | Revision number |
| U | extended_description | DESCRIZIONE_ESTESA |
| AD | material | Material spec |
| AE | part_number | Part number |
| AF | weight | Weight |
| AG | manufacturer | Manufacturer |
| AL | treatment | Surface treatment |
| AN | uom | Unit of measure |
| **AR** | **level** | **Hierarchy level (CRITICAL!)** |

**Why Column AR is Critical:**
The `build_tree()` function (lines 550-567) uses level to determine parent-child relationships:

```python
def build_tree(rows):
    stack = []
    for row in rows:
        while stack and stack[-1]["level"] >= row["level"]:
            stack.pop()
        if stack:
            stack[-1]["children"].append(row)  # ← Wrong data = wrong tree!
```

**Solution Implemented:**
- Enhanced BOM Upload now **searches for headers dynamically** (not hardcoded columns)
- Validates all required columns exist before processing
- Displays clear errors if any required column is missing
- Handles both old and new Excel formats automatically
- See: `bom_upload_enhanced.py` - `parse_rows_dynamic()` function

**Validation Added:**
```python
Required columns:
- Item Code (C or search: "Item no")
- Level (AR or search: "LivelloBom" / "Level")
- Description, Qty, UOM, etc.

If ANY required column missing:
→ BLOCK upload
→ Display error: "Missing required column: [column_name]"
```

**Files Affected:**
- ✅ Working: `/private/files/sample_input_3964d9f.xlsx` (LivelloBom in AR)
- ❌ Broken: `/files/BomExport_V00000000015_00_lds4la.xlsx` (LivelloBom in AQ)
- ✅ Fixed: Enhanced upload handles both formats

**Resolution Status:** ✅ Fixed in Phase 4H (2026-02-01)

#### Issue 2: active_bom Not Updated When BOM Shared Across Projects (2026-02-04)

**Symptom:**
- User uploads BOM for project SMR260003
- Version change detected, user confirms
- Old BOM deactivated, new BOM (v5) created
- But Component Master still shows old BOM (v3) as `active_bom`

**Root Cause Analysis:**

The issue stems from how BOMs are shared across projects and how `active_bom` linking works.

**Business Requirement:**
- Same BOM should be shareable across multiple projects (no duplicates)
- Version change should only affect current project
- Other projects keep using their existing BOM

**Technical Flow (What Goes Wrong):**

```
1. BOM-D00000084229-005 exists with project=SMR260002
2. User uploads for project SMR260003 (same structure)
3. create_bom_recursive() checks if BOM exists:

   existing = frappe.db.exists("BOM", {
       "item": node["item_code"],
       "is_active": 1,
       "is_default": 1
       # ❌ NO PROJECT FILTER - finds BOM from SMR260002
   })

4. BOM found → returns False → NO NEW BOM CREATED
5. on_bom_submit hook NEVER FIRES for SMR260003
6. _link_boms_to_component_masters() runs but SKIPS CM because:

   filters={
       "active_bom": ("is", "not set")  # ❌ CM already has old active_bom
   }

7. CM for SMR260003 never gets updated with correct active_bom
```

**Why on_bom_submit Doesn't Help:**
- `on_bom_submit` uses `doc.project` to find Component Master
- If BOM has `project=SMR260002`, it only updates SMR260002's CM
- SMR260003's CM is never touched

**Locations Affected:**

| File | Function | Issue |
|------|----------|-------|
| `bom_upload.py:414-418` | `create_bom_recursive()` | BOM existence check has no project filter |
| `bom_upload_enhanced.py:1343-1348` | `_link_boms_to_component_masters()` | Skips CMs that already have `active_bom` set |
| `bom_hooks.py:112` | `on_bom_submit()` | Only updates CM for BOM's project |

**Solution:**

Fix `_link_boms_to_component_masters()` to:
1. Process ALL CMs with `has_bom=1` (remove "active_bom not set" filter)
2. Find the correct active+default BOM for the item (any project)
3. Update CM's `active_bom` if it differs from current value
4. Only skip if already pointing to correct BOM

**Code Change in `bom_upload_enhanced.py`:**

```python
# BEFORE (line 1343-1348):
cms = frappe.get_all(
    "Project Component Master",
    filters={
        "project": project,
        "has_bom": 1,
        "active_bom": ("is", "not set"),  # ❌ Skips CMs with existing active_bom
    },
    ...
)

# AFTER:
cms = frappe.get_all(
    "Project Component Master",
    filters={
        "project": project,
        "has_bom": 1,
        # ✅ Removed "active_bom not set" filter - process ALL CMs
    },
    ...
)

# Then for each CM, check if update needed:
for cm_data in cms:
    bom_name = find_active_bom_for_item(cm_data.item_code)  # Any project
    if bom_name and cm_data.active_bom != bom_name:
        # Update active_bom
```

**Design Decision: BOM Sharing Across Projects**

| Requirement | Answer | Current Status |
|-------------|--------|----------------|
| Should projects share the same BOM? | Yes | ✅ Implemented |
| Should version change affect all projects? | No (only current) | ⚠️ Currently global |
| Create duplicate BOMs? | No | ✅ Implemented |

**Current Behavior (2026-02-04, updated 2026-02-04):**
- BOMs are shared across projects (same BOM linked to multiple CMs)
- When version change confirmed, old BOM is **demoted** (`is_default=0`) — NOT deactivated
- Old BOM stays `is_active=1` — archived, still referenceable by parent BOMs and for traceability
- New BOM created with `is_active=1, is_default=1`, linked to Component Master via `on_bom_submit`

**Controlled Upward Propagation (Industry Best Practice):**
- Child BOM change does NOT automatically version parent BOMs
- Parent BOMs still reference old child via `bom_no` until engineer explicitly adopts
- System surfaces impacted parents (where-used) in confirmation dialog and post-creation result
- Engineer reviews impact per ECO best practice, adopts when ready
- This follows industry standard (SAP/Oracle/PLM): controlled revision, not auto-cascade

**Why demotion instead of deactivation:**
- Frappe blocks `is_active=0` on submitted BOMs that are referenced via `bom_no` in other submitted BOMs
- `is_default=0` is sufficient: `create_bom_recursive` checks `is_active=1 AND is_default=1` to skip existing
- Old BOM remains valid for parent references and version history audit trail
- `total_qty_limit` on Component Master is the hard procurement gate — duplicate BOMs do not cause duplicate procurement

**Fix Applied:**
- Modified `_link_boms_to_component_masters()` in `bom_upload_enhanced.py`
- Now processes ALL CMs with `has_bom=1` (removed "active_bom not set" filter)
- Includes current `active_bom` in query to compare before updating
- Only updates if `active_bom` differs from correct BOM

---

