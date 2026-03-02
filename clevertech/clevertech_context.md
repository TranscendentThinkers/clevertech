# Engineer to order+PLM Component Master - Architecture Context

## Document Purpose
This document explains the business context, architectural decisions, and design rationale for the **Project Component Master** system in Clevertech's ERP implementation. It serves as a reference for understanding WHY specific design choices were made.

---

## Related Documents

This is part of a complete documentation suite for the Project Component Master system:

1. **[clevertech_context.md](../clevertech_context.md)** (This Document)
   - Business context and workflow
   - Architectural decisions and rationale
   - Design evolution and trade-offs
   - **Read this first** to understand the "WHY"

2. **[docs/bom_upload_code_study.md](docs/bom_upload_code_study.md)**
   - Analysis of existing BOM Upload code
   - What can be reused vs. what needs enhancement
   - Integration points for new functionality
   - **Read this second** to understand current implementation

3. **[docs/project_component_master_tech_specs.md](docs/project_component_master_tech_specs.md)**
   - Complete DocType JSON definitions
   - All function specifications with signatures
   - Test cases and validation logic
   - Implementation checklist
   - **Use this for implementation** - contains all technical details

4. **[docs/bom_upload_enhanced_flow.md](docs/bom_upload_enhanced_flow.md)**
   - Detailed technical flowcharts for `bom_upload_enhanced.py`
   - Testing flowcharts (QA reference without implementation details)
   - Function reference with line numbers
   - Test data checklist and expected results
   - **Use this for testing** - contains complete test scenarios

**Recommended Reading Order:**
- **Manager/Stakeholder:** Read Context doc only
- **Developer:** Read all three in order (Context → Code Study → Tech Specs → Enhanced Flow)
- **QA/Tester:** Focus on Context doc + Test Cases in Tech Specs + **Part 2 of Enhanced Flow**

---

## Table of Contents
1. [Business Context](#business-context)
2. [Current System & Limitations](#current-system--limitations)
3. [Core Requirements](#core-requirements)
4. [Architectural Decisions](#architectural-decisions)
5. [Design Evolution](#design-evolution)
6. [Final Architecture](#final-architecture)

---

## Business Context

### Company Profile
**Clevertech** is an engineer-to-order (ETO) manufacturer of packaging machines. Their business model is characterized by:
- Custom machine design per customer order
- Long lead times for component procurement
- Complex multi-level Bill of Materials (BOM)
- Continuous design evolution during project execution

### Current Workflow

#### 1. Design Phase
- Machines are designed in **SolidWorks** (3D CAD)
- Bill of Materials (BOM) is maintained in **PE2** (PLM system)
- A typical machine has **~500 components** across multiple levels
- Not all components are designed upfront

#### 2. Phased Design Release
**Day 1:**
- Only 2-3 components finalized
- These components may have 4-level deep BOMs
- Procurement must start immediately due to long lead times

**Day 30:**
- 3 more components released
- Some existing components may have design revisions
- Procurement for initial components already in progress

**Day 60+:**
- Continuous component additions and revisions
- Some components procured as "loose items" before design finalized

#### 3. Current ERPNext Integration
**Process:**
1. Export BOM from PE2 to Excel
2. Upload Excel to ERPNext via "BOM Upload" doctype
3. System creates Item masters and BOM structures
4. Material Requests (MR) raised from BOMs
5. Standard procurement workflow: MR → RFQ → Supplier Quotation → Purchase Order

**Problem:** This works for initial upload but breaks down on subsequent uploads when components change.

---

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

## Core Requirements

### Requirement 1: Incremental BOM Updates
**Need:** Upload full BOM export monthly/weekly, but only create NEW components, skip unchanged, and ALERT on changes.

**Business Driver:** Design evolves continuously. Can't manually track 500 components across 20 projects.

### Requirement 2: Change Detection with Impact Analysis
**Need:** When Motor-Gearbox BOM changes, system must:
- Detect the change (compare structure)
- Find all parent assemblies using Motor-Gearbox
- Block creation of entire chain until resolved
- Show user what changed (qty, new items, removed items)

**Business Driver:** Cost rollups and procurement tracking break if parent BOMs created with wrong child structure.

### Requirement 3: Loose Item Management
**Need:** Track components procured before design finalized:
- Allow procurement without BOM
- When component added to BOM later, prevent duplicate procurement
- Track quantity limits: `MAX(loose_qty, bom_qty)` not `SUM`

**Business Driver:** Long lead items (6+ months) must be ordered before design complete. Common in custom machinery.

### Requirement 4: Version Control
**Need:** When Motor-Assembly BOM changes:
- Create new version (not replace)
- Keep old version for existing POs
- Track procurement per version
- Allow parallel procurement (v1 and v2 simultaneously)

**Business Driver:** May have orders for old version in production while new version being quoted.

### Requirement 5: Budget & Timeline Tracking
**Need:**
- Set target cost per component (designer estimate)
- Auto-calculate rolled-up cost from child components
- Allow manual override (for assembly labor, overhead)
- Track actual procurement cost vs budget

**Business Driver:** Custom machines quoted based on component cost estimates. Need variance tracking.

### Requirement 6: Procurement Quantity Control
**Need:** Hard limit on Material Request quantities:
```
If Bearing: loose_qty=100, bom_qty=150
Then: total_limit = MAX(100, 150) = 150
Block any MR that would cause total procurement > 150
```

**Business Driver:** Prevent over-procurement. Inventory carrying costs are high for custom components.

### Requirement 7: Comprehensive Reporting
**Need:** Report showing per project:
- All components (assemblies + loose items)
- BOM hierarchy (levels)
- Budget vs actual
- Procurement status (Not Started / In Progress / Complete)
- Linked documents (MR, RFQ, PO)

**Business Driver:** Management needs project-level procurement visibility for cash flow planning.

---

## Architectural Decisions

### Decision 1: Introduce "Project Component Master" DocType

**Problem:** ERPNext's native Item and BOM doctypes are project-agnostic. Can't track project-specific:
- Procurement status per project
- Budget per project (same bearing may have different target cost in different projects)
- Loose item tracking per project

**Solution:** New master doctype bridging Project ↔ Item ↔ BOM

**Why not use existing doctypes?**

| Option | Why Rejected |
|--------|--------------|
| **Custom fields on Item** | Items are global; same item used across projects with different budgets/status |
| **Custom fields on BOM** | BOMs are global; same BOM may be used in multiple projects |
| **Project doctype child table** | Can't handle deep hierarchy; poor query performance; limited customization |
| **New DocType** | ✓ Project-specific context, ✓ Rich data model, ✓ Separate permissions |

**Trade-off Accepted:** Additional complexity of maintaining Component Master, but gains flexibility and clarity.

---

### Decision 2: Component Master Scope - "ALL Items in BOM Tree"

> **⚠️ EVOLVED:** Original design (v1.0-v1.7) was "Assemblies + Loose Items only". Changed in v1.9 to include ALL items after realizing raw materials need procurement validation and reporting rollup.

**Evolution of this Decision:**

**v1.0–v1.7: Assemblies + Loose Items Only**
- Only items with BOMs or marked as loose got Component Masters
- Raw materials (leaf items) were NOT tracked
- **Problem discovered:** MR/PO validation couldn't enforce limits on raw materials because they had no Component Master record!
- **Problem discovered:** Management report needed rollup from any level (M → G → D → RM), requiring all levels to exist

**v1.9: ALL Items in BOM Tree (CURRENT DESIGN)**
```
Project Component Master contains:
✓ Root assemblies (M level) — has_bom=1, make_or_buy=Make
✓ Sub-assemblies (G level) — has_bom=1, make_or_buy=Make
✓ Sub-assemblies (D level) — has_bom=1, make_or_buy=Make OR Buy
✓ Raw materials (RM level) — has_bom=0, make_or_buy=Buy
✓ Loose raw materials — is_loose_item=1
```

**Why ALL items now:**
1. **Procurement validation:** MR/PO for raw materials needs Component Master to check limits
2. **Report rollup:** Management views at M/G level require all children to exist for aggregation
3. **Calculation chain:** `project_qty` propagates from root → children; every level needs a record
4. **Make/Buy control:** Parent's make/buy flag determines if children need separate procurement
5. **Consistent data model:** Every item in the project has one tracking record

**Trade-off Accepted:**
- More records (~200-500 per project instead of ~50-100)
- ERPNext handles this scale well
- Benefits of complete visibility outweigh storage cost

---

### Decision 3: Hierarchical Structure (Parent-Child)

**Options Considered:**

**Option A: Flat List**
```
Component Master:
- Motor-Assembly (no parent link)
- Gearbox-Sub (no parent link)
- Shaft-001 (no parent link)
```

**Option B: Hierarchical**
```
Component Master:
- Motor-Assembly (parent=null, level=0)
- Gearbox-Sub (parent=Motor-Assembly, level=1)
- Custom-Bracket (parent=Gearbox-Sub, level=2)
```

**Chosen: Option B (Hierarchical)**

**Rationale:**
1. **Cost Rollup:** Need to calculate Motor-Assembly cost = Gearbox cost + Housing cost + ...
2. **Dependency Tracking:** If Gearbox changes, must know Motor-Assembly affected
3. **Reporting:** Show "which assemblies are blocked by Gearbox delay?"
4. **Business Context:** PE2 export has hierarchy (level column), natural to preserve it

**Implementation Detail:**
- Hierarchy implicit in PE2 export (level 0, 1, 2...)
- BOM Upload derives parent-child during tree building
- Auto-populates `parent_component` and `bom_level` fields

---

### Decision 3A: BOM Versioning and Change Propagation

**CRITICAL UNDERSTANDING: BOMs are Version-Locked**

**How ERPNext BOMs Work:**
```
Parent BOMs reference children by ITEM CODE with VERSION FROZEN at submission:

BOM-A-001 (submitted):
  Items:
    - Item: B (qty: 1)  → Uses BOM-B-001 (frozen)

BOM-C-001 (submitted):
  Items:
    - Item: B (qty: 3)  → Uses BOM-B-001 (frozen)
```

**When Child BOM Changes:**

**Scenario:** Design team updates item B's structure in SolidWorks → PE2 → New Excel export

**What Happens:**
1. New Excel file contains:
   - Updated BOM for item B
   - BOM for item A (which uses B)
   - BOM for item C (which uses B)

2. BOM Upload creates NEW versions:
   - BOM-B-002 (new structure for B)
   - BOM-A-002 (uses BOM-B-002)
   - BOM-C-002 (uses BOM-B-002)

3. Old versions become inactive:
   - BOM-A-001 still exists but inactive
   - BOM-B-001 still exists but inactive
   - BOM-C-001 still exists but inactive

**Key Insight:**
- Parent BOMs **DO NOT** automatically use new child BOM versions
- BOMs are **IMMUTABLE** after submission — `bom_no` on BOM Item rows cannot be updated
- Child change is **demoted** (not deactivated) — old BOM stays `is_active=1` for parent references
- Parent adoption is **controlled** — engineer reviews impacted parents and adopts explicitly (ECO best practice)
- System surfaces impacted parents via `_get_impacted_parent_boms()` (where-used query on `bom_no`)
- PE2 exports the ENTIRE hierarchy so all levels are available for adoption when needed

**Impact on Component Master:**

```
Before BOM Upload (Old State):
Component Master for B:
├── active_bom = BOM-B-001
├── BOM Usage Table:
    ├── parent_bom = BOM-A-001
    └── parent_bom = BOM-C-001

After BOM Upload (New State):
Component Master for B:
├── active_bom = BOM-B-002  ← UPDATED
├── BOM Usage Table:
    ├── parent_bom = BOM-A-002  ← UPDATED (old row removed, new row added)
    └── parent_bom = BOM-C-002  ← UPDATED (old row removed, new row added)
```

**Blocking Logic:**
```
When BOM Upload attempts to create BOM-B-002:

1. Check: Does Component Master for B exist? → YES
2. Check: Does B have active procurement? → Check procurement_records table
3. If YES (procurement exists):
   - BLOCK entire BOM Upload
   - Prevents creation of BOM-A-002, BOM-B-002, BOM-C-002
   - Show user: "Item B has procurement. Cannot change. Affects BOM-A-001, BOM-C-001"
   - User must resolve/cancel procurement before uploading new file

4. If NO (no procurement):
   - Allow BOM Upload
   - Create BOM-A-002, BOM-B-002, BOM-C-002
   - Deactivate BOM-A-001, BOM-B-001, BOM-C-001
   - Update Component Master BOM Usage tables
```

**Why This Matters:**
1. **Procurement Control:** A single procured item blocks entire hierarchy update
2. **Change Traceability:** BOM versions track exact configuration at point in time
3. **Surgical Blocking:** Only affected items with procurement block upload
4. **Unaffected Siblings:** If item D (not in hierarchy) has procurement, it doesn't block A/B/C changes

**Rationale:**
- ERPNext's BOM immutability prevents mid-procurement confusion
- PE2's full hierarchy export ensures all parent references update together
- Component Master tracks current active versions + parent-child relationships
- Blocking logic prevents breaking existing procurement commitments

---

### Decision 4: Loose Item Conversion Logic

**Key Insight:** Loose items are **always raw materials**, never become assemblies with BOMs.

**Status States (Based on Actual BOM Usage):**
```
State 1: Pending Conversion
- is_loose_item = Yes
- has_bom = No
- bom_conversion_status = Pending Conversion
- bom_usage table is empty (not used in any BOM yet)

State 2: Converted to BOM
- is_loose_item = Yes (preserves history)
- has_bom = No (still a raw material)
- bom_conversion_status = Converted to BOM
- bom_usage table has 1 entry (used in exactly one BOM)

State 3: Partial (Used in Multiple BOMs)
- is_loose_item = Yes
- has_bom = No
- bom_conversion_status = Partial
- bom_usage table has 2+ entries (used in multiple BOMs)
```

**Important:** Status is determined by **actual BOM usage**, not by the checkbox.

**Permission Gate (Separate from Status):**
```
can_be_converted_to_bom (checkbox):
- Default: No (unchecked)
- Purpose: Permission gate to control BOM Upload
- Does NOT change status
- If No: BOM Upload BLOCKED (hard error)
- If Yes: BOM Upload ALLOWED (status updates when actually used)
```

**Blocking Logic:**
```python
if is_loose_item and not can_be_converted_to_bom:
    # HARD BLOCK - cannot use in any BOM
    raise Exception("Enable conversion first")
```

**Why keep `is_loose_item=Yes` even after conversion?**
- Preserves procurement history
- Loose vs BOM procurement tracked separately
- Helps explain why total_qty_limit might be higher than BOM requirement

**Rationale:** Designer must explicitly confirm "design finalized, OK to use in production BOM" by checking the box, but status only changes when item is actually added to a BOM.

---

### Decision 5: Procurement Quantity Control - MAX not SUM

**Critical Business Logic:**

**Scenario:**
```
Bearing-SKF-001:
- Day 1: Loose procurement = 100 units (long lead time)
- Day 30: Motor-Assembly BOM = 50 units
- Day 45: Pump-Assembly BOM = 30 units
- Total BOM requirement: 80 units
```

**Question:** What's the procurement limit?

**Wrong Answer: SUM**
```
Total limit = 100 (loose) + 80 (BOM) = 180
Problem: Bearing procured twice! 100 loose + 80 from BOM = 180 units
But only need MAX(100, 80) = 100 units
```

**Correct Answer: MAX**
```
Total limit = MAX(100, 80) = 100 units
Rationale:
- If loose=100 and BOM=80: Loose already covers BOM, no additional procurement
- If loose=100 and BOM=150: Need 150 total, loose covers 100, procure 50 more
```

**Implementation:**
```python
total_qty_limit = MAX(loose_qty_required, bom_qty_required)

# Material Request Validation
if total_procurement_attempt > total_qty_limit:
    raise Exception("Exceeds limit")
```

**Edge Case Handling:**
```
If loose=200, BOM=100:
- total_limit = MAX(200, 100) = 200 ✓
- But BOM MR should be 0 (already over-procured!)
- System shows: "Warning: Loose procurement (200) exceeds BOM (100)"
- Allows MR up to 200 total, not 200 + 100
```

---

### Decision 6: Change Detection - Hash-Based Comparison

**Problem:** How to detect if BOM structure changed?

**Options Considered:**

**Option A: Field-by-Field Comparison**
```python
for each child:
    compare item_code, qty, uom, custom_fields...
```
Rejected: Slow, complex, miss changes if new field added

**Option B: BOM Version Number**
```python
if old_bom.version != new_bom.version:
    changed = True
```
Rejected: PE2 doesn't export version cleanly, prone to false positives

**Option C: Structure Hash (CHOSEN)**
```python
structure = sorted([(item_code, qty) for child in children])
hash = md5(str(structure))
```

**Rationale:**
- Fast comparison (single string match)
- Captures structural changes (items added/removed/qty changed)
- Ignores non-structural changes (descriptions, custom fields)
- Same approach used by existing duplicate detection validation

**What triggers "changed"?**
- ✓ Child item added
- ✓ Child item removed
- ✓ Child item quantity changed
- ✗ Child item description changed (not structural)
- ✗ Custom fields changed (position, revision, material)

**Trade-off:** May miss "soft" changes (revision updated but BOM structure same). Acceptable because revision tracked separately in BOM Item custom fields.

---

### Decision 7: Change Blocking Strategy - Ancestor Chain

**Problem:** When Gearbox BOM changes, what should be blocked?

**Options Considered:**

**Option A: Block Entire Upload (All or Nothing)**
```
If ANY component changed → Block ALL components
```
Rejected: Unnecessarily delays 98 components because 2 changed

**Option B: Block Only Changed Component**
```
Block: Gearbox
Allow: Motor-Assembly (uses Gearbox)
```
Rejected: Creates Motor-Assembly BOM with wrong Gearbox structure

**Option C: Block Ancestor Chain (CHOSEN)**
```
If Gearbox changed:
- Block Gearbox ✓
- Block Motor-Assembly (uses Gearbox) ✓
- Block Main-Machine (uses Motor-Assembly) ✓
- Allow Pump-Assembly (doesn't use Gearbox) ✓
```

**Algorithm:**
```python
1. Identify changed components
2. For each changed component:
   - Find all ancestors (components containing it, recursively)
   - Add ancestors to blocked set
3. Allow creation of components NOT in blocked set
```

**Why this approach?**
- **Surgical:** Only blocks what's affected
- **Safe:** Preserves BOM integrity (no partial structures)
- **Efficient:** Allows parallel work on unrelated components

**Multi-Level Example:**
```
Upload contains:
- Machine
  ├── Module-A
  │   └── Assembly-X (unchanged)
  └── Module-B
      └── Gearbox (CHANGED)

Result:
✓ Allow: Assembly-X (no dependency on Gearbox)
✗ Block: Gearbox (changed itself)
✗ Block: Module-B (contains Gearbox)
✗ Block: Machine (contains Module-B which contains Gearbox)
```

---

### Decision 8: Budget Tracking - No Child Table

**Problem:** Need to track budget at component level AND leaf item level for cost rollup.

**Options Considered:**

**Option A: Budget Child Table in Component Master**
```
Project Component Master: Motor-Assembly
├── budgeted_rate: $500 (parent level)
└── Child Table: Item Budgets
    ├── Shaft: $100
    ├── Bearing: $50
    └── Housing: $200
```

**Rejected because:**
- Duplication: BOM already has item list
- Sync issues: If BOM changes, budget table out of sync
- Maintenance burden: Manual entry for every child item
- Complexity: What if child item also has BOM? Recursive budgets?

**Option B: Budget in BOM Item (ERPNext child table)**
```
BOM: Motor-Assembly
└── BOM Items:
    ├── Shaft, qty=1, custom_budgeted_rate=$100
    ├── Bearing, qty=2, custom_budgeted_rate=$50
```

**Rejected because:**
- Budget lives in BOM, not Component Master
- If multiple BOM versions, which budget applies?
- Hard to report "all component budgets" without querying BOMs

**Option C: Budget Only for Managed Components (CHOSEN)**
```
Project Component Master:
├── Motor-Assembly: budgeted_rate=$500 (manual entry)
├── Gearbox-Sub: budgeted_rate=$300 (manual entry)
└── Custom-Bracket: budgeted_rate=$150 (loose item)

Rollup Logic:
Motor-Assembly cost =
  Gearbox-Sub budget ($300 from Component Master) +
  Bearing actual ($120 from last PO) +
  Bolts actual ($8 from last PO)
```

**Rationale:**
- Budgets only for "managed components" (assemblies + loose items)
- Leaf catalog items (bolts, bearings) use actual procurement cost
- Designer estimates at assembly level, not bolt level
- Rollup combines budgets (for managed) + actuals (for catalog items)

**Business Context:**
- ETO quoting done at assembly level ("Motor section: $5000")
- Not at leaf level ("M6 bolt: $0.05")
- This matches how designers think about costs

---

### Decision 9: Material Request Validation - Hard Block

**Problem:** How to enforce procurement quantity limits?

**Options Considered:**

**Option A: Warning Only**
```python
if mr_qty > limit:
    frappe.msgprint("Warning: Exceeds limit")
    # But allow save
```
Rejected: Users ignore warnings, over-procurement happens

**Option B: Auto-Adjust**
```python
if mr_qty > limit:
    mr_qty = max_allowed
    frappe.msgprint("Adjusted to maximum")
```
Rejected: Silent changes confusing, may hide data entry errors

**Option C: Hard Block (CHOSEN)**
```python
if mr_qty > limit:
    frappe.throw("Cannot exceed limit")
    # Save fails
```

**Rationale:**
- Over-procurement is costly (inventory carrying, obsolescence)
- Better to force user decision than allow mistake
- User can increase limit in Component Master if genuinely needed
- Clear error message explains why and what limit is

**UX Consideration:**
Error message shows:
```
Cannot add 200 units of Bearing-SKF to Material Request

Procurement Limit Exceeded:
• Total Limit: 150 (from Component Master)
• Existing MRs: 100
• This MR: 200
• Total: 300

Maximum allowed for this MR: 50
```

Gives user actionable information to fix.

---

### Decision 10: BOM Versioning - Use ERPNext Native

**Decision:** Don't build custom versioning, use ERPNext's native BOM versioning.

**Rationale:**
- ERPNext already supports multiple BOMs per item
- Activate/deactivate mechanism exists
- Reports and queries understand BOM status
- Less code to maintain

**Component Master Role:**
- Tracks `active_bom` (current version)
- Child table tracks BOM version history
- Provides project-specific version context

**When BOM changes:**
```
Old approach (custom): BOM-MOT-001-V1, BOM-MOT-001-V2
New approach (native): BOM-MOT-001, BOM-MOT-002 (ERPNext auto-naming)

Component Master:
- active_bom = BOM-MOT-002
- BOM Version History:
  - BOM-MOT-001 (v1, created 2026-01-01, procurement: PO-001)
  - BOM-MOT-002 (v2, created 2026-02-15, procurement: PO-045)
```

**User Workflow:**
1. Upload detects change → Show dialog
2. User manually creates new BOM (or lets system create with new name)
3. User deactivates old BOM
4. System updates Component Master.active_bom

---

### Decision 11: Two Distinct Flows for Component Master Creation

**CRITICAL: Component Masters are created differently depending on the scenario.**

**Flow 1: Cutover (Existing Projects)**
```
Projects where BOMs already exist in ERPNext (e.g., SMR260001 with 24 BOMs).

Sequence:
1. BOMs already exist (submitted, active, default)
2. User clicks "Generate Component Masters" on Project form
3. System creates Component Masters FROM existing BOMs
4. Sets: has_bom=1, active_bom=BOM-xxx, bom_structure_hash, design_status="Design Released"
5. Populates BOM Usage tables retroactively

Direction: BOM → Component Master (retrospective)
Implementation: Phase 2A — bulk_generation.py + project.js
```

**Flow 2: New Projects (Ongoing PE2 Uploads)**
```
New project, first PE2 export uploaded to BOM Upload doctype.

Sequence:
1. Parse PE2 Excel → build tree of assemblies
2. Create Component Masters FIRST (has_bom=1, active_bom=null)
3. Run analysis — check procurement blocks, loose items, changes
4. Create BOMs bottom-up (existing BOM Upload logic)
5. Link back — set active_bom and bom_structure_hash on Component Masters
6. BOM on_submit hooks fire → populate BOM Usage tables automatically

Direction: Component Master → BOM (proactive)
Implementation: Phase 3 — enhanced BOM Upload
```

**Why Component Masters BEFORE BOMs in Flow 2:**
- **Blocking logic needs them:** During BOM creation, the system checks if a component has active procurement or is a loose item without conversion enabled. These checks require the Component Master to already exist.
- **Analysis requires them:** The analyze_upload() function queries Component Masters to categorize items as new/unchanged/changed/blocked.
- **active_bom is set later:** Component Master is created with active_bom=null, then updated after BOM is successfully created and submitted.

**Why BOMs BEFORE Component Masters in Flow 1:**
- **No analysis needed:** Cutover data is already clean — BOMs are submitted and active.
- **No blocking possible:** No procurement exists yet for these items.
- **Simpler:** Just read existing BOMs and create tracking records.

**Incremental Upload (Day 30, Day 60...):**
```
Subsequent PE2 uploads for an existing project follow Flow 2:

1. Parse Excel → build tree
2. Some items already have Component Masters (from previous upload)
3. New items: Create Component Masters first, then BOMs
4. Unchanged items: Skip (hash comparison)
5. Changed items: Block ancestor chain, require resolution
6. BOM hooks update existing Component Masters automatically
```

**Rationale:**
- Cutover is a one-time operation, simplicity wins
- Ongoing uploads need full validation pipeline, safety wins
- Both flows produce the same end state: Component Master with active_bom linked

---

### Decision 12: New Button on BOM Upload — Reuse Existing Code via Imports

**CRITICAL: Do NOT modify the existing BOM Upload code written by another developer.**

**Strategy: Option B — New button, import their functions**

**Existing BOM Upload code** (`clevertech/doctype/bom_upload/bom_upload.py`) provides:
```
Importable Functions:
├── parse_rows(ws)                              → Excel worksheet → list of row dicts
├── build_tree(rows)                            → Row list → nested tree (stack-based, uses "level" field)
├── ensure_item_exists(item_code, desc, uom)    → Create Item master if missing
├── create_bom_recursive(node, project, root)   → Bottom-up BOM creation + child linking
└── create_boms(docname)                        → Main entry point (existing button calls this)

Helper Functions:
├── clean_code(code)                            → Remove dots, strip whitespace from item codes
├── to_float(val, default)                      → Safe float conversion
└── normalize_uom(uom)                          → NUMERI→Nos, PEZZI→Nos, METRI→Meter
```

**Key finding:** Item creation happens INSIDE `create_bom_recursive()` — it calls
`ensure_item_exists()` for each node before creating the BOM. Item + BOM creation
are interleaved, not separate phases.

**Our new button's sequence (using their imports):**
```
Step 1: parse_rows(ws)                          → Their code — parse Excel
Step 2: build_tree(rows)                        → Their code — build hierarchy
Step 3: Walk tree → ensure_item_exists()        → Their code — Items must exist before
         for all assembly nodes                   Component Masters (Link field dependency)
Step 4: Create Component Masters                → OUR code — assemblies only, active_bom=null
Step 5: Run analysis                            → OUR code — hash comparison, blocking checks
Step 6: create_bom_recursive()                  → Their code — bottom-up BOM creation
         (calls ensure_item_exists again,          (harmless — checks existence, returns early)
          for leaf items too)
Step 7: Link active_bom back to                 → OUR code — set active_bom + hash
         Component Masters
```

**Dependency chain:**
```
Items must exist       → before Component Masters  (item_code is Link field to Item)
Component Masters must → before analysis           (blocking checks query Component Master)
exist
Analysis must pass     → before BOM creation        (blocked = stop, don't create BOMs)
BOMs must exist        → before linking active_bom   (need BOM name to set on Component Master)
```

**Why this works without touching their code:**
- Their existing "Create BOMs" button continues to work as-is
- Our new "Create BOMs with Validation" button imports their functions
- `ensure_item_exists()` is idempotent (checks first, skips if exists)
- `create_bom_recursive()` is idempotent (skips if BOM already active/default)
- Users choose which button to use: old (no tracking) or new (with Component Masters)

---

### Decision 12A: Mapping Function Inheritance Strategy (Phase 4H - 2026-02-01)

**Context:** The original `bom_upload.py` contains hardcoded mapping dictionaries for:
- Material normalization (Italian → English, e.g., "INOX" → "SS 304 No. 4")
- Surface treatment translation (Italian → English)
- Type of material extraction (first word of description → type)
- Item group/HSN code assignment (item code prefix → group/HSN)
- Default expense account assignment (item code prefix → account)

**Situation:** Mapping doctypes exist but are not yet utilized:
- `Surface Treatment Translation` (italian → english)
- `Material Mapping` (materiale → material)
- `Type of Material` (item_description → type_of_material)

**Future Work:** Developer will migrate hardcoded dictionaries to use these doctypes.

**Question:** How should `bom_upload_enhanced.py` handle mapping functions?

**Options Considered:**

| Option | Approach | Pros | Cons |
|--------|----------|------|------|
| **A: Copy functions** | Duplicate mapping functions to enhanced file | Independent from original | ❌ Code duplication<br>❌ Won't inherit doctype updates |
| **B: Import functions** ✅ | Import all mapping functions from bom_upload.py | ✅ Zero duplication<br>✅ Auto-inherits doctype migration<br>✅ Single source of truth | None |
| **C: Create separate module** | Extract to shared module, refactor both files | Clean separation | ❌ Requires modifying bom_upload.py<br>❌ Violates Decision 12 |

**Decision: Option B — Import All Mapping Functions**

**Implementation in `bom_upload_enhanced.py`:**

```python
from clevertech.clevertech.doctype.bom_upload.bom_upload import (
    # Core logic (reuse as-is)
    build_tree,
    ensure_item_exists,
    create_bom_recursive,

    # Mapping functions (will auto-inherit doctype changes)
    normalize_material,           # ← When developer updates to use Material Mapping
    get_surface_treatment,        #    doctype, we automatically inherit it!
    get_type_of_material,
    get_item_group_and_hsn,
    get_default_expense_account,

    # Utility functions
    clean_code,
    to_float,
    normalize_uom,
    HAS_IMAGE_LOADER,
)

# DO NOT import parse_rows - replaced by parse_rows_dynamic()
```

**What Enhanced Code Adds (ONLY):**
1. `map_excel_columns(ws)` — Dynamic header detection (handles column shifts)
2. `parse_rows_dynamic(ws)` — Replacement for hardcoded `parse_rows()`
3. Excel format validation — Block upload if required columns missing

**What Enhanced Code DOES NOT Touch:**
- ❌ Mapping functions (import from original)
- ❌ Item creation logic (reuse `ensure_item_exists`)
- ❌ BOM creation logic (reuse `create_bom_recursive`)
- ❌ Tree building logic (reuse `build_tree`)

**Inheritance Flow:**

| Timeline | What Happens |
|----------|--------------|
| **Today** | Enhanced imports `normalize_material()` → uses hardcoded dictionary |
| **Developer migrates to doctypes** | Updates `normalize_material()` in `bom_upload.py` to query Material Mapping doctype |
| **Enhanced code** | Automatically uses new doctype-based version — zero changes needed! ✅ |

**Benefits:**
1. **Zero Code Duplication** — Single source of truth in `bom_upload.py`
2. **Automatic Migration** — When mappings move to doctypes, enhanced code inherits automatically
3. **Follows Decision 12** — Reuse existing code via imports, don't modify original
4. **Clear Separation** — Enhanced adds ONLY dynamic column detection
5. **Easy Review** — Diff shows only column detection logic, nothing else

**Example: Future Migration (Developer's Work):**

```python
# BEFORE (current state in bom_upload.py)
def normalize_material(material):
    material_mapping = {
        "INOX": "SS 304 No. 4",
        "ALLUMINIO": "HE-30(Aluminum Alloy 6082)",
        # ... 50+ hardcoded entries
    }
    return material_mapping.get(mat, mat)

# AFTER (developer migrates to doctype)
def normalize_material(material):
    """Now queries Material Mapping doctype"""
    if not material:
        return None

    mapped = frappe.db.get_value(
        "Material Mapping",
        {"materiale": material.strip()},
        "material"
    )
    return mapped or material
```

**Enhanced code automatically uses the new version** — no changes required in `bom_upload_enhanced.py`! ✅

**Why This Decision:**
- Respects Decision 12 (don't modify inherited code)
- Ensures enhanced upload benefits from all future improvements
- Minimizes maintenance burden (one place to update mappings)
- Clear architectural boundary: enhanced = column detection, original = everything else

---

### Decision 13: Project Quantity Multiplication and Simplified Procurement Limit (FINAL DESIGN)

**Problem Identified:** `bom_qty_required` was summing raw `qty_per_unit` from BOM Usage table without accounting for how many units of the parent assembly the project actually needs.

**Example of the Bug:**
```
BOM-A (project needs 2 units)
├── RM-1 (qty_per_unit = 2 per unit of A)
└── RM-2 (qty_per_unit = 5 per unit of A)

❌ WRONG (old):  bom_qty_required for RM-1 = 2   (just qty_per_unit, no multiplication)
✅ CORRECT:      bom_qty_required for RM-1 = 4   (2 units of A × 2 per unit = 4 total)
                 bom_qty_required for RM-2 = 10  (2 units of A × 5 per unit = 10 total)
```

---

## Final Simplified Design (Phase 4B Implementation)

### Core Principles

**Three fundamental rules that drive the entire system:**

1. **`project_qty`** = **ALWAYS manually entered** (never auto-calculated)
   - User enters it OR comes from Excel column E
   - System NEVER overwrites this value

2. **`bom_qty_required`** = **ALWAYS auto-calculated** from BOM usage
   - Multiplies `qty_per_unit × parent.project_qty`
   - Sums across all parent BOMs for multi-BOM usage

3. **`total_qty_limit`** = **MAX(project_qty, bom_qty_required)**
   - Simplified from original Decision 5 which used `loose_qty_required`
   - Hard procurement limit enforced in Material Request validation

---

### New Fields Added

**Field 1: `project_qty` (Float)**
```json
{
  "fieldname": "project_qty",
  "label": "Project Qty Required",
  "description": "From Excel for BOM Upload (read-only), manually entered for Cutover/Manual Entry",
  "read_only_depends_on": "eval:doc.created_from=='BOM Upload'",
  "default": "0"
}
```

**Purpose:** Input field for "How many units of this component does the project need?"

**Behavior:**
- **BOM Upload:** Set from Excel column E, becomes **read-only** (data integrity)
- **Cutover:** Defaults to 1, user can edit (manual review)
- **Manual Entry:** User enters directly, fully editable

**Field 2: `created_from` (Select)**
```json
{
  "fieldname": "created_from",
  "label": "Created From",
  "options": "\nBOM Upload\nCutover\nManual Entry",
  "read_only": 1,
  "in_list_view": 1,
  "in_standard_filter": 1
}
```

**Purpose:** Source tracking for traceability and data governance

**Benefits:**
- ✅ Know data origin for quality assessment
- ✅ Filter cutover data needing review
- ✅ Different UI hints based on source
- ✅ Audit trail for compliance

---

### Implementation Details

#### Fixed Calculation: `calculate_bom_qty_required()`

**File:** `project_component_master.py`

```python
def calculate_bom_qty_required(self):
    """
    Calculate BOM quantity required by multiplying qty_per_unit by parent's project_qty.

    For root assemblies (no bom_usage): bom_qty_required = project_qty
    For loose items "Pending Conversion": bom_qty_required = 0
    For components in BOMs: SUM(parent.project_qty × qty_per_unit)
    """
    if not self.bom_usage:
        # Root assembly or loose item - no BOM usage rows
        if self.is_loose_item:
            self.bom_qty_required = 0  # Not in any BOM yet
        else:
            self.bom_qty_required = self.project_qty or 0  # Root assembly
        return

    # Has BOM usage rows - calculate from all parent BOMs
    total = 0
    for usage in self.bom_usage:
        # Get parent's manually-set project quantity
        parent_qty = frappe.db.get_value(
            "Project Component Master",
            {"project": self.project, "item_code": usage.parent_item},
            "project_qty"
        ) or 0

        # Multiply and store row-level total
        usage.total_qty_required = (usage.qty_per_unit or 0) * parent_qty
        total += usage.total_qty_required

    self.bom_qty_required = total
```

**Key Changes:**
- ✅ Multiplies `qty_per_unit × parent_project_qty` (fixes the bug!)
- ✅ Populates `total_qty_required` on each BOM Usage row
- ✅ Handles root assemblies, loose items, and child components correctly

#### Simplified: `calculate_total_qty_limit()`

**Original (Decision 5):**
```python
total_qty_limit = MAX(loose_qty_required, bom_qty_required)
```

**New (Simplified):**
```python
def calculate_total_qty_limit(self):
    """MAX(project_qty, bom_qty_required) - hard procurement limit."""
    project = self.project_qty or 0
    bom = self.bom_qty_required or 0
    self.total_qty_limit = max(project, bom)
```

**Rationale:** User's `project_qty` estimate should override if higher than BOM requirement

**Removed:** `calculate_project_qty()` method entirely (project_qty is always manual!)

---

### Multi-Level Calculation Example

```
Project Structure (from Excel upload):

TOP-ASSY
├── project_qty = 3 (from Excel column E)
├── bom_qty_required = 3 (no bom_usage, so equals project_qty)
├── total_qty_limit = MAX(3, 3) = 3

SUB-ASSY (child of TOP-ASSY)
├── qty_per_unit = 2 (in TOP-ASSY's BOM)
├── project_qty = 0 (user doesn't set for child items)
├── bom_usage table:
│   └── parent=TOP-ASSY, qty_per_unit=2, total_qty_required=6 (3×2)
├── bom_qty_required = 6 (auto-calculated)
├── total_qty_limit = MAX(0, 6) = 6

MOTOR (child of SUB-ASSY, used in 2 BOMs)
├── qty_per_unit = 1 (in SUB-ASSY's BOM)
├── qty_per_unit = 2 (in PUMP-ASSY's BOM, assume PUMP project_qty=4)
├── project_qty = 0
├── bom_usage table (2 rows):
│   ├── parent=SUB-ASSY, qty_per_unit=1, total_qty_required=6 (6×1)
│   └── parent=PUMP-ASSY, qty_per_unit=2, total_qty_required=8 (4×2)
├── bom_qty_required = 6 + 8 = 14 (SUM approach for multi-BOM)
├── total_qty_limit = MAX(0, 14) = 14
```

**Note:** For child items, users typically don't set `project_qty` (leave at 0), so `total_qty_limit` uses `bom_qty_required`.

---

### Loose Item Handling (All 4 Conversion Statuses)

**Status 1: "Not Applicable"** (`is_loose_item = 0`)
- Regular assembly/component
- Follows standard calculation logic

**Status 2: "Pending Conversion"** (`is_loose_item = 1`, no bom_usage)
```
Bearing-SKF:
├── is_loose_item = 1
├── project_qty = 150 (user's estimate, manually entered)
├── loose_qty_required = 100 (user decides to procure this much upfront)
├── bom_usage = empty (not in any BOM yet)
├── bom_qty_required = 0 (calculation sets to 0 for loose items)
├── total_qty_limit = MAX(150, 0) = 150
└── Result: Can procure up to 150 (user's estimate is the limit)
```

**Status 3: "Converted to BOM"** (`is_loose_item = 1`, 1 bom_usage row)
```
Bearing-SKF now added to Motor-Assembly BOM:
├── is_loose_item = 1 (preserves history)
├── project_qty = 150 (unchanged, user's original estimate)
├── loose_qty_required = 100 (historical loose procurement)
├── bom_usage: parent=Motor-Assembly (project_qty=50), qty_per_unit=2
├── bom_qty_required = 2 × 50 = 100 (auto-calculated from BOM)
├── total_qty_limit = MAX(150, 100) = 150
└── Result: User's estimate (150) wins! Prevents duplicate procurement.
```

**Status 4: "Partial"** (`is_loose_item = 1`, 2+ bom_usage rows)
```
Bearing-SKF used in 2 assemblies:
├── is_loose_item = 1
├── project_qty = 150
├── bom_usage (2 rows):
│   ├── Motor-Assembly (project_qty=50) × qty_per_unit=2 = 100
│   └── Pump-Assembly (project_qty=30) × qty_per_unit=1 = 30
├── bom_qty_required = 100 + 30 = 130 (SUM approach)
├── total_qty_limit = MAX(150, 130) = 150
└── Result: User's estimate still wins. Loose procurement covers both BOMs.
```

**Key Insight:** Loose items use `project_qty` for procurement planning even before BOM exists, preventing over-procurement when later converted.

---

### Three Data Flows

#### Flow 1: BOM Upload (New Projects)

**Sequence:**
```
1. User uploads Excel with column E (quantity)
2. bom_upload_enhanced.py parses Excel
3. For each assembly:
   - Sets project_qty from column E ✅
   - Sets created_from = "BOM Upload" ✅
   - project_qty becomes READ-ONLY (data integrity) ✅
4. Creates BOMs bottom-up
5. BOM hooks populate bom_usage tables
6. Save triggers:
   - calculate_bom_qty_required() multiplies project_qty × qty_per_unit ✅
   - calculate_total_qty_limit() = MAX(project_qty, bom_qty_required) ✅
```

**Data Integrity Protection:**
- `project_qty` read-only for BOM Upload source
- User cannot accidentally change Excel values
- Forces proper workflow: update PE2 → re-upload
- Leverages existing duplicate BOM blocking

#### Flow 2: Cutover (Existing Projects)

**Sequence:**
```
1. User clicks "Generate Component Masters" on Project
2. bulk_generation.py creates CMs from existing BOMs:
   - Sets project_qty = 1 (default) ✅
   - Sets created_from = "Cutover" ✅
   - project_qty stays EDITABLE (needs review) ✅
3. Warning shown: "Review and update Project Qty Required"
4. User manually updates root assembly project_qty to correct value
5. Save triggers recalculation cascade:
   - Root assembly: bom_qty_required = project_qty
   - Children: bom_qty_required = SUM(parent_qty × qty_per_unit)
   - total_qty_limit = MAX(project_qty, bom_qty_required)
```

**Cutover Limitations:**
- Root assemblies have NO bom_usage rows (nothing references them)
- Raw materials get NO Component Masters (only assemblies with BOMs)
- Full multiplication chain requires user to set root project_qty
- System defaults to 1 (safe but incomplete)

#### Flow 3: Manual Entry

**Sequence:**
```
1. User creates Component Master directly in ERPNext
2. Sets created_from = "Manual Entry" manually
3. project_qty fully editable (no restrictions)
4. User enters all values including project_qty
5. Save triggers normal calculations
```

**Use Case:** Loose items created before BOM exists

---

### Files Modified (Phase 4B)

1. **project_component_master.json**
   - Added `project_qty` field (Float, conditional read-only)
   - Added `created_from` field (Select, tracking)
   - Updated `total_qty_limit` description

2. **project_component_master.py**
   - ✅ Fixed `calculate_bom_qty_required()` to multiply
   - ✅ Updated `calculate_total_qty_limit()` to MAX(project_qty, bom_qty)
   - ❌ Removed `calculate_project_qty()` method entirely
   - ❌ Removed call to calculate_project_qty from before_save()

3. **bom_upload_enhanced.py**
   - Sets `project_qty` from Excel column E
   - Sets `created_from = "BOM Upload"`

4. **bulk_generation.py**
   - Sets `project_qty = 1` as default
   - Sets `created_from = "Cutover"`
   - Shows warning message to review quantities

---

### Design Rationale Summary

**Why project_qty is always manual:**
- ✅ Clear separation: manual input vs calculated output
- ✅ No auto-overwrite confusion (user retains control)
- ✅ Simpler code (no complex auto-calculation logic)
- ✅ User can override procurement limits when needed
- ✅ Works for all flows: new uploads, cutover, loose items, manual entry

**Why read-only for BOM Upload:**
- ✅ PE2 is source of truth, ERPNext reflects it
- ✅ Prevents accidental data corruption
- ✅ Forces proper workflow: fix PE2 → re-upload
- ✅ Leverages existing duplicate BOM blocking
- ✅ Clear signal: "this is managed by upload"

**Why MAX(project_qty, bom_qty_required):**
- ✅ Simpler than original Decision 5
- ✅ User's estimate overrides if higher
- ✅ Handles loose items before/after BOM conversion
- ✅ Prevents over-procurement
- ✅ Single procurement limit for all sources

---

### Decision 14: Make/Buy Flag and Procurement Routing

**Problem:** In ETO manufacturing, not all items in a BOM tree are procured the same way:
- Root machines (M level) and sub-assemblies (G level) are **assembled in-house**
- Some sub-assemblies (D level) are **procured as complete units** from vendors
- Raw materials (RM level) are **procured** unless their parent assembly is bought as a unit

**When a parent assembly is "Buy" (procured as unit):**
- The parent itself appears in MR/PO
- Its child RMs do NOT need separate procurement (they come with the assembly)

**When a parent assembly is "Make" (assembled in-house):**
- The parent does NOT appear in MR/PO
- Its child RMs DO need separate procurement via MR/PO

---

#### Make/Buy Field Design

```json
{
  "fieldname": "make_or_buy",
  "fieldtype": "Select",
  "label": "Make / Buy",
  "options": "\nMake\nBuy",
  "description": "Make = assembled in-house (children procured separately). Buy = procured as unit."
}
```

**Defaults by item type:**
| Level | Typical Default | Notes |
|-------|----------------|-------|
| M (Root Machine) | Make | Always assembled in-house |
| G (Sub-Assembly) | Make | In-house (vendors not yet developed) |
| D (Sub-Assembly) | Make or Buy | Depends on vendor availability per project |
| RM (Raw Material) | Buy | Always procured |

**Editability:**
- ✅ Editable directly on Component Master form (anytime, including mid-project)
- ✅ Can change mid-project (e.g., vendor fails → switch D from Buy to Make)
- ✅ Set from BOM Upload Excel column (if PE2 team adds the column)

---

#### BOM Upload Merge Logic for Make/Buy

PE2 exports the full BOM file every time. Previously tagged items should NOT require re-tagging.

```python
# Merge strategy during BOM Upload:
if excel_has_make_buy_value:       # Excel column has value
    component.make_or_buy = excel_value    # Use Excel value
elif component_already_exists:     # Existing CM, Excel column empty
    pass                           # Keep existing value (no change)
elif new_component_with_bom:       # New item with children
    component.make_or_buy = "Make" # Default for assemblies
elif new_component_without_bom:    # New leaf item (RM)
    component.make_or_buy = "Buy"  # Default for raw materials
```

**Key behavior:** PE2 team only tags new items or changes. Previously tagged items can be left blank in Excel.

---

#### Impact on Quantity Calculations

**CRITICAL:** Parent's make/buy flag determines whether children need separate procurement.

```
M (Make) — project_qty = 2
├─ G1 (Make)
│   ├─ D1 (Buy)  ← Procured as unit. D1's RMs covered!
│   │   ├─ RM-1  ← SKIP (parent D1 is Buy, covers RM-1)
│   │   └─ RM-2  ← SKIP (parent D1 is Buy, covers RM-2)
│   └─ D2 (Make) ← In-house. D2's RMs need separate procurement!
│       ├─ RM-1  ← COUNT (parent D2 is Make, RM-1 needs own MR)
│       └─ RM-3  ← COUNT (parent D2 is Make, RM-3 needs own MR)
```

**Updated bom_qty_required calculation:**
```python
def calculate_bom_qty_required(self):
    total = 0
    for usage in self.bom_usage:
        parent = frappe.db.get_value(
            "Project Component Master",
            {"project": self.project, "item_code": usage.parent_item},
            ["project_qty", "make_or_buy"], as_dict=True
        )

        # Only count if parent is "Make" (assembled in-house)
        # If parent is "Buy", this component is covered by parent's procurement
        if parent and parent.make_or_buy == "Make":
            usage.total_qty_required = (usage.qty_per_unit or 0) * (parent.project_qty or 0)
            total += usage.total_qty_required
        else:
            usage.total_qty_required = 0  # Covered by parent procurement

    self.bom_qty_required = total
```

---

#### Cascade Recalculation on Make/Buy Change

When make/buy changes mid-project, ALL children's `bom_qty_required` must recalculate:

```
BEFORE: D1 = Buy
  RM-1.bom_qty_required → D1 excluded → only counts Make parents → 0
  RM-2.bom_qty_required → D1 excluded → 0

AFTER: D1 changed to Make (vendor failed)
  RM-1.bom_qty_required → D1 now included → D1.project_qty × qty_per_unit
  RM-2.bom_qty_required → D1 now included → D1.project_qty × qty_per_unit

  → Cascade: All children of D1 recalculate bom_qty_required!
```

**Implementation:**
```python
def before_save(self):
    if self.has_value_changed("make_or_buy"):
        self.recalculate_children_bom_qty()
    # existing calculations...

def recalculate_children_bom_qty(self):
    """When make/buy changes, trigger recalc on all BOM children."""
    if not self.active_bom:
        return
    bom_items = frappe.get_all("BOM Item",
        filters={"parent": self.active_bom},
        fields=["item_code"])
    for item in bom_items:
        child_cm = frappe.db.get_value(
            "Project Component Master",
            {"project": self.project, "item_code": item.item_code}, "name")
        if child_cm:
            child_doc = frappe.get_doc("Project Component Master", child_cm)
            child_doc.save()  # Triggers before_save → recalculates
```

---

#### Impact on Validation

MR/PO validation only enforces limits for "Buy" items (items that are actually procured):

```python
# In validate_material_request_qty / validate_purchase_order_qty:
component = get_component_master(project, item_code)

if not component:
    return  # Not tracked

if component.make_or_buy != "Buy":
    return  # "Make" items are not directly procured, skip validation

# ... existing cumulative qty validation for Buy items
```

---

#### Impact on Reports

**Report at M & G level with drill-down:**
```
Project: PROJ-2024-MACHINE-A
═══════════════════════════════════════════════════════
M-001 (Make)                           Overall: 65%
├─ G1 (Make)                           Procurement: 70%
│   ├─ D1 (Buy)     PO: 10/10 ✓       ← Direct procurement
│   │   (RMs covered by D1 purchase)
│   └─ D2 (Make)                       ← In-house
│       ├─ RM-3     PO: 150/200 (75%) ← Separate procurement
│       └─ RM-4     PO: 0/300 (0%)    ← Pending!
├─ G2 (Make)                           Procurement: 60%
│   └─ D3 (Buy)     PO: 8/15 (53%)    ← Direct procurement
│       (RMs covered by D3 purchase)
```

**Report logic per node:**
- **Buy item:** Show its own procurement status
- **Make item:** Show rollup of children's procurement %
- **Buy item's children:** Skip (covered by parent's procurement)

---

#### Project Field Names by DocType

| DocType | Project Field Name | Notes |
|---------|-------------------|-------|
| Material Request | `custom_project_` | Custom field (with trailing underscore) |
| Request for Quotation | `custom_project` | Custom field (no trailing underscore) |
| Purchase Order | `project` | Standard ERPNext field |
| Purchase Receipt | `project` | Standard ERPNext field |

**Important:** Validation code must use the correct field name for each doctype.

---

### Decision 15: Why Keep Component Masters for Root/Sub-Assemblies (M & G Levels)

**Question raised:** Since M and G levels are always "Make" (assembled in-house), what benefit do their Component Masters provide?

**Answer: They are essential for 3 reasons:**

**1. project_qty Storage and Propagation Chain**
```
M.project_qty = 2        ← WHERE the quantity originates (stored in Component Master)
│
├─ G.bom_qty_required = M.project_qty × qty_per_unit = 2 × 3 = 6
│  │
│  ├─ D.bom_qty_required = G.project_qty × qty_per_unit
│  │   │
│  │   └─ RM.bom_qty_required = D.project_qty × qty_per_unit
```
Without M and G Component Masters, the calculation chain breaks — there's no record to store root project_qty.

**2. Report Entry Points**
Management wants: "Show me Machine M — how is procurement?" Component Master for M is the starting node for the tree drill-down report.

**3. BOM Change Detection**
Already implemented — `bom_structure_hash` comparison during BOM Upload requires Component Master to exist for assemblies.

**What they DON'T use:**
- Procurement validation (not procured, they're "Make")
- total_qty_procured (always 0)
- These fields sit empty — acceptable trade-off for consistent data model.

---

### Decision 16: BOM Version Change Handling (During BOM Upload)

**Problem:** When a new BOM version is uploaded via PE2 Excel for an item that already has an active BOM in Component Master:
1. The old BOM's `bom_usage` entries remain on child Component Masters, double-counting qty
2. Items removed in the new BOM version still show procurement demand
3. Need to handle different procurement stages differently (no procurement vs MR vs RFQ vs PO)

**Tiered Blocking Rules:**

| Procurement Stage | Behavior | User Action |
|-------------------|----------|-------------|
| **No MR/RFQ/PO** | Confirm dialog with remarks + impacted parents shown | User confirms, keys in reason |
| **MR exists** | Confirmable (changed from BLOCK) | User confirms with remarks |
| **RFQ exists** | Confirmable (changed from BLOCK) | User confirms with remarks |
| **PO exists** | Requires Manager role to proceed | Manager confirms or blocks |

**Note:** Old BOM is **demoted** (`is_default=0`), not deactivated. Stays `is_active=1` so parent BOMs referencing it via `bom_no` remain valid. Impacted parents are surfaced for engineer review (controlled upward propagation).

---

**Scenario A — No Procurement (Hash Changed, No MR/RFQ/PO):**
```
Item A has BOM-A-001 (active), no MRs/RFQs/POs for any children
User uploads PE2 file with changed BOM structure

System behavior:
1. Detects hash change
2. Checks procurement status → none found
3. Shows confirm dialog:
   "BOM structure changed for Item A. Proceed with new version?"
   [Remarks: ________________]
   [Cancel] [Proceed]
4. If user confirms:
   - Stores remarks in Component Master (version_change_remarks field)
   - Old BOM's usage rows removed from children
   - New BOM created and linked
   - Proceeds with upload
5. If user cancels:
   - Upload blocked for this component and its ancestors
```

**Scenario B — MR or RFQ Exists:**
```
Item A has BOM-A-001 (active), child X has MR-00123 submitted
User uploads PE2 file with changed BOM structure

System behavior:
1. Detects hash change
2. Checks procurement status → MR found
3. Shows confirm dialog (confirmable, not hard block):
   "BOM structure changed for Item A. Child X has active MR-00123 (qty: 50).
    Impacted parents: [Motor-Assembly, ...]
    Remarks: ________________"
   [Cancel] [Proceed]
4. If user confirms:
   - Old BOM-A-001 demoted (is_default=0, is_active stays 1)
   - New BOM-A-002 created (is_active=1, is_default=1)
   - on_bom_submit handles version history + bom_usage cleanup
   - Impacted parent BOMs returned for engineer review
5. Parent BOMs still reference old BOM-A-001 via bom_no — valid until
   engineer adopts new version (controlled upward propagation)
```

**Scenario C — PO Exists (Stricter):**
```
Item A has BOM-A-001 (active), child X has PO-00456 submitted
User uploads PE2 file with changed BOM structure

System behavior:
1. Detects hash change
2. Checks procurement status → PO found
3. Checks user role:
   - If NOT "Component Master Manager" or "System Manager":
     Shows BLOCK dialog (same as Scenario B)
   - If HAS manager role:
     Shows confirm dialog with strong warning:
     "⚠️ CAUTION: Child items have active Purchase Orders!
      - X: PO-00456 (Submitted, qty: 50)

      Proceeding will change the BOM. Existing POs will remain unchanged.
      [Remarks: ________________]
      [Cancel] [Proceed Anyway]"
```

**Scenario D — BOM Cancelled:**
```
Item A has BOM-A-001 as active_bom
User cancels BOM-A-001

System behavior:
1. System finds fallback BOM (active+default first, then any active)
2. If fallback found:
   - Sets active_bom = BOM-A-002
   - Populates bom_usage entries from fallback
   - Notifies user: "BOM-A-001 cancelled. Switched to BOM-A-002"
3. If no fallback:
   - Clears active_bom
   - has_bom remains 1 (item type unchanged)
```

---

**New Field for Remarks:**
```json
{
  "fieldname": "version_change_remarks",
  "fieldtype": "Small Text",
  "label": "Version Change Remarks",
  "description": "Reason for allowing BOM version change (logged during upload)",
  "read_only": 1
}
```

**Implementation:**
```python
# In bom_upload_enhanced.py:

def _check_procurement_blocking(project, item_code, old_bom_name):
    """
    Check if procurement exists and determine blocking level.

    Returns:
        dict: {
            "can_proceed": bool,
            "blocking_level": "none" | "confirm" | "block" | "manager_required",
            "procurement_docs": [...],
            "message": str
        }
    """
    # Get all child items from old BOM
    old_bom = frappe.get_doc("BOM", old_bom_name)

    blocking_level = "none"
    procurement_docs = []

    for item in old_bom.items:
        # Check MR
        mrs = get_material_requests(project, item.item_code)
        if mrs:
            procurement_docs.extend(mrs)
            blocking_level = max_level(blocking_level, "block")

        # Check RFQ
        rfqs = get_rfqs(project, item.item_code)
        if rfqs:
            procurement_docs.extend(rfqs)
            blocking_level = max_level(blocking_level, "block")

        # Check PO
        pos = get_purchase_orders(project, item.item_code)
        if pos:
            procurement_docs.extend(pos)
            blocking_level = "manager_required"  # Strictest

    return {
        "can_proceed": blocking_level == "none",
        "blocking_level": blocking_level,
        "procurement_docs": procurement_docs,
    }


def _can_override_po_block():
    """Check if current user has manager role for PO-stage override."""
    user_roles = frappe.get_roles()
    return "Component Master Manager" in user_roles or "System Manager" in user_roles
```

**User-Facing Dialogs:**

1. **Confirm Dialog (No Procurement):**
   - Title: "BOM Structure Changed"
   - Message: "BOM structure changed for {item}. Proceed with new version?"
   - Fields: Remarks (mandatory)
   - Buttons: [Cancel] [Proceed]

2. **Block Dialog (MR/RFQ Exists):**
   - Title: "BOM Change Blocked"
   - Message: Lists procurement documents
   - Instructions: Deactivate old BOM, re-run upload
   - Button: [Open BOM List]

3. **Manager Confirm Dialog (PO Exists):**
   - Title: "⚠️ BOM Change - Manager Override"
   - Message: Strong warning about existing POs
   - Fields: Remarks (mandatory)
   - Buttons: [Cancel] [Proceed Anyway]
   - Only shown to users with Manager role

---

## Design Evolution

This section documents key design iterations during the architecture discussion.

### Evolution 1: Component Master Scope

**Initial Proposal:**
> "Create Component Master only for items having BOM (excluding loose items)"

**Issue Identified:**
> "But loose items have no BOM, where do they live?"

**Resolution:**
Changed scope to: `has_bom = Yes OR is_loose_item = Yes`

**Learning:** Loose items are a special case requiring tracking despite being leaf nodes.

---

### Evolution 2: Procurement Quantity Logic

**Initial Proposal:**
> "If loose=100 and BOM=50, error if MR qty > 100"

**Issue Identified:**
> "What if loose=100 and BOM=150? Using MAX(100, 150)=150 is correct, but what about the 100 already procured?"

**Resolution:**
- total_qty_limit = MAX(loose, bom)
- total_procurement = SUM(all MRs including loose)
- Block if: total_procurement > total_qty_limit
- Warning if: loose > bom (over-procurement alert)

**Learning:** Need to track cumulative procurement across loose + BOM sources.

---

### Evolution 3: Change Blocking Granularity

**Initial Proposal:**
> "Block entire upload until changes resolved"

**Issue Identified:**
> "If 100 components uploaded and 2 changed, blocks 98 good components unnecessarily"

**Resolution:**
Staged approach:
1. Categorize: new / unchanged / changed / blocked
2. Create new and unchanged immediately
3. Block only components dependent on changed items
4. Show resolution dialog for changed items

**Learning:** Surgical blocking maintains efficiency while ensuring safety.

---

### Evolution 4: Loose Item State Model

**Initial Proposal:**
> "is_loose_item becomes No after conversion"

**Issue Identified:**
> "Loses procurement history and can't explain why total_limit > bom_qty"

**Resolution:**
- Keep `is_loose_item = Yes` permanently
- Add `bom_conversion_status` field (Pending / Converted / Partial)
- Loose vs BOM procurement tracked separately in child table

**Learning:** State transitions, not binary flags, better model complex workflows.

---

### Evolution 5: Budget Tracking Complexity

**Initial Proposal:**
> "Budget at component level and leaf level in child table"

**Issue Identified:**
> "Child table duplicates BOM structure, sync nightmare, high maintenance"

**Resolution:**
- Budget only for managed components (assemblies + loose)
- Rollup uses: managed component budgets + leaf item actual costs
- Matches business practice (designers estimate at assembly level)

**Learning:** Simplicity over completeness when complexity doesn't add business value.

---

### Evolution 6: Component Master Scope Expanded to ALL Items

**Initial Design (v1.0-v1.7):**
> "Component Masters only for assemblies (has_bom=1) and loose items (is_loose_item=1). Raw materials are just BOM Items."

**Issue Identified:**
> "Raw materials are not present in Component Masters. MR/PO validation can't enforce limits on RM procurement. Report rollup from M/G level needs ALL levels to exist."

**Resolution:**
- Component Masters created for ALL items in BOM tree (assemblies + raw materials)
- Raw materials: has_bom=0, make_or_buy=Buy
- Enables: procurement validation, report rollup, calculation chain
- BOM Upload modified to create Component Masters for leaf items too

**Learning:** Procurement control requires visibility at every level. Tracking only assemblies left a gap at the most procured level (raw materials).

---

### Evolution 7: Make/Buy Flag for Procurement Routing

**Initial Design:**
> "All items in Component Master follow same procurement rules."

**Issue Identified:**
> "If D-level sub-assembly is procured as whole unit (Buy), its raw materials should NOT be separately procured. If D is assembled in-house (Make), its RMs need separate MRs."

**Resolution:**
- Added `make_or_buy` field (Select: Make/Buy)
- Editable anytime on Component Master form (mid-project changes supported)
- BOM Upload merge: Excel value wins if present, else keep existing
- bom_qty_required calculation only counts "Make" parents
- MR/PO validation only enforces for "Buy" items
- Cascade recalculation when make/buy changes on parent

**Learning:** Procurement routing depends on manufacturing strategy, not just BOM structure. The same BOM tree can have different procurement patterns depending on vendor availability.

---

## Final Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                     BOM Upload (Excel)                       │
│                  (PE2 Export, ~500 rows)                     │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              BOM Upload Analysis Engine                      │
│  Step 1: Parse Excel → Build tree                            │
│  Step 2: Create Component Masters FIRST (active_bom=null)    │
│  Step 3: Analyze — compare hashes, check procurement blocks  │
│  Step 4: Categorize: new / unchanged / changed / blocked     │
└───────────┬─────────────────────────────────┬───────────────┘
            │                                 │
            │ If blocked/changed              │ If clear
            ▼                                 ▼
┌─────────────────────────┐   ┌──────────────────────────────┐
│ Change Resolution Dialog│   │  Create BOMs (bottom-up)     │
│  • Show changes          │   │  • Use existing BOM Upload    │
│  • List blocked items    │   │    logic for BOM creation    │
│  • Require user action   │   │  • Link active_bom back to   │
│                          │   │    Component Masters         │
└─────────────────────────┘   │  • BOM hooks auto-populate    │
                               │    BOM Usage tables           │
                               └────────────┬─────────────────┘
                                            │
                                            ▼
                    ┌───────────────────────────────────────┐
                    │   Project Component Master            │
                    │   • Tracks managed components         │
                    │   • Budget & timeline                 │
                    │   • Procurement status                │
                    │   • Quantity limits                   │
                    └───────────┬───────────────────────────┘
                                │
                                ▼
                    ┌───────────────────────────────────────┐
                    │   Material Request Validation         │
                    │   • Check quantity limits             │
                    │   • Enforce MAX(loose, bom)           │
                    │   • Hard block if exceeded            │
                    └───────────┬───────────────────────────┘
                                │
                                ▼
                    ┌───────────────────────────────────────┐
                    │   Standard ERPNext Procurement        │
                    │   MR → RFQ → Quote → PO → Receipt     │
                    └───────────────────────────────────────┘
```

### Data Flow

**Scenario: Initial Upload (Day 1) — New Project via PE2**
```
1. Upload BOM Excel → 2 assemblies, 10 leaf items
2. Create Items for assemblies (ensure_item_exists — idempotent):
   - 2 Item masters for assembly nodes (Link field dependency)
3. Create Component Masters:
   - 2 Component Master entries (assemblies only)
   - has_bom=1, active_bom=null, design_status="Design Released"
4. Analysis: All new, no blocking issues
5. Create BOMs bottom-up (create_bom_recursive):
   - 2 BOM structures (with 10 leaf items in BOM Items)
   - 10 Item masters for leaf items (ensure_item_exists called again, idempotent)
6. Link back: Set active_bom and bom_structure_hash on Component Masters
7. BOM on_submit hooks populate BOM Usage tables
8. Final state: Design Released, Procurement Not Started
```

**Scenario: Loose Item Procurement (Day 5)**
```
1. User manually creates Component Master entry
   - item_code: Bearing-SKF-001
   - is_loose_item: Yes
   - loose_qty_required: 100
   - loose_item_reason: "Long lead time, design pending"
2. Create Material Request: 100 units
3. Component Master auto-updates:
   - total_qty_limit: 100
   - total_qty_procured: 100
   - procurement_status: In Progress
```

**Scenario: Incremental Upload (Day 30)**
```
1. Upload BOM Excel → 5 assemblies total
2. Analysis:
   - 2 unchanged (skip)
   - 2 new (create)
   - 1 changed (Gearbox structure modified)
3. Check dependencies:
   - Motor-Assembly uses Gearbox → Block Motor
   - Pump-Assembly doesn't use Gearbox → Allow
4. Show dialog:
   - "Gearbox changed, blocks Motor-Assembly"
   - "Create 2 new components (Pump-Assembly, Valve-Block)?"
5. User confirms Gearbox change → old BOM demoted, new version created
   - Impacted parents (Motor-Assembly) surfaced for review
6. Upload proceeds → Creates remaining components
7. Engineer reviews Motor-Assembly impact, adopts when ready
```

**Scenario: Material Request with Limit Check (Day 35)**
```
1. User creates MR from Motor-Assembly BOM
2. Includes Bearing-SKF-001 (qty 50)
3. Validation hook:
   - Checks Component Master
   - loose_qty_required: 100
   - bom_qty_required: 50 (from Motor BOM)
   - total_qty_limit: MAX(100, 50) = 100
   - Existing procurement: 100 (loose MR)
   - This MR would add: 50
   - Total: 150 > 100 ✗
4. Error: "Cannot exceed limit of 100. Already procured 100 as loose item."
5. User adjusts: Remove Bearing from MR (already covered by loose procurement)
```

---

## Success Criteria

The architecture is successful if it achieves:

### Functional Goals
1. ✓ Incremental BOM uploads without manual tracking
2. ✓ Change detection with impact analysis
3. ✓ Loose item integration without duplicate procurement
4. ✓ Procurement quantity control enforcement
5. ✓ Budget and timeline visibility per component
6. ✓ Audit trail of BOM versions and changes

### Non-Functional Goals
1. ✓ Maintainable: Clear separation of concerns (upload logic, validation, reporting)
2. ✓ Extensible: Can add new procurement controls without core changes
3. ✓ Performant: Analysis on 500-component BOM < 30 seconds
4. ✓ User-friendly: Clear error messages, actionable dialogs
5. ✓ Auditable: Full history of changes, decisions, procurement

### Business Outcomes
1. Reduced over-procurement (cost savings)
2. Faster project execution (parallel work on independent components)
3. Better cost control (budget tracking and variance analysis)
4. Improved visibility (management dashboards and reports)
5. Reduced manual coordination (system enforces rules)

---

## Future Enhancements

### Phase 2 Possibilities
1. **Differential Material Requests**
   - When BOM changes, auto-generate MR for ONLY new/changed items
   - Skip items already procured

2. **Procurement Timeline Prediction**
   - Based on lead times, predict component arrival dates
   - Flag assemblies blocked by late components

3. **Cost Variance Alerts**
   - Auto-alert when actual PO cost exceeds budget by >10%
   - Suggest design alternatives

4. **Supplier Integration**
   - When BOM changes, auto-notify suppliers of affected RFQs
   - Request revised quotes

5. **Design Change Workflow**
   - Formal approval process for BOM changes
   - Impact analysis report before change approved

---

## Appendix: Key Design Principles

### 1. Explicit Over Implicit
- Loose items require explicit conversion enabling
- Changes require explicit user resolution
- No silent auto-corrections

### 2. Fail Fast and Loud
- Hard blocks on validation failures
- Clear error messages with actionable steps
- Better to stop early than corrupt data

### 3. Single Source of Truth
- Component Master is THE record for project-specific component data
- Other doctypes (Item, BOM) remain global/reusable
- Clear ownership boundaries

### 4. Business Logic in Code, Not User Memory
- System enforces quantity limits (not user discipline)
- System detects changes (not user tracking)
- System calculates rollups (not spreadsheets)

### 5. Optimize for Common Case
- 90% of uploads are incremental (mostly new, few changed)
- Allow fast path for common case
- Slow path only for exceptions

---

## Conclusion

The **Project Component Master** architecture provides a robust, maintainable solution for Clevertech's complex ETO procurement workflow. By introducing a project-specific component tracking layer, the system bridges the gap between design evolution (PE2) and procurement execution (ERPNext).

Key innovations:
- **Full BOM tree tracking** (assemblies + raw materials, all levels)
- **Make/Buy routing** (parent's flag determines children's procurement path)
- **MAX-based quantity limits** (preventing duplicate procurement)
- **Ancestor chain blocking** (surgical change control)
- **Hash-based change detection** (fast and reliable)
- **Three-layer procurement validation** (MR + RFQ + PO with cumulative checks)
- **BOM version change handling** (old version cleanup, fallback on cancel, procurement impact warnings)

The design balances flexibility (supports continuous design evolution) with control (enforces procurement limits), enabling Clevertech to scale their ETO operations efficiently.

---

## Implementation Status

**Phase 1: DocTypes Created** ✅ (2026-01-26)
- Project Component Master (40+ fields, 2 child tables)
- Component Procurement Record (child table)
- Component BOM Usage (child table)
- All fields migrated and visible in ERPNext

**Phase 1A: BOM Event Hooks** ✅ (2026-01-26)
- on_submit, on_cancel, on_update_after_submit hooks
- Auto-populates BOM Usage child table
- Hash-based structure change detection
- Info messages for untracked project BOMs
- Silent skip pattern for non-project BOMs
- **File:** `project_component_master/bom_hooks.py`

**Phase 2A: Bulk Generation (Cutover Flow)** ✅ (2026-01-27)
- "Generate Component Masters" button on Project form — **HIDDEN** (use BOM Upload instead)
- Creates Component Masters FROM existing BOMs (BOM → CM direction)
- Tested on project SMR260001: 24 Component Masters created
- **Button hidden:** BOM Upload handles this scenario automatically (links to existing BOMs)
- **Backend intact:** `bulk_generation.py` kept for edge cases where PE2 file unavailable
- **Files:** `project_component_master/bulk_generation.py`, `public/js/project.js`

**Phase 2: Enhanced BOM Upload (New Project Flow)** ✅ (2026-01-27)
- New "Create BOMs with Validation" button on BOM Upload form
- Full analysis engine: parse Excel → create Items → create Component Masters → analyze → create BOMs → link back
- Hash-based change detection categorizes components as new/unchanged/changed/blocked
- Ancestor chain blocking — changed child blocks all parent assemblies
- Loose item blocking — items without `can_be_converted_to_bom` block upload
- Three dialog outcomes: blocked (red), requires resolution (orange), success (green)
- Imports existing `parse_rows`, `build_tree`, `ensure_item_exists`, `create_bom_recursive` from `bom_upload.py` (Decision 12 — no modification to existing code)
- **Files:**
  - `clevertech/doctype/bom_upload/bom_upload_enhanced.py` — Server logic (whitelisted)
  - `clevertech/doctype/bom_upload/bom_upload.js` — Button handler + 3 dialog functions
  - `clevertech/doctype/bom_upload/bom_upload.json` — Added button field

**Phase 3: Procurement Hooks** ✅ (2026-01-27)
- 8 event hooks: on_submit and on_cancel for Material Request, RFQ, Purchase Order, Purchase Receipt
- Automatically adds/removes rows in Component Procurement Record child table
- Tracks: document_type, document_name, quantity, rate, amount, date, status, procurement_source
- Silent skip pattern — only processes items with an existing Component Master
- Idempotent — duplicate records checked before inserting
- Supplier Quotations NOT tracked (use separate comparison report per design)
- **File:** `project_component_master/procurement_hooks.py`

**Phase 3A: Material Request & Purchase Order Quantity Validation** ✅ (2026-01-27)
*(RFQ validation added later in Phase 4D)*

**Material Request Validation:**
- Validate hook on Material Request — checks qty against `total_qty_limit`
- Hard block (frappe.throw) if cumulative MR qty would exceed limit
- Runs on `validate` event (triggers on every save, including draft - perfect for workflow scenarios)
- Calculates existing MR qty across all non-cancelled MRs for the project+item
- Example: If limit=100, existing MRs=90, current MR=11 → blocks (90+11=101 > 100, max allowed=10)
- Warning for loose item over-procurement (loose qty > BOM qty)
- Clear error table: total limit, existing MRs, this MR, max allowed
- **File:** `project_component_master/material_request_validation.py`

**Purchase Order Validation:**
- Validate hook on Purchase Order — checks qty against `total_qty_limit` (defense in depth)
- Hard block (frappe.throw) if cumulative PO qty would exceed limit
- Runs on `validate` event (triggers on every save, including draft)
- Calculates existing PO qty across all non-cancelled POs for the project+item
- Catches cases where: POs created without MRs, PO qtys manually edited, multiple POs exceed limit
- Info message for loose items with manual project_qty override
- Clear error table: total limit, existing POs, this PO, max allowed
- **File:** `project_component_master/purchase_order_validation.py`

**Validation Workflow:**
```
User creates MR/PO (Draft) → enters qty → clicks Save
  ↓
validate event fires HERE ← blocks if qty exceeds limit (BEFORE workflow starts)
  ↓
Document saved as Draft → approval workflow starts → final submit
```

**Phase 4: Auto-Calculations** ✅ (2026-01-27)
- `before_save()` in ProjectComponentMaster class runs 6 auto-calculations:
  - `calculate_bom_qty_required()` — initially had bug (summed qty_per_unit without multiplication) — **FIXED in Phase 4B**
  - `calculate_total_qty_limit()` — initially MAX(loose_qty, bom_qty) — **SIMPLIFIED in Phase 4B to MAX(project_qty, bom_qty)**
  - `calculate_procurement_totals()` — sums MR + PO quantities from procurement records
  - `update_procurement_status()` — Not Started / In Progress / Completed / Over-procured
  - `calculate_budgeted_rate_rollup()` — child component budgets + leaf item last purchase rates
  - `update_bom_conversion_status()` — Not Applicable / Pending / Converted / Partial
- **File:** `clevertech/doctype/project_component_master/project_component_master.py`

**Phase 4B: Project Quantity Multiplication & Simplified Design** ✅ (2026-01-27)
- **Problem fixed:** `bom_qty_required` now correctly multiplies `qty_per_unit × parent.project_qty`
- **Added 2 new fields:**
  - `project_qty` (Float) — always manual, read-only for BOM Upload source (data integrity)
  - `created_from` (Select) — tracks source: BOM Upload / Cutover / Manual Entry
- **Simplified design (from discussion):**
  - ✅ `project_qty` = ALWAYS manual (never auto-calculated)
  - ✅ `bom_qty_required` = ALWAYS auto-calculated
  - ✅ `total_qty_limit = MAX(project_qty, bom_qty_required)` (simplified from Decision 5)
  - ❌ Removed `calculate_project_qty()` method entirely (not needed!)
- **Fixed calculation:**
  - `calculate_bom_qty_required()` multiplies `qty_per_unit × parent_project_qty`
  - Populates `total_qty_required` on each BOM Usage row
  - Handles root assemblies, loose items (4 statuses), and multi-BOM usage (SUM approach)
- **Data flows:**
  - BOM Upload: sets `project_qty` from Excel column E, makes it read-only
  - Cutover: defaults `project_qty = 1`, user reviews and updates
  - Manual Entry: user sets everything, fully editable
- **Data integrity:** `project_qty` read-only when `created_from = "BOM Upload"` (forces PE2 → re-upload workflow)
- **Files modified:**
  - `project_component_master.json` — added fields, updated descriptions
  - `project_component_master.py` — fixed calculation, removed auto-calc, simplified limit
  - `bom_upload_enhanced.py` — sets project_qty and created_from
  - `bulk_generation.py` — sets defaults and warnings for cutover
- **See Decision 13 for complete design rationale and examples**

**Phase 4A: Hooks Registration** ✅ (2026-01-27)
- All new hooks registered in hooks.py using list syntax where events have existing handlers
- Purchase Receipt on_submit: existing QI handler + new procurement hook (list)
- Material Request validate: existing stock validation + new qty limit check (list)
- New on_submit/on_cancel events added for PO, RFQ
- **File:** `hooks.py`

**Phase 4C: Make/Buy Flag & Component Masters for ALL Items** ✅ (2026-01-28)
- **New field:** `make_or_buy` (Select: Make/Buy) on Component Master
  - Editable on form anytime (supports mid-project changes)
  - Cascade recalculation: changing parent's make/buy recalculates all children's bom_qty_required
  - Uses `on_update` hook to cascade after save completes
- **Component Master scope expanded:** Now created for ALL items (assemblies + raw materials)
  - BOM Upload modified to create Component Masters for leaf items (RMs) too
  - RMs: has_bom=0, make_or_buy=Buy
  - `_get_all_nodes()` replaces `_get_assembly_nodes()` for CM creation
  - `ensure_items_for_all_nodes()` ensures Items exist for leaf items before CM creation
- **BOM Upload make/buy merge:** Excel value wins if present, else keep existing value
  - `_merge_make_or_buy()` function handles merge logic
  - PE2 team only tags new items or changes; previously tagged items left blank
  - Defaults: assemblies=Make, raw materials=Buy
- **Updated calculations:**
  - `calculate_bom_qty_required()` now checks parent's `make_or_buy`
  - Only counts parents where make_or_buy="Make" (Buy parents cover their children)
  - Sets `total_qty_required = 0` on bom_usage rows for "Buy" parents
- **Updated validations:**
  - MR validation: uses `custom_project_` field, only enforces for Buy items
  - PO validation: uses `project` field, only enforces for Buy items
  - Both skip validation when `make_or_buy != "Buy"`
  - Fixed project field names per doctype (see Decision 14 table)
- **Procurement hooks updated:**
  - `_get_project_from_doc()` now handles all 3 field variants: `project`, `custom_project_`, `custom_project`
- **Cutover flow updated:**
  - `bulk_generation.py` sets `make_or_buy = "Make"` as default for assemblies
  - Warning message updated to mention Make/Buy review
- **Files modified:**
  - `project_component_master.json` — added make_or_buy field
  - `project_component_master.py` — make/buy in calculation + cascade recalc + on_update hook
  - `bom_upload_enhanced.py` — create all items + make/buy merge + ensure_items_for_all_nodes
  - `material_request_validation.py` — fixed field name to custom_project_, Buy-only check
  - `purchase_order_validation.py` — fixed field name to project, Buy-only check
  - `procurement_hooks.py` — added custom_project (no underscore) for RFQ
  - `bulk_generation.py` — make_or_buy default + updated warning
  - `hooks.py` — PO validate hook (list syntax)
- **See Decision 14 for complete design rationale**
- **See Decision 15 for why M/G levels still need Component Masters**

**Phase 4D: RFQ Validation & BOM Version Handling (Basic)** ✅ (2026-01-28)
- **RFQ Quantity Validation:**
  - Validate hook on Request for Quotation — checks qty against `total_qty_limit`
  - Hard block (frappe.throw) if cumulative RFQ qty would exceed limit
  - Uses `custom_project` field (no trailing underscore)
  - Only enforces for "Buy" items (Make items skip validation)
  - Calculates existing RFQ qty across all non-cancelled RFQs for the project+item
  - Pre-order enforcement — catches over-procurement before PO stage
  - Clear error table: total limit, existing RFQs, this RFQ, max allowed
  - **File:** `project_component_master/rfq_validation.py`
  - **Hook:** hooks.py — RFQ validate changed from string to list
- **BOM Version Change Handling (on_bom_submit) — WARNS ONLY:**
  - Detects when a different BOM was already active for the same item+project
  - Removes old BOM's bom_usage entries from ALL child Component Masters (prevents double-counting)
  - Checks for items removed in new version that have existing MRs/POs — **warns user (does not block)**
  - Notifies user of version change (blue info or orange warning based on impact)
- **BOM Version Fallback (on_bom_cancel):**
  - Instead of blindly clearing active_bom, finds another active+default BOM for same item+project
  - Fallback priority: active+default first, then any active (most recently modified)
  - Populates bom_usage entries from fallback BOM
  - Notifies user of automatic switch
  - Only clears if NO other active BOM exists
- **Files modified:**
  - `project_component_master/rfq_validation.py` — new file
  - `project_component_master/bom_hooks.py` — added `_handle_bom_version_change()`, `_find_fallback_bom()`, updated `on_bom_submit()` and `on_bom_cancel()`
  - `hooks.py` — RFQ validate changed to list with rfq_validation hook
- **Note:** This phase implements basic warning. Phase 4E adds tiered blocking during BOM Upload.

**Phase 4E: BOM Version Change — Tiered Blocking During Upload** ✅ (2026-01-30)
- **Tiered blocking based on procurement stage:**
  - No MR/RFQ/PO → Confirm dialog with remarks, auto-proceed if confirmed
  - MR exists → BLOCK, user must deactivate old BOM manually
  - RFQ exists → BLOCK, user must deactivate old BOM manually
  - PO exists → BLOCK (stricter), requires Manager role to override
- **New field:** `version_change_remarks` (Small Text, read-only) on Component Master
- **New confirm dialog:** "BOM structure changed. Proceed with new version?" with mandatory remarks
- **New block dialog:** Shows procurement documents, instructs user to deactivate old BOM
- **Manager override:** Users with "Component Master Manager" or "System Manager" role can proceed even with PO
- **Re-run workflow:** After user deactivates old BOM, re-run upload to proceed
- **Server-side functions added:**
  - `_get_material_requests()` — queries MRs for project/item
  - `_get_rfqs()` — queries RFQs for project/item
  - `_get_purchase_orders()` — queries POs for project/item
  - `_check_procurement_blocking()` — determines blocking level based on procurement stage
  - `_can_override_po_block()` — checks for Manager role
  - `confirm_version_change()` — whitelisted method to handle user confirmation with remarks
  - `_proceed_with_confirmed_changes()` — deactivates old BOMs and creates new ones
- **Client-side dialogs added:**
  - `_show_procurement_block_dialog()` — shows MR/RFQ blocks, instructs user to deactivate old BOM
  - `_show_manager_required_dialog()` — shows PO blocks when user lacks Manager role
  - `_show_confirmation_dialog()` — collects remarks for each changed component, then proceeds
- **New response statuses:** `procurement_blocked`, `manager_required`, `requires_confirmation`
- **Files modified:**
  - `bom_upload_enhanced.py` — added procurement blocking functions and tiered logic
  - `bom_upload.js` — added 3 new dialog functions for tiered blocking
  - `project_component_master.json` — added `version_change_remarks` field
- **See Decision 16 for complete design rationale**

**Phase 4F: BOM Version History Tracking** ✅ (2026-01-30)
- **New child table:** `Component BOM Version History`
  - `bom_name` (Link to BOM)
  - `version_number` (Int) — sequential 1, 2, 3...
  - `structure_hash` (Data) — hash at that version
  - `activated_on` (Datetime)
  - `deactivated_on` (Datetime)
  - `is_current` (Check)
  - `change_remarks` (Small Text)
- **New field on Procurement Record:** `bom_version` (Link to BOM)
  - Links each MR/RFQ/PO/PR to the BOM version active at time of procurement
  - Enables audit trail: "Which BOM version drove this procurement?"
- **BOM hooks updated:**
  - `_log_bom_version_change()` — logs version change to history table
  - `_add_initial_bom_version()` — adds first version when BOM first linked
  - `on_bom_submit()` now calls these functions
- **Procurement hooks updated:**
  - `_add_procurement_records()` now sets `bom_version` from `active_bom`
- **Files created:**
  - `clevertech/doctype/component_bom_version_history/` — new child table DocType
- **Files modified:**
  - `project_component_master.json` — added `bom_version_history` child table
  - `component_procurement_record.json` — added `bom_version` field
  - `project_component_master/bom_hooks.py` — version history logging
  - `project_component_master/procurement_hooks.py` — bom_version on records

**Phase 4G: Image Upload Enhancement & Comprehensive Summary** ✅ (2026-01-31)
- **Synchronized BOM Upload functions:** Ensured `create_boms_with_validation` (enhanced) matches all recent changes from `create_boms` (original)
  - **Background:** The original `create_boms()` button was recently enhanced with image upload and extended fields. The enhanced version `create_boms_with_validation()` needed synchronization to match these changes.
  - **Import changes:**
    - Added `HAS_IMAGE_LOADER` flag import from `bom_upload.py`
    - Added conditional `SheetImageLoader` import (graceful fallback if library not installed)
  - **Item creation synchronization:**
    - `ensure_items_for_all_nodes()` — updated to accept and pass `ws` and `image_loader` parameters
    - All `ensure_item_exists()` calls now pass 6 extended fields: `material`, `treatment`, `weight`, `part_number`, `manufacturer`, `revision`
    - Returns "updated" status when existing items get images added (new behavior)
  - **BOM creation synchronization:**
    - `create_boms_and_link_components()` — updated signature to accept `ws` and `image_loader`
    - `_create_bom_for_node()` — passes `ws` and `image_loader` to `create_bom_recursive()`
    - `_proceed_with_confirmed_changes()` — initializes image loader and passes through entire flow
  - **Image loader initialization:**
    - Image loader created only if `HAS_IMAGE_LOADER` flag is True and `SheetImageLoader` is available
    - Wrapped in try/except to gracefully handle failures (image upload is optional)
    - Same pattern used in both main upload path and confirmation path
- **Image update for existing items:**
  - Modified `ensure_item_exists()` in `bom_upload.py` to check if existing items lack images
  - If item exists without image and Excel has embedded image, extract and upload image to Item master
  - Returns "updated" status (new) in addition to "created", "existing", "failed"
- **Business rules for procurement defaults:**
  - All items default to `make_or_buy = "Buy"` (conservative approach — supply chain manually changes to "Make" later)
  - Items with codes starting with T, Y, or E: `released_for_procurement = "No"` (require manual release)
  - Other items: `released_for_procurement = "Yes"` (auto-released)
- **Comprehensive summary tracking:**
  - Item counters: `{"created": 0, "existing": 0, "updated": 0, "failed": 0}`
  - BOM counters: `{"created": 0, "existing": 0, "failed": 0}`
  - Component Master counters: `{"created": 0, "existing": 0, "updated": 0, "failed": 0}`
  - Summary built after upload showing detailed breakdown by category
- **JavaScript enhancement:**
  - Rewrote `_show_upload_success()` to display 3-column layout (Items | BOMs | Component Masters)
  - Color-coded table rows: green (created), gray (existing), yellow (updated), red (failed), blue (total)
  - Items section now shows "Updated" row when items had images added
- **Files modified:**
  - `bom_upload.py` — updated `ensure_item_exists()` to handle image updates, returns "updated" status
  - `bom_upload_enhanced.py` — synced signatures, added business rules, comprehensive summary building
  - `bom_upload.js` — rewrote success dialog with 3-column summary display
  - `project_component_master.json` — verified `released_for_procurement` field exists
- **Key improvement:** Users now see exactly what happened during BOM Upload:
  - How many items were created vs already existed vs updated with images
  - How many BOMs were created vs skipped
  - How many Component Masters were created vs already existed vs updated
  - Clear visibility into any failures

**Phase 4H: Dynamic Column Mapping & Excel Format Validation** ✅ (2026-02-01)

**Root Cause Analysis:**
- **Issue:** BOM-A00000006515-001 created for raw material (should not have BOM)
- **Cause:** PE2 Excel export format changed — `LivelloBom` (level) column shifted from AR to AQ
- **Impact:** Wrong hierarchy built → raw materials got children → BOMs created incorrectly
- **Details:** See "Known Issues & Root Cause Analysis" section

**Solution Implemented:**
1. **Dynamic Column Detection:**
   - Added `map_excel_columns(ws)` function — searches row 2 headers by name, not position
   - Handles both old format (LivelloBom in AR) and new format (LivelloBom in AQ)
   - Required columns defined: Item no, Description, Qty, Rev., LivelloBom, etc.

2. **Excel Format Validation:**
   - Validates ALL required columns present before processing
   - Displays clear error if any column missing:
     ```
     Excel file format validation failed. Missing required columns:
     • Field: level
       Expected header: LivelloBom

     Found headers in row 2:
       Column AR: QtaTotale  ← WRONG!
       Column AQ: LivelloBom ← Should use this!
     ```
   - Blocks upload if validation fails — prevents incorrect BOM creation

3. **Mapping Function Inheritance (Decision 12A):**
   - Import ALL mapping functions from `bom_upload.py`:
     - `normalize_material()`, `get_surface_treatment()`, `get_type_of_material()`
     - `get_item_group_and_hsn()`, `get_default_expense_account()`
   - When developer migrates to use Material Mapping/Surface Treatment Translation doctypes, enhanced code automatically inherits changes
   - Zero code duplication — single source of truth

**Column Mapping Implemented:**

| Field | Header Name | Working File | Broken File | Strategy |
|-------|-------------|--------------|-------------|----------|
| Item Code | `Item no` | Column C | Column C | ✅ Search by name |
| Description | `Description` | Column D | Column D | ✅ Search by name |
| Qty | `Qty` | Column E | Column E | ✅ Search by name |
| **Level** | **`LivelloBom`** | **Column AR** | **Column AQ** | ✅ **Search by name** |

**Files Modified:**
- `bom_upload_enhanced.py`:
  - Added `map_excel_columns(ws)` — dynamic header detection
  - Added `parse_rows_dynamic(ws)` — replacement for hardcoded `parse_rows()`
  - Updated imports to include all mapping/utility functions from `bom_upload.py`
  - Updated `create_boms_with_validation()` to use `parse_rows_dynamic()`
- `clevertech_context.md`:
  - Added "Known Issues & Root Cause Analysis" section
  - Added "Decision 12A: Mapping Function Inheritance Strategy"
  - Updated document version to 2.6

**Benefits:**
- ✅ Handles PE2 export format changes automatically
- ✅ Clear error messages when Excel format is invalid
- ✅ Prevents incorrect BOM creation due to column shifts
- ✅ Future-proof: auto-inherits doctype migration when developer completes it
- ✅ Zero code duplication with original `bom_upload.py`

**Resolution:** Excel format issue resolved. Enhanced upload now handles both old and new formats dynamically.

---

**Phase 4I: BOM Version Change — Path 2 Blocking & Procurement Snapshot** ✅ (2026-02-02)

**Problem Identified:**
- **Path 1 (BOM Upload):** Has tiered blocking via `_check_procurement_blocking()` ✅
- **Path 2 (Direct BOM Submit):** Only warned via `_handle_bom_version_change()`, no blocking ❌
- **Missing:** When user submits BOM directly (not via upload), version change wasn't blocked even with active procurement
- **Data Loss:** Old bom_usage entries were deleted without preserving the procurement data (MR/RFQ/PO refs and quantities)

**Solution Implemented:**

**1. On-BOM-Validate Hook (Tiered Blocking for Path 2):**
- Added `on_bom_validate()` hook — runs BEFORE BOM submission
- Detects BOM version change (different BOM already active for same item+project)
- Checks if old BOM is still active (`is_active = 1`)
- If old BOM active AND has child items with procurement → **BLOCKS submission**
- Clear error message guides user to deactivate old BOM first:
  ```
  Cannot submit new BOM version while old BOM is active.

  Another BOM (BOM-001) is currently active for item A00000001 in project PRJ001.

  Reason: The following child items have active procurement documents:
  • A00000002: Material Request MR-001, Purchase Order PO-001
  • A00000003: Request for Quotation RFQ-001

  To proceed:
  1. Open the old BOM: BOM-001
  2. Uncheck the 'Is Active' flag
  3. Save the old BOM
  4. Then submit this new BOM
  ```
- Uses "Uncheck Is Active" approach (non-destructive, can be reactivated)

**2. Procurement Snapshot at Version Deactivation:**
- Added `procurement_snapshot` field (JSON) to `Component BOM Version History` doctype
- When old BOM version is deactivated, captures complete procurement state:
  ```json
  {
    "snapshot_time": "2026-02-02 10:30:00",
    "bom_name": "BOM-001",
    "child_items": [
      {
        "item_code": "A00001",
        "qty_per_unit": 2.0,
        "bom_qty_required": 4.0,
        "total_qty_limit": 4.0,
        "mr_refs": ["MR-001", "MR-002"],
        "mr_total_qty": 3.0,
        "rfq_refs": ["RFQ-001"],
        "rfq_total_qty": 2.0,
        "po_refs": ["PO-001"],
        "po_total_qty": 2.0,
        "pr_refs": ["PR-001"],
        "received_qty": 1.0
      }
    ]
  }
  ```
- Preserves audit trail: "What was procured against which BOM version?"
- Enables reconciliation when BOM changes mid-procurement

**3. Enhanced Version Change Alerts:**
- Now detects TWO types of issues (not just removed items):
  - **Items REMOVED from BOM:** With existing MR/RFQ/PO
  - **Items with QTY REDUCED:** Where procured qty exceeds new requirement (over-procurement)
- Combined alert shown in red with clear breakdown:
  ```
  BOM version changed from BOM-001 to BOM-002 for item A00000001.

  🔴 REVIEW REQUIRED:

  ⚠️ Items REMOVED from BOM (have existing procurement):
  • A00002 (1 MR(s), 0 PO(s))

  ⚠️ Items with QTY REDUCED (over-procurement detected):
  • A00003: BOM qty 2 → 1 (requirement 4 → 2). Procured: 3. OVER by 1

  Procurement snapshot saved in BOM Version History for audit.
  Please review and adjust these procurement documents.
  ```

**User Workflow (Path 2 — Direct BOM Submission):**
1. User tries to submit new BOM → **BLOCKED** by `on_bom_validate` (old BOM still active with procurement)
2. Error message tells user to uncheck `is_active` on old BOM
3. User opens old BOM → Unchecks "Is Active" → Saves
4. User submits new BOM → `on_bom_validate` passes (old BOM not active)
5. `on_bom_submit` runs:
   - Logs version change to history (with procurement snapshot on old version)
   - Removes old bom_usage entries
   - Creates new bom_usage entries
   - Shows alert if items removed or qty reduced with over-procurement

**Files Modified:**
- `clevertech/doctype/component_bom_version_history/component_bom_version_history.json`:
  - Added `section_break_procurement` (collapsible section)
  - Added `procurement_snapshot` (JSON field)
- `project_component_master/bom_hooks.py`:
  - Added `on_bom_validate()` — tiered blocking for direct BOM submission
  - Added `_check_bom_version_blocking()` — checks child items for MR/RFQ/PO
  - Added `_capture_procurement_snapshot()` — captures complete procurement state
  - Added `_get_material_requests()`, `_get_rfqs()`, `_get_purchase_orders()` — query helpers
  - Updated `_log_bom_version_change()` — now captures snapshot before deactivation
  - Updated `_handle_bom_version_change()` — now detects qty reduction and over-procurement
- `hooks.py`:
  - Added BOM `validate` hook pointing to `on_bom_validate`

**Key Benefits:**
- ✅ Path 2 (direct submit) now has same blocking as Path 1 (upload)
- ✅ Procurement data preserved in version history for audit
- ✅ Over-procurement detected when BOM qty reduces
- ✅ Non-destructive "Uncheck Is Active" workflow
- ✅ Clear user guidance on how to proceed

---

**Phase 4J: BOM Version Tracking Bugs & Fixes** ✅ (2026-02-03)

**Problems Identified During Testing:**

During testing of BOM version change functionality (Phase 4F-4I), two critical bugs were discovered:

**Bug #1: Procurement Records Missing BOM Version**
```
Symptom:
- Component Procurement Record has `bom_version` field
- Field was NULL for all procurement records
- Unable to track which BOM version procurement was created for

Root Cause:
- For child items (raw materials, has_bom=0), procurement hook captured `cm.active_bom`
- But child items don't have their own BOM, so active_bom is always NULL
- Should have captured PARENT assembly's active_bom instead

Impact:
- Lost audit trail: can't reconcile procurement to specific BOM versions
- Multi-BOM scenario: child used in multiple parent BOMs, can't tell which one
```

**Bug #2: BOM Version History Missing Old Versions**
```
Symptom:
- Parent Component Master shows only BOM-003 as "version 1"
- But 3 BOMs exist: BOM-001, BOM-002, BOM-003
- Expected: All 3 BOMs in version history as v1, v2, v3

Root Cause:
Timeline:
  1. BOM-001 created (2026-02-02 19:10) → Component Master didn't exist yet
  2. BOM-002 created (2026-02-02 21:33) → Component Master didn't exist yet
  3. Component Master created (2026-02-02 23:30) via BOM Upload
  4. BOM-003 created (2026-02-03 12:01) → Component Master exists now
     → on_bom_submit() checks: active_bom is empty
     → Calls _add_initial_bom_version(BOM-003) → treats as version 1!

Old BOMs were created BEFORE Component Master existed, so they were never tracked.
```

**Solutions Implemented:**

**Fix #1: Procurement BOM Version Tracking**

1. **Added `custom_procurement_bom` field to Material Request:**
   - Link field to BOM doctype
   - Populated when user clicks "Get Items from BOM"
   - Stores exact BOM used for procurement (accurate!)

2. **Updated procurement hook logic** (`procurement_hooks.py`):
```python
# Priority:
# 1. If MR has custom_procurement_bom set, use that (accurate)
# 2. Otherwise, infer from current active parent BOM (fallback)

bom_version = None
if doc.get("custom_procurement_bom"):
    bom_version = doc.custom_procurement_bom  # From MR field
else:
    bom_version = _get_bom_version_for_procurement(cm, project)  # Infer from bom_usage
```

3. **Added `_get_bom_version_for_procurement()` helper:**
   - For assemblies: returns their own `active_bom`
   - For raw materials: looks up parent BOM from `bom_usage` table
   - If multiple parents: returns most recently modified active parent BOM

4. **Updated `material_request.js`:**
```javascript
// In get_items_from_bom callback:
frm.set_value('custom_procurement_bom', values.bom);
```

**Fix #2: BOM Version History Backfilling**

1. **Added automatic backfill** in `on_bom_submit()`:
```python
# Before version change detection:
if not component_master.bom_version_history:
    _backfill_bom_version_history(doc.project, doc.item, doc.name)
    component_master = get_component_master(doc.project, doc.item)  # Reload
```

2. **Implemented `_backfill_bom_version_history()`:**
   - Finds all submitted BOMs for the item (ordered by creation)
   - Filters out BOMs already in version history
   - Adds missing BOMs with proper version numbers
   - Sets `is_current=1` for the most recent BOM
   - Uses next BOM's creation date as deactivation date

3. **Created `fix_bom_version_history()` utility** for manual fixes:
   - Rebuilds version history from scratch
   - Clears existing entries and re-adds all BOMs in chronological order
   - Fixes version numbers and deactivation dates
   - Useful for historical data cleanup

**Design Decisions & Trade-offs:**

**Decision 1: Don't Repurpose `custom_bom_id` Field**
- Existing field stores item code (used for material transfer)
- Different purpose than BOM version tracking
- Created new field `custom_procurement_bom` instead

**Decision 2: Multi-BOM Problem**
- Child items can be used in multiple parent BOMs
- One MR can have items from multiple BOMs
- `bom_version` field can only store one value
- **Accepted limitation:** Use most recently modified active parent BOM
- **Future enhancement:** Could add BOM version per MR Item (child table)

**Decision 3: Historical Data Handling**
- Can't reliably determine which BOM was used for old MRs
- MR doesn't store BOM reference (except via new field)
- **Options considered:**
  - Date-based lookup (inaccurate: MR might be created weeks after design)
  - Leave as NULL (honest: we don't know)
  - Use current active BOM (approximation)
- **Chosen:** Utility function uses current active BOM with disclaimer
- **Recommended:** Leave historical data as NULL if accuracy is critical

**Files Modified:**

**1. Database Schema:**
- Added `custom_procurement_bom` field to Material Request (Link → BOM)

**2. Backend:**
- `clevertech/project_component_master/bom_hooks.py`:
  - Added `_backfill_bom_version_history()` — automatic backfill on BOM submit
  - Added `fix_bom_version_history()` — utility for manual cleanup (whitelisted)
  - Added `fix_procurement_bom_versions()` — utility for backfilling procurement records (whitelisted)

- `clevertech/project_component_master/procurement_hooks.py`:
  - Updated `_add_procurement_records()` — checks `custom_procurement_bom` first
  - Added `_get_bom_version_for_procurement()` — infers parent BOM for child items

**3. Frontend:**
- `clevertech/public/js/material_request.js`:
  - Updated `get_items_from_bom()` callback — populates `custom_procurement_bom`

**Test Results:**

**Parent Component Master (PCM-SMR260002-001666):**
```
Before:
  bom_version_history: [BOM-003 (version 1)]  ❌

After (ran fix_bom_version_history):
  bom_version_history:
    - BOM-001 (v1, activated: 2026-02-02 19:10, deactivated: 21:33)
    - BOM-002 (v2, activated: 2026-02-02 21:33, deactivated: 2026-02-03 12:01)
    - BOM-003 (v3, activated: 2026-02-03 12:01, is_current=1)  ✅
```

**Child Component Master (PCM-SMR260002-001667):**
```
Before:
  procurement_records:
    - MR-017: bom_version = NULL  ❌
    - MR-020: bom_version = NULL  ❌

After (ran fix_procurement_bom_versions):
  procurement_records:
    - MR-017: bom_version = BOM-D00000084229-003  ✅ (current active parent BOM)
    - MR-020: bom_version = BOM-D00000084229-003  ✅
```

**Key Benefits:**

**Automated (Going Forward):**
- ✅ New BOM uploads auto-detect and backfill missing version history
- ✅ New MRs from "Get Items from BOM" store exact BOM used
- ✅ Procurement records automatically get correct BOM version
- ✅ Accurate audit trail for BOM → Procurement linkage

**Manual Utilities (For Historical Data):**
- ✅ `fix_bom_version_history(component_master_name)` — rebuild version history
- ✅ `fix_procurement_bom_versions(component_master_name)` — backfill bom_version field
- ✅ Both are whitelisted for API/console access

**Limitations & Future Enhancements:**

**Current Limitations:**
1. Historical MRs don't have `custom_procurement_bom` populated (field didn't exist)
2. Utility function uses current active parent BOM (may not be historically accurate)
3. Multi-BOM scenario: child in multiple BOMs, can only store one bom_version

**Future Enhancements:**
1. Add `custom_procurement_bom` to Material Request Item child table (per-item BOM tracking)
2. Add BOM version field to RFQ Item, PO Item, PR Item for complete traceability
3. Historical BOM version lookup based on procurement dates + bom_version_history timeline
4. Procurement reconciliation report: "Show procurement per BOM version"

**Usage Guide:**

**For New Procurement:**
```
User workflow:
1. Open Material Request
2. Click "Get Items From" → "Bill of Materials"
3. Select BOM (e.g., BOM-Parent-003)
4. Click "Get Items"
   → custom_procurement_bom auto-populated with BOM-Parent-003 ✓
5. Submit MR
   → procurement_records.bom_version = BOM-Parent-003 ✓
```

**For Historical Data Cleanup:**
```python
# Fix parent's version history:
from clevertech.project_component_master.bom_hooks import fix_bom_version_history
result = fix_bom_version_history("PCM-SMR260002-001666")

# Fix child's procurement bom_version:
from clevertech.project_component_master.bom_hooks import fix_procurement_bom_versions
result = fix_procurement_bom_versions("PCM-SMR260002-001667")
```

**Bulk Fix (All Component Masters in Project):**
```python
import frappe

project = "SMR260002"
cms = frappe.get_all("Project Component Master",
    filters={"project": project},
    pluck="name"
)

for cm_name in cms:
    # Fix version history for assemblies
    cm = frappe.get_doc("Project Component Master", cm_name)
    if cm.has_bom:
        from clevertech.project_component_master.bom_hooks import fix_bom_version_history
        fix_bom_version_history(cm_name)

    # Fix procurement records for all items
    from clevertech.project_component_master.bom_hooks import fix_procurement_bom_versions
    fix_procurement_bom_versions(cm_name)

frappe.db.commit()
```

---

**Phase 5: Project Tracking Report** ✅ (Implemented - 2026-02-03)

**Report Overview:**
- **Purpose:** Track procurement lifecycle for all procurable items across projects
- **Data Source:** Project Component Master + Component Procurement Records + linked documents
- **Structure:** Flat table (no tree hierarchy) with toggleable column sections
- **Total Columns:** 61 columns across 8 sections
- **Reference:** `/home/bharatbodh/bharatbodh-bench/sites/clevertech-uat.bharatbodh.com/public/files/Project Tracking.xlsx`
- **BOM Structure Reference:** `/files/clevertech_bom_comparison.pdf`

---

### Item Code Structure (from BOM Comparison PDF)

| Code | Description | Procurement | Report Inclusion |
|------|-------------|-------------|------------------|
| V/P | Machine/Project (linked to WBS) | Make (assembled) | ❌ Exclude |
| M | MEC element (Modules) | Make (assembled) | ❌ Exclude |
| G | Groups/Assemblies | Make (assembled) | ❌ Exclude |
| D/IM | Drawing items under G | Make OR Buy | ✅ If make_or_buy="Buy" |
| A | Commercial mechanical | Buy (procured) | ✅ Include |
| E | Electrical commercial | Buy (procured) | ✅ Include |
| U | Commercial pneumatic | Buy (procured) | ✅ Include |
| L | Commercial lubrication | Buy (procured) | ✅ Include |
| I | Commercial hydraulic | Buy (procured) | ✅ Include |
| Y | Raw materials | Buy (procured) | ✅ Include |
| Z | Robot/3rd-party machines | Buy (procured) | ✅ Include |

**Report Inclusion Criteria:**
```python
# ONLY show items where:
item_code.startswith(('A', 'E', 'U', 'L', 'I', 'Y', 'Z'))
OR (item_code.startswith(('D', 'IM')) AND make_or_buy == "Buy")

# EXCLUDE:
# - V, P, M, G codes (always assembled in-house)
# - D/IM codes where make_or_buy == "Make"
```

---

### Column Sections (61 Total)

#### **Section 1: Default Visible (11 columns)** - Always shown

| # | Column | Data Source | Field/Logic |
|---|--------|-------------|-------------|
| 1 | Project No | Project Component Master | `project` |
| 2 | Machine Code | Project Component Master | `machine_code` **(NEW FIELD)** |
| 3 | WBS Code | Project Component Master | `cost_center` name **(NEW FIELD - Link to Cost Center)** |
| 4 | M-Code | Hierarchy Traversal | Traverse `parent_component` up, find item starting with "M" |
| 5 | G-Code | Hierarchy Traversal | Traverse `parent_component` up, find item starting with "G" |
| 6 | Image | Project Component Master | `component_image` |
| 7 | Item No | Project Component Master | `item_code` |
| 8 | Item Name | Project Component Master | `item_name` |
| 9 | Description | Project Component Master | `description` |
| 10 | QTY | Project Component Master | `total_qty_limit` |
| 11 | UOM | Item Master | `stock_uom` |

**UI Enhancement:** Blank consecutive duplicate values for columns 1-5 (Project/Machine/WBS/M-Code/G-Code) when same as previous row

---

#### **Section 2: BOM Data (8 columns)** - Toggle: `show_bom_data`

| # | Column | Data Source | Field Name |
|---|--------|-------------|------------|
| 12 | REV | Item Master | `custom_revision_no` |
| 13 | Material | Item Master | `custom_material` |
| 14 | Part Number | Item Master | `custom_excode` |
| 15 | Manufacturer | Item Master | `custom_item_short_description` |
| 16 | Weight (KG) | Item Master | `custom_last_updating_of` |
| 17 | Surface Treatment | Item Master | `custom_class_name` |
| 18 | Type of Material | Item Master | `custom_type_of_material` |
| 19 | Quality Required | Item Master | `inspection_required_before_purchase` (checkbox) |

---

#### **Section 3: Budget vs Actual (3 columns)** - Toggle: `show_budget`

| # | Column | Data Source | Calculation |
|---|--------|-------------|-------------|
| 20 | Budget Amount | Project Component Master | `budgeted_rate * total_qty_limit` |
| 21 | Actual Amount | Component Procurement Record | `SUM(amount)` where `document_type = "Purchase Order"` |
| 22 | Balance Budget | Calculated | Budget Amount - Actual Amount |

---

#### **Section 4: Material Request (4 columns)** - Toggle: `show_mr`

| # | Column | Data Source | Logic |
|---|--------|-------------|-------|
| 23 | Material Request No | Component Procurement Record | `document_name` where `document_type = "Material Request"` (comma-separated if multiple) |
| 24 | Material Request Qty | Component Procurement Record | `SUM(quantity)` for all MRs |
| 25 | ETA | Material Request Item | `schedule_date` from latest MR |
| 26 | Qty Pending for MR | Calculated | `total_qty_limit - material_request_qty` |

---

#### **Section 5: RFQ & Supplier Quotation (22 columns)** - Toggle: `show_rfq`

**Design Decision:** Fixed maximum of 4 vendors, hide empty columns in UI if fewer quotations exist

**Vendor Columns (16 columns = 4 vendors × 4 fields):**

| # | Column Pattern | Data Source | Logic |
|---|----------------|-------------|-------|
| 27-30 | Vendor 1: Name, RFQ Status, Rate, Total | Supplier Quotation | First quotation sorted by `creation` |
| 31-34 | Vendor 2: Name, RFQ Status, Rate, Total | Supplier Quotation | Second quotation |
| 35-38 | Vendor 3: Name, RFQ Status, Rate, Total | Supplier Quotation | Third quotation |
| 39-42 | Vendor 4: Name, RFQ Status, Rate, Total | Supplier Quotation | Fourth quotation |

- **Name:** `supplier` from Supplier Quotation
- **RFQ Status:** `status` from linked Request for Quotation
- **Rate:** `rate` from Supplier Quotation Item
- **Total:** `amount` from Supplier Quotation Item

**Comparison Columns (6 columns):**

| # | Column | Logic |
|---|--------|-------|
| 43 | Lowest Bid Vendor | Supplier with `MIN(rate)` from all quotations |
| 44 | Lowest Bid Rate | `MIN(rate)` |
| 45 | Lowest Bid Total | `amount` corresponding to lowest rate |
| 46 | Decided Vendor | `supplier` from Purchase Order (final selection) |
| 47 | Decided Rate | `rate` from Purchase Order Item |
| 48 | Decided Total | `amount` from Purchase Order Item |

---

#### **Section 6: Purchase Order & Delivery (9 columns)** - Toggle: `show_po`

| # | Column | Data Source | Logic |
|---|--------|-------------|-------|
| 49 | PO Number | Component Procurement Record | `document_name` where `document_type = "Purchase Order"` |
| 50 | PO Date | Purchase Order | `transaction_date` |
| 51 | PO Qty | Component Procurement Record | `SUM(quantity)` for all POs |
| 52 | Qty Pending for PO | Calculated | `total_qty_limit - po_qty` |
| 53 | GRN No | Component Procurement Record | `document_name` where `document_type = "Purchase Receipt"` |
| 54 | Delivery Qty | Component Procurement Record | `SUM(quantity)` for all PRs |
| 55 | Delivery Date | Purchase Receipt | `posting_date` from latest PR |
| 56 | Pending Delivery Qty | Calculated | `po_qty - delivery_qty` |
| 57 | Delivery Status | Calculated | "Pending" / "Partial" / "Completed" based on delivery_qty vs po_qty |

---

#### **Section 7: Quality Status (2 columns)** - Toggle: `show_quality`

| # | Column | Data Source | Logic |
|---|--------|-------------|-------|
| 58 | Quality Accepted Qty | Quality Inspection | `SUM(sample_size)` where `status = "Accepted"` and linked to item |
| 59 | Quality Rejected Qty | Quality Inspection | `SUM(sample_size)` where `status = "Rejected"` and linked to item |

---

#### **Section 8: Production (2 columns)** - Toggle: `show_production`

| # | Column | Data Source | Logic |
|---|--------|-------------|-------|
| 60 | Material in Project Warehouse | Stock Ledger Entry | `SUM(actual_qty)` in project-specific warehouse |
| 61 | Pending Material to Issue | Material Request | `SUM(qty)` where `material_request_type = "Material Issue"` and `docstatus = 1` and not fully issued |

---

### Design Decisions

**Decision 13: Flat Table Structure (2026-02-01)**

**Context:** Original spec mentioned "tree structure" but procurement tracking is item-centric, not hierarchy-focused.

**Decision:** Use flat table with M-Code and G-Code as **columns** (not tree levels)

**Rationale:**
1. **Procurement Focus:** Report tracks individual procurable items (A, E, U, L, I, Y, Z, D codes)
2. **M and G Always Make:** Since M-codes and G-codes are always assembled in-house, they never have procurement records
3. **Column Grouping:** M-Code and G-Code columns show parent context without needing tree expansion
4. **Simpler Queries:** Flat structure avoids complex recursive hierarchy queries
5. **Better Performance:** Single-level query with JOIN vs. tree building

**Implementation:**
- Each row = one procurable item (leaf node in BOM)
- M-Code column = traverse up `parent_component` chain to find item starting with "M"
- G-Code column = traverse up `parent_component` chain to find item starting with "G"

---

**Decision 14: Machine Code and WBS Code Storage (2026-02-01)**

**Problem:** Machine Code (P-code from Excel top) and WBS Code (Cost Center) needed in report but not stored in Component Master

**Solution:**
1. **Add `machine_code` field** to Project Component Master
   - Type: Data
   - Populated during BOM Upload from Excel header (e.g., "Item no:P0000000003033")
   - Stored at all hierarchy levels (inherited from parent during upload)

2. **Add `cost_center` field** to Project Component Master
   - Type: Link to Cost Center
   - Populated based on `project + machine_code` lookup
   - Enables direct WBS Code display without traversal

3. **Update Cost Center doctype** to include `machine_code` field
   - Enables mapping: `(project, machine_code) → cost_center`
   - Supports multi-machine projects (1 project = multiple cost centers)

**Rationale:**
- Denormalized storage improves report performance (no hierarchy traversal for every row)
- BOM Upload already processes hierarchy — natural place to populate these fields
- Cost Center mapping supports business model: 1 project with 4 machines = 4 cost centers

---

**Decision 15: RFQ Vendor Column Strategy (2026-02-01)**

**Problem:** Variable number of quotations per item (could be 0 to 10+)

**Options Considered:**
- **A:** Dynamic columns (show only as many as max quotations across all items)
- **B:** Fixed maximum with empty column hiding
- **C:** Single "Vendors" column with formatted text

**Decision:** Fixed maximum of 4 vendors, hide empty columns in UI

**Rationale:**
1. **UI Simplicity:** Fixed columns easier to implement in Frappe report format
2. **Business Context:** Typical procurement process involves 3-4 quotations
3. **Performance:** Pre-defined columns avoid runtime column generation
4. **Comparison:** 4 vendors provide sufficient comparison data
5. **Overflow Handling:** If >4 quotations exist, show first 4 by date/rate

**Implementation:**
- Python: Always generate 16 vendor columns (4 vendors × 4 fields)
- JavaScript: Use `formatter` to hide columns where all rows are empty
- Sort quotations by: lowest rate first (prioritize competitive quotes)

---

**Decision 16: Separate Component Masters per Machine (2026-02-01)**

**Context:** Projects have multiple machines, each with independent BOM release and procurement timeline.

**Question:** Should same item used in multiple machines have:
- **Option A:** One shared Component Master (project + item_code unique)
- **Option B:** Separate Component Masters per machine (project + item_code + machine_code unique)

**Decision:** **Option B - Separate Component Masters per machine**

**Business Rationale:**

1. **Phase-wise BOM Release:**
   - Machine 1 BOM released Week 1 → Procurement starts immediately
   - Machine 2 BOM released Week 4 → Independent procurement cycle
   - Machine 3 BOM released Week 8 → Separate timeline
   - Each upload creates separate Component Masters scoped to machine_code

2. **Machine-Specific Procurement:**
   - Material Request: "10 bearings for Machine P0003033" (clear, specific)
   - Purchase Order: Linked to specific machine's Component Master
   - Delivery tracking: Per-machine delivery schedules
   - Cost Center: Each machine has its own WBS/Cost Center

3. **Delay Visibility:**
   - "Machine 1 is 80% complete, Machine 2 is 40%" (critical for customer communication)
   - Supplier delay impacts specific machines, not entire project
   - Report shows: Which machines are on track, which are delayed

4. **Budget Control:**
   - Each machine has separate budget allocation
   - Cost tracking per machine via Cost Center (WBS code)
   - Budget reports: "Machine 1: $95K/$120K, Machine 2: $120K/$150K"

5. **Change Isolation:**
   - Design change to Machine 2 doesn't affect Machine 1's data
   - BOM versions are machine-specific
   - Procurement records are machine-specific

**Data Model Impact:**

```python
# Example: Item A00001 (Bearing) used in 2 machines

Component Master 1:
- Name: PCM-PRJ001-000001
- project: PRJ001
- item_code: A00001
- machine_code: P0003033
- parent_component: PCM-PRJ001-000010 (M00001 under Machine 1)
- total_qty_limit: 10
- procurement_records: [MR-001, PO-001, PR-001]

Component Master 2:
- Name: PCM-PRJ001-000025
- project: PRJ001
- item_code: A00001  (SAME ITEM)
- machine_code: P0003034
- parent_component: PCM-PRJ001-000030 (M00002 under Machine 2)
- total_qty_limit: 15
- procurement_records: [MR-002, PO-002, PR-002]

# Total project requirement for A00001 = 10 + 15 = 25 (aggregated in reports)
```

**Uniqueness Constraint:** `(project, item_code, machine_code)` must be unique
- Allows same item in multiple machines
- Prevents duplicate Component Masters for same machine

**Reporting Impact:**

*Machine-Level View (Primary):*
```sql
-- Show procurement for Machine P0003033
SELECT machine_code, item_code, total_qty_limit, procurement_status
FROM `tabProject Component Master`
WHERE project = 'PRJ001' AND machine_code = 'P0003033'
```

*Project-Level Rollup (Aggregate):*
```sql
-- Show total project requirement by item
SELECT item_code, SUM(total_qty_limit) AS total_qty
FROM `tabProject Component Master`
WHERE project = 'PRJ001'
GROUP BY item_code
```

**Implementation Requirements:**

1. **BOM Upload Enhancement:**
   - Add `machine_code` field to BOM Upload doctype form (✅ DONE)
   - Read machine_code from form during upload
   - Populate machine_code on ALL Component Masters created in that upload
   - Duplicate check: `(project, item_code, machine_code)` instead of `(project, item_code)`

2. **Cutover/Retroactive Fix (Project Button):**
   - User manually enters machine_code on ROOT Component Masters
   - Button on Project form: "Update Component Data"
   - Cascades machine_code from roots to all children (traverse parent_component chain)
   - Rebuilds BOM Usage tables (calls `populate_bom_usage_tables()`)

**Edge Cases Handled:**

- **Bulk Vendor Negotiation:** PO for 25 total, split across 2 Component Masters (10+15)
- **Partial Delivery:** Track delivery qty per Component Master (Machine 1: complete, Machine 2: partial)
- **Different Specs:** A00001 Rev.02 for Machine 1, A00001 Rev.03 for Machine 2 (separate Component Masters)
- **Shared Components:** If same item appears in multiple BOMs within same machine, only ONE Component Master (machine_code prevents duplication)

**Why NOT Shared Component Master:**

*Option A Rejected (Single Component Master per item):*
- ❌ Loses per-machine procurement granularity
- ❌ Can't answer: "Which machines are delayed?"
- ❌ Complex child table needed for machine-wise tracking
- ❌ Material Request would need to specify which machine(s)
- ❌ Doesn't align with phase-wise BOM release workflow
- ❌ Budget tracking becomes ambiguous

**Trade-offs Accepted:**

- ✅ More Component Master records (acceptable - modern DB performance)
- ✅ Aggregation needed for project totals (simple GROUP BY query)
- ✅ Easier to aggregate from separate → combined than to disaggregate combined → separate

---

### Prerequisites for Implementation

**1. Project Component Master - New Fields:**
```python
# Field: machine_code
{
    "fieldname": "machine_code",
    "fieldtype": "Data",
    "label": "Machine Code",
    "description": "Machine/P-code from BOM Excel header (e.g., P0000000003033)"
}

# Field: cost_center
{
    "fieldname": "cost_center",
    "fieldtype": "Link",
    "options": "Cost Center",
    "label": "Cost Center (WBS Code)",
    "description": "WBS Code for procurement tracking"
}
```

**2. Cost Center Doctype - New Field:**
```python
# Field: machine_code
{
    "fieldname": "machine_code",
    "fieldtype": "Data",
    "label": "Machine Code",
    "description": "Links to Project Component Master machine_code for WBS mapping"
}
```

**3. BOM Upload Doctype - New Field:**
```python
# Field: machine_code (added to BOM Upload form)
{
    "fieldname": "machine_code",
    "fieldtype": "Data",
    "label": "Machine Code",
    "description": "Enter machine code for this BOM (e.g., P0000000003033)",
    "reqd": 1  # Required for new uploads
}
```

---

### Implementation Plan

**Status:** ✅ Fields added to Project Component Master and BOM Upload
**Next:** Implement machine_code population logic

#### **Case 1: New BOM Uploads (bom_upload_enhanced.py)**

**Purpose:** Auto-populate machine_code for all Component Masters during new BOM uploads

**Files to Modify:**
- `clevertech/clevertech/doctype/bom_upload/bom_upload_enhanced.py`

**Changes Required:**

1. **Read machine_code from BOM Upload form:**
```python
def create_boms_with_validation(self):
    # Get machine_code from BOM Upload doctype
    machine_code = self.machine_code

    if not machine_code:
        frappe.throw(_("Machine Code is required for BOM Upload"))

    # ... rest of the function
```

2. **Update duplicate check to include machine_code:**
```python
# OLD (Current):
existing = frappe.db.exists(
    "Project Component Master",
    {"project": project, "item_code": item_code}
)

# NEW (Required):
existing = frappe.db.exists(
    "Project Component Master",
    {
        "project": project,
        "item_code": item_code,
        "machine_code": machine_code  # Add this
    }
)
```

3. **Set machine_code on all Component Masters during creation:**
```python
# When creating Component Master in the loop
component_master = frappe.get_doc({
    "doctype": "Project Component Master",
    "project": project,
    "item_code": item_code,
    "machine_code": machine_code,  # NEW: Set on all CMs
    # ... other fields
})
```

**Result:** Going forward, all new BOM uploads automatically populate machine_code ✅

---

#### **Case 2: Existing/Cutover Data (Project Button)**

**Purpose:** Retroactive fix for Component Masters created before machine_code implementation

**Files to Create/Modify:**
- `clevertech/project_component_master/utils.py` (NEW - create this file)
- `clevertech/public/js/project.js` (MODIFY - add button)

**Button on Project Form:**

```javascript
// File: clevertech/public/js/project.js
frappe.ui.form.on('Project', {
    refresh: function(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__("Update Component Data"), function() {
                frappe.confirm(
                    __("This will cascade machine codes from root Component Masters to all children and rebuild BOM Usage tables. Continue?"),
                    function() {
                        frappe.call({
                            method: "clevertech.project_component_master.utils.update_component_data",
                            args: { project: frm.doc.name },
                            freeze: true,
                            freeze_message: __("Updating Component Data..."),
                            callback: function(r) {
                                if (r.message) {
                                    frappe.msgprint({
                                        title: __("Update Complete"),
                                        message: r.message.summary,
                                        indicator: r.message.has_errors ? "orange" : "green"
                                    });
                                }
                            }
                        });
                    }
                );
            }, __("Component Master"));
        }
    }
});
```

**Server Method Logic:**

```python
# File: clevertech/project_component_master/utils.py

import frappe
from frappe import _
from clevertech.project_component_master.bulk_generation import populate_bom_usage_tables


@frappe.whitelist()
def update_component_data(project):
    """
    Cascade machine_code from root Component Masters to children and rebuild BOM usage.

    Workflow:
    1. User manually enters machine_code on ROOT Component Masters
    2. This function cascades to all descendants
    3. Rebuilds BOM Usage tables for entire project

    Args:
        project: Project name

    Returns:
        dict: {
            "machine_code_updated": int,
            "bom_usage_rebuilt": int,
            "summary": str,
            "has_errors": bool,
            "errors": list
        }
    """
    # Step 1: Find all root Component Masters
    roots = frappe.get_all(
        "Project Component Master",
        filters={
            "project": project,
            "parent_component": ["is", "not set"],  # Root = no parent
            "has_bom": 1
        },
        fields=["name", "item_code", "machine_code"]
    )

    if not roots:
        return {
            "summary": _("No root Component Masters found for this project."),
            "machine_code_updated": 0,
            "bom_usage_rebuilt": 0,
            "has_errors": False
        }

    # Step 2: Validate all roots have machine_code
    missing_machine_code = [r.item_code for r in roots if not r.machine_code]

    if missing_machine_code:
        error_msg = _(
            "Please enter machine_code for these root components first:<br><br>"
            "<b>{0}</b><br><br>"
            "Then run this button again."
        ).format("<br>".join(missing_machine_code))

        frappe.throw(error_msg, title=_("Machine Code Missing"))

    # Step 3: Cascade machine_code from each root to its descendants
    machine_code_updated = 0
    errors = []

    for root in roots:
        try:
            count = cascade_machine_code_recursive(root.name, root.machine_code)
            machine_code_updated += count
        except Exception as e:
            frappe.log_error(
                title=f"Failed to cascade machine_code for {root.item_code}",
                message=frappe.get_traceback()
            )
            errors.append(f"{root.item_code}: {str(e)}")

    # Step 4: Rebuild BOM Usage tables
    bom_usage_rebuilt = 0
    try:
        boms = frappe.get_all(
            "BOM",
            filters={"project": project, "docstatus": 1, "is_active": 1},
            fields=["name", "item"]
        )

        if boms:
            populate_bom_usage_tables(project, boms)
            bom_usage_rebuilt = len(boms)
    except Exception as e:
        frappe.log_error(
            title=f"Failed to rebuild BOM usage for {project}",
            message=frappe.get_traceback()
        )
        errors.append(f"BOM Usage rebuild: {str(e)}")

    # Step 5: Commit and return summary
    frappe.db.commit()

    summary = _(
        "✓ Roots processed: <b>{0}</b><br>"
        "✓ Machine codes updated: <b>{1}</b> Component Masters<br>"
        "✓ BOM usage rebuilt: <b>{2}</b> BOMs<br>"
    ).format(len(roots), machine_code_updated, bom_usage_rebuilt)

    if errors:
        summary += _("<br>⚠ Errors encountered:<br>• {0}").format("<br>• ".join(errors))

    return {
        "machine_code_updated": machine_code_updated,
        "bom_usage_rebuilt": bom_usage_rebuilt,
        "summary": summary,
        "has_errors": len(errors) > 0,
        "errors": errors
    }


def cascade_machine_code_recursive(component_master_name, machine_code):
    """
    Recursively cascade machine_code to all descendants via parent_component chain.

    Args:
        component_master_name: Name of Component Master (starting point)
        machine_code: Machine code to cascade

    Returns:
        int: Count of Component Masters updated
    """
    # Find all direct children
    children = frappe.get_all(
        "Project Component Master",
        filters={"parent_component": component_master_name},
        fields=["name"]
    )

    updated_count = 0

    for child in children:
        # Update machine_code (overwrites existing value - root is source of truth)
        frappe.db.set_value(
            "Project Component Master",
            child.name,
            "machine_code",
            machine_code,
            update_modified=False  # Don't update modified timestamp
        )
        updated_count += 1

        # Recursively cascade to this child's children
        updated_count += cascade_machine_code_recursive(child.name, machine_code)

    return updated_count
```

**Validation Logic:**

- **Root Identification:** `parent_component IS NULL AND has_bom = 1`
- **Error Handling:** If any root missing machine_code → show error with list, user must fix first
- **Cascade Strategy:** Overwrite all descendant machine_codes (root is source of truth)
- **BOM Usage:** Call existing `populate_bom_usage_tables()` from `bulk_generation.py`

**Result:** Existing Component Masters get machine_code populated retroactively ✅

---

### Implementation Log (2026-02-02)

**Status:** ✅ **COMPLETED** - Machine Code population implemented for both new uploads and existing data

#### **Files Modified/Created:**

1. **bom_upload_enhanced.py** (Modified - Case 1: New BOM Uploads)
   - File: `clevertech/clevertech/doctype/bom_upload/bom_upload_enhanced.py`
   - Changes:
     - Added machine_code validation in `create_boms_with_validation()` (line ~207)
     - Updated function signature: `create_component_masters_for_all_items(tree, project, machine_code)`
     - Updated duplicate check to include machine_code: `{"project": project, "item_code": item_code, "machine_code": machine_code}`
     - Added machine_code to Component Master creation in `cm_data` dict
     - Updated `analyze_upload()` to accept and pass machine_code parameter
     - Updated `_determine_component_status()` to query with machine_code
     - Updated `confirm_version_change()` to read and use machine_code
     - Updated `_proceed_with_confirmed_changes()` to handle machine_code in all queries

2. **utils.py** (Created - Case 2: Existing Data Cascade)
   - File: `clevertech/project_component_master/utils.py`
   - Functions:
     - `update_component_data(project)`: Main whitelisted function for Project button
       - Finds root Component Masters (parent_component IS NULL)
       - Validates all roots have machine_code
       - Cascades machine_code to all descendants
       - Rebuilds BOM Usage tables via `populate_bom_usage_tables()`
       - Returns summary with counts and error messages
     - `cascade_machine_code_recursive(component_master_name, machine_code)`: Recursive helper
       - Traverses parent_component chain
       - Updates machine_code on all children
       - Returns count of updated records

3. **project.js** (Modified - Case 2: UI Button)
   - File: `clevertech/public/js/project.js`
   - Added button: "Update Component Data" in Component Master menu
   - Confirmation dialog with prerequisites explanation
   - Calls `clevertech.project_component_master.utils.update_component_data`
   - Displays success/error summary with color indicators

#### **Implementation Approach:**

**Case 1: New BOM Uploads (Going Forward)**
- BOM Upload form now requires machine_code field (validated at start)
- All Component Masters created during upload automatically get machine_code
- Uniqueness constraint enforced: (project + item_code + machine_code)
- Same item in different machines = separate Component Master records

**Case 2: Existing/Cutover Data (Retroactive Fix)**
- User workflow:
  1. Manually set machine_code on root Component Masters (V/P codes)
  2. Click "Update Component Data" button on Project form
  3. System cascades machine_code to all children recursively
  4. BOM Usage tables automatically rebuilt
- Root is source of truth (overwrites any existing machine_code on children)

#### **Testing Checklist:**

- [ ] Upload new BOM with machine_code → Verify all Component Masters get machine_code
- [ ] Upload same item for different machines → Verify separate Component Masters created
- [ ] Set machine_code on root → Click button → Verify cascade to all descendants
- [ ] Verify BOM Usage tables repopulated after cascade
- [ ] Test error handling: Missing machine_code on root → Should show error with item list
- [ ] Test error handling: Empty machine_code on BOM Upload → Should show validation error

#### **Database Impact:**

- **No schema changes needed** - machine_code field already added to Project Component Master
- **Existing records:** machine_code will be NULL until populated via Case 2 workflow
- **New records:** machine_code will be populated automatically from BOM Upload
- **Query changes:** All Component Master lookups now include machine_code in filters

#### **Breaking Changes:**

⚠️ **BOM Upload now requires machine_code** - Users must enter machine_code when uploading BOMs going forward

#### **Next Steps for Production Deployment:**

1. **Pre-deployment:**
   - Review existing Component Masters - identify which need machine_code
   - Prepare mapping: Root Component Master → Machine Code
   - Communicate machine_code requirement to BOM upload users

2. **Deployment:**
   - Deploy code changes
   - Run database migration (if any custom SQL needed for bulk updates)

3. **Post-deployment:**
   - Admin manually sets machine_code on root Component Masters
   - Admin clicks "Update Component Data" button per project
   - Verify cascade completed successfully
   - Test new BOM uploads with machine_code

4. **Phase 5 Continuation:**
   - Proceed to Procurement Status Report implementation
   - Report will use machine_code for machine-level tracking

---

### Report Features

**Filters:**
- Project (Link to Project) - Required
- Machine Code (Data) - Optional
- Date Range (From/To Date) - Optional
- Procurement Status (Select: Not Started/In Progress/Completed) - Optional
- Item Code (Link to Item) - Optional

**Toggle Sections (Checkboxes):**
- Show BOM Data (default: unchecked)
- Show Budget (default: unchecked)
- Show Material Request (default: checked)
- Show RFQ (default: unchecked)
- Show Purchase Order (default: checked)
- Show Quality (default: unchecked)
- Show Production (default: unchecked)

**UI Enhancements:**
- Blank consecutive duplicate values for Project/Machine/WBS/M-Code/G-Code columns
- Color-coded status indicators (Pending=Red, Partial=Orange, Completed=Green)
- Clickable links to source documents (MR, RFQ, PO, PR, QI)
- Export to Excel with all data

**Implementation Files:**
```
clevertech/supply_chain/report/procurement_status_report/
├── __init__.py
├── procurement_status_report.json    # Report metadata
├── procurement_status_report.py      # Backend: data fetching, calculations
└── procurement_status_report.js      # Frontend: filters, toggles, formatting
```

---

### Phase 5 Issue: BOM Hash Comparison Failure (2026-02-02)

#### Problem Discovery

During testing of the enhanced BOM Upload system, a critical issue was discovered:

**Symptom:**
- Excel file uploaded with BOM structure containing item A00000006515 appearing 3 times under G00000054189 with quantities 5, 1, 4 (total=10)
- Existing BOM-G00000054189-001 has 1 row for A00000006515 with qty=14
- Upload reported "8 BOMs already existed" - treating the BOM as unchanged
- **Hash comparison failed to detect the structure change**

#### Root Cause Analysis (RCA)

**Investigation Steps:**
1. Created debug function `debug_bom_quantities()` to trace BOM creation from Excel
2. Confirmed Excel structure: 3 occurrences with qty=5, 1, 4 (total=10) ✓
3. Checked existing BOM: 1 row with qty=14 (created 7 months ago)
4. Examined Component Master: `bom_structure_hash` was NULL for old BOMs

**Root Causes Identified:**

1. **NULL Hash for Existing BOMs:**
   - Old BOMs created before hash system was implemented have NULL hash in Component Master
   - Comparison logic treats NULL hash as "unchanged" (bug!)
   - No backfill migration was run to calculate hashes for existing BOMs

2. **Hash Storage Location:**
   - Current: Hash stored in Component Master (calculated at BOM creation time)
   - Problem: Component Master can exist without a hash if BOM was created before hash feature
   - Better: Hash should be stored in BOM itself (source of truth)

3. **Hash Calculation Timing:**
   - Current: Hash calculated from Excel tree during upload, stored in Component Master
   - Problem: If hash is NULL in Component Master, comparison fails silently
   - Better: Calculate hash from actual BOM items, store in BOM, compare during upload

**Why Qty Changed (14 vs 10):**
- Old BOM created from different Excel revision 7 months ago
- Design underwent revisions, quantities changed
- This is expected - the issue is that the change wasn't detected

#### Proposed Solution

**Design Decision 17: BOM Structure Hash Storage and Comparison**

**1. Add Custom Field to BOM DocType:**
```python
{
    "fieldname": "custom_bom_structure_hash",
    "fieldtype": "Data",  # 140 chars, sufficient for 32-char MD5 hash
    "label": "BOM Structure Hash",
    "read_only": 1,
    "hidden": 1  # Internal use only
}
```

**2. Hash Calculation Logic (No Consolidation):**

*Decision: Do NOT consolidate duplicate items before hashing*

**Rationale:**
- Frappe stores BOM items as separate rows (no auto-consolidation)
- Hashing raw structure catches more granular changes:
  - Quantity changes ✓
  - Item additions/removals ✓
  - Occurrence count changes ✓ (e.g., 1 row→3 rows even if total qty same)
- Matches actual BOM storage format
- More precise change detection

**Example:**
```python
# BOM Items table
items = [
    ("A00000006515", 5.0),   # Row 1
    ("A00000006515", 1.0),   # Row 2
    ("A00000006515", 4.0),   # Row 3
    ("B00000012345", 2.0)
]

# Hash calculation (sorted by item_code, then by qty for deterministic order)
structure = sorted(
    [(item.item_code, float(item.qty)) for item in bom.items],
    key=lambda x: (x[0], x[1])  # Sort by item_code, then qty
)
structure_str = json.dumps(structure, sort_keys=True)
hash = hashlib.md5(structure_str.encode()).hexdigest()
# Result: "5d07e6e944a5cdb3ab165a2474f4222c" (32 chars)
```

**3. When to Calculate Hash:**

```python
# In bom_hooks.py - on_submit hook
def on_submit(self, method):
    """Calculate and store BOM structure hash after submit"""
    if self.docstatus == 1:  # Only for submitted BOMs
        # Calculate hash from items table
        structure = sorted(
            [(item.item_code, float(item.qty or 0)) for item in self.items],
            key=lambda x: (x[0], x[1])
        )
        structure_str = json.dumps(structure, sort_keys=True)
        hash_value = hashlib.md5(structure_str.encode()).hexdigest()

        # Store in BOM (not Component Master)
        self.db_set('custom_bom_structure_hash', hash_value, update_modified=False)
```

**4. Comparison Logic During Upload:**

```python
# In bom_upload_enhanced.py - _determine_component_status()
def compare_bom_structures(component_master, new_excel_children, project, machine_code):
    """
    Compare existing BOM hash with new Excel structure hash.

    Returns:
        tuple: (is_changed, old_hash, new_hash)
    """
    # Get existing BOM
    existing_bom_name = component_master.active_bom
    if not existing_bom_name:
        return (False, None, None)  # No BOM to compare

    existing_bom = frappe.get_doc("BOM", existing_bom_name)

    # Get or calculate existing BOM hash
    old_hash = existing_bom.custom_bom_structure_hash
    if not old_hash:
        # Backfill: Calculate hash from existing BOM items
        structure = sorted(
            [(item.item_code, float(item.qty or 0)) for item in existing_bom.items],
            key=lambda x: (x[0], x[1])
        )
        old_hash = hashlib.md5(json.dumps(structure, sort_keys=True).encode()).hexdigest()
        existing_bom.db_set('custom_bom_structure_hash', old_hash, update_modified=False)

    # Calculate new hash from Excel
    structure = sorted(
        [(child["item_code"], float(child.get("qty", 1))) for child in new_excel_children],
        key=lambda x: (x[0], x[1])
    )
    new_hash = hashlib.md5(json.dumps(structure, sort_keys=True).encode()).hexdigest()

    # Compare
    is_changed = (old_hash != new_hash)

    return (is_changed, old_hash, new_hash)
```

**5. Migration for Existing BOMs:**

```python
# One-time migration script
def migrate_bom_hashes():
    """Backfill BOM structure hash for all existing submitted BOMs"""
    import frappe
    import hashlib
    import json

    boms = frappe.get_all(
        "BOM",
        filters={"docstatus": 1},
        fields=["name"]
    )

    updated = 0
    for bom_data in boms:
        bom = frappe.get_doc("BOM", bom_data.name)

        # Skip if hash already exists
        if bom.custom_bom_structure_hash:
            continue

        # Calculate hash
        structure = sorted(
            [(item.item_code, float(item.qty or 0)) for item in bom.items],
            key=lambda x: (x[0], x[1])
        )
        hash_value = hashlib.md5(json.dumps(structure, sort_keys=True).encode()).hexdigest()

        # Store hash
        bom.db_set('custom_bom_structure_hash', hash_value, update_modified=False)
        updated += 1

    frappe.db.commit()
    print(f"Updated {updated} BOMs with structure hash")
```

#### Debug Function Added

To facilitate troubleshooting BOM quantity discrepancies, added `debug_bom_quantities()` function:

**File:** `clevertech/clevertech/doctype/bom_upload/bom_upload_enhanced.py`

**Function:** `debug_bom_quantities(docname, target_item_code=None)`

**Purpose:**
- Parse Excel and trace BOM creation WITHOUT actually creating BOMs
- Show how many times an item appears in Excel
- Group occurrences by parent assembly
- Display individual quantities and hierarchy
- Identify quantity discrepancies

**Usage:**
```javascript
// From browser console on BOM Upload form
cur_frm.trigger('debug_bom_quantities')
// Enter item code (e.g., "A00000006515") or leave empty
```

**Output:**
- Excel occurrences count
- Total quantity from Excel
- Breakdown by parent assembly
- Individual row details (row number, position, qty, level)
- Warning if multiple BOM items would be created

#### Implementation Checklist

**Phase 5 Hash Fix:**
- [x] Add `custom_bom_structure_hash` field to BOM DocType (Data, 140 chars)
- [ ] Implement hash calculation in `on_submit` hook (bom_hooks.py)
- [ ] Update comparison logic in bom_upload_enhanced.py
- [ ] Add backfill logic for NULL hashes during comparison
- [ ] Create migration script for existing BOMs
- [ ] Test with old BOM (hash=NULL) to verify backfill works
- [ ] Test with new BOM to verify hash stored correctly
- [ ] Test comparison detects changes (qty change, structure change)
- [ ] Remove `bom_structure_hash` from Component Master (cleanup)
- [ ] Update documentation

**Files to Modify:**
1. `clevertech/clevertech/doctype/bom_upload/bom_upload_enhanced.py` - comparison logic
2. `clevertech/project_component_master/bom_hooks.py` - hash calculation on submit
3. Custom field JSON for BOM DocType

---

### Sample Output

```
| Project | Machine  | WBS Code | M-Code  | G-Code  | Item No  | Item Name   | Qty | UOM | [+ 52 more columns] |
|---------|----------|----------|---------|---------|----------|-------------|-----|-----|---------------------|
| PRJ001  | P0003033 | WBS0001  | M00249  | G00453  | A000001  | Gear Shaft  | 2   | Nos | ...                 |
|         |          |          |         |         | D000851  | Pulley      | 1   | Nos | ...                 |
|         |          |          |         |         | E000123  | Cable       | 5   | Mtr | ...                 |
|         |          |          | M00250  | G00454  | A000002  | Bearing     | 4   | Nos | ...                 |
```
*(Note: Duplicate values in columns 1-5 shown as blank for visual clarity)*

---

### Phase 5 Fix: Component Master Calculation Issues (2026-02-02)

#### Problem 1: Calculated Fields Not Persisting After BOM Upload

**Symptom:**
- After BOM upload, Component Masters created successfully
- `total_qty_limit`, `bom_qty_required`, and other calculated fields remained 0.00
- Manual `save()` in console worked perfectly
- `save()` during hooks/BOM upload didn't persist calculated values

**Investigation:**
```python
# Manual save in console - WORKS ✓
cm = frappe.get_doc("Project Component Master", "PCM-SMR260002-001646")
cm.save()  # Triggers before_save() → calculations run → values persist
frappe.db.commit()

# During BOM upload hooks - FAILS ✗
component_master.calculate_bom_qty_required()
component_master.calculate_total_qty_limit()
component_master.save(ignore_permissions=True)
frappe.db.commit()  # Values still show as 0.00 in database!
```

**Root Cause:**
- `save()` within hooks (before_save, on_submit, etc.) doesn't persist calculated values due to:
  - Transaction context issues
  - Flags like `ignore_validate=True` may skip `before_save()` in some contexts
  - Inner save within hook lifecycle can trigger rollbacks
- Manual console `save()` works because it's outside hook context

**Solution: Use `frappe.db.set_value()` for Calculated Fields**

Following ERPNext manufacturing code patterns, switched to direct DB writes for calculated fields in hooks:

```python
# BEFORE (didn't work)
cm.calculate_bom_qty_required()
cm.calculate_total_qty_limit()
cm.save(ignore_permissions=True)

# AFTER (works reliably)
cm.calculate_bom_qty_required()
cm.calculate_total_qty_limit()
cm.calculate_procurement_totals()
cm.update_procurement_status()

# Direct DB write (bypasses save() issues)
frappe.db.set_value(cm.doctype, cm.name, {
    "bom_qty_required": cm.bom_qty_required,
    "total_qty_limit": cm.total_qty_limit,
    "total_qty_procured": cm.total_qty_procured,
    "procurement_balance": cm.procurement_balance,
    "procurement_status": cm.procurement_status
}, update_modified=False)

frappe.db.commit()
```

**Why This Approach:**
- ✅ Reliable in hooks context
- ✅ Standard Frappe pattern for calculated fields
- ✅ Fast (no validation/hooks overhead)
- ✅ Used in ERPNext manufacturing code for inventory calculations
- ✅ Better than multiple `db_set()` calls (single DB operation)

**Files Modified:**
1. **bom_hooks.py** - `recalculate_component_masters_for_project()`
   - Called after all BOMs created and committed
   - Uses `frappe.db.set_value()` to persist calculated fields

2. **project_component_master.py** - `recalculate_children_bom_qty()`
   - Cascade recalculation when parent's make_or_buy changes
   - Uses `frappe.db.set_value()` to persist calculated fields

---

#### Problem 2: Incorrect `project_qty` for Child Items

**Symptom:**
- Item A00000000479 has parent D00000084229 marked as "Buy"
- `bom_qty_required = 0.0` ✓ (correct - parent is "Buy", child covered by parent procurement)
- `project_qty = 1.0` (from Excel column E during upload)
- `total_qty_limit = MAX(1, 0) = 1.0` ✗ (WRONG! Should be 0)

**Root Cause Analysis:**

According to **Decision 13** (documented earlier):
- `project_qty` should only be set for **root assemblies** (level 1)
- **Child items** (level 2+) should have `project_qty = 0`
- Their requirement comes from `bom_qty_required` (calculated from BOM usage)

**Example from Decision 13:**
```
SUB-ASSY (child of TOP-ASSY)
├── qty_per_unit = 2 (in TOP-ASSY's BOM)
├── project_qty = 0 (user doesn't set for child items)  ← KEY POINT
├── bom_usage table:
│   └── parent=TOP-ASSY, qty_per_unit=2, total_qty_required=6 (3×2)
├── bom_qty_required = 6 (auto-calculated)
├── total_qty_limit = MAX(0, 6) = 6
```

**Current Issue:**
BOM upload was setting `project_qty` from Excel column E for ALL items (root + children), causing child items to have incorrect `total_qty_limit`.

**Solution: Only Set `project_qty` for Root Assemblies**

**File:** `clevertech/clevertech/doctype/bom_upload/bom_upload_enhanced.py`

```python
# BEFORE (incorrect)
cm_data = {
    "project_qty": node.get("qty", 0),  # Set for ALL items
    # ...
}

# AFTER (correct)
# Only set project_qty for root assemblies (level 1)
# Child items (level 2+) get project_qty=0, their requirement comes from bom_qty_required
level = node.get("level", 0)
project_qty = node.get("qty", 0) if level == 1 else 0

cm_data = {
    "project_qty": project_qty,  # From Excel column E (root assembly only)
    # ...
}
```

**Result:**
- Root assemblies (level 1): `project_qty` from Excel, `total_qty_limit = MAX(project_qty, bom_qty_required)`
- Child items (level 2+): `project_qty = 0`, `total_qty_limit = bom_qty_required`
- Child items with "Buy" parents: `project_qty = 0`, `bom_qty_required = 0`, `total_qty_limit = 0` ✓

---

#### Problem 3: Cascade Recalculation Not Working

**Symptom:**
- Changed parent Component Master from "Buy" to "Make"
- Saved parent successfully
- Child items' `bom_qty_required` and `total_qty_limit` did NOT update

**Root Cause:**
Cascade function `recalculate_children_bom_qty()` was calling `save()` on children, which suffered from the same persistence issue as Problem 1.

**Solution:**
Applied same fix - use `frappe.db.set_value()` in cascade function.

**File:** `clevertech/clevertech/doctype/project_component_master/project_component_master.py`

```python
def recalculate_children_bom_qty(self):
    """Cascade recalculation when parent's make_or_buy changes"""
    if not self.active_bom:
        return

    bom_items = frappe.get_all("BOM Item", filters={"parent": self.active_bom}, fields=["item_code"])

    for item in bom_items:
        child_cm_name = frappe.db.get_value(
            "Project Component Master",
            {"project": self.project, "item_code": item.item_code},
            "name"
        )
        if child_cm_name:
            child_doc = frappe.get_doc("Project Component Master", child_cm_name)

            # Calculate all quantities
            child_doc.calculate_bom_qty_required()
            child_doc.calculate_total_qty_limit()
            child_doc.calculate_procurement_totals()
            child_doc.update_procurement_status()

            # Use frappe.db.set_value to persist (bypasses save() in hooks)
            frappe.db.set_value(child_doc.doctype, child_doc.name, {
                "bom_qty_required": child_doc.bom_qty_required,
                "total_qty_limit": child_doc.total_qty_limit,
                "total_qty_procured": child_doc.total_qty_procured,
                "procurement_balance": child_doc.procurement_balance,
                "procurement_status": child_doc.procurement_status
            }, update_modified=False)

    # Commit all changes
    frappe.db.commit()
```

**Trigger:** Automatically runs via `on_update()` hook when `make_or_buy` changes on parent Component Master.

---

#### Design Rationale: Why `frappe.db.set_value()` Over `save()`

**Context:**
Hooks like `before_save` or `on_update` run within the document's save lifecycle. Calling `save()` again within this context can trigger:
- Infinite loops
- Transaction rollbacks
- Validation blocks that prevent persistence
- Flags (e.g., `ignore_validate`) that skip `before_save()` in some contexts

**Manual `save()` in Console Works Because:**
- It's outside the hook context
- No outer transaction to roll back
- No flag conflicts

**Recommended Approach for Calculated Fields in Hooks:**
Use `frappe.db.set_value()` with a dict:

**Pros:**
- ✅ Reliable in hooks (no transaction conflicts)
- ✅ Direct DB write (fast, no ORM overhead)
- ✅ Single DB operation for multiple fields
- ✅ Proven pattern in ERPNext manufacturing code
- ✅ Scales well for inventory calculations under Indian compliance loads

**Cons:**
- ❌ Bypasses hooks and validations (acceptable for calculated fields)
- ❌ Not the "standard" Frappe way (but recommended for this use case)
- ❌ Doesn't update `modified`/`modified_by` (use `update_modified=False`)

**When NOT to Use This Approach:**
- Business rules require full validation
- Field values need to trigger other hooks
- Audit trail of modifications is critical

**For Calculated Fields (our use case):**
- No validation needed (values are computed, not user-entered)
- No hooks needed (calculations are deterministic)
- Audit trail not required (can be recalculated anytime)
- **This is the right approach**

---

#### Implementation Summary

**Phase 5 Calculation Fixes (2026-02-02):**
- ✅ Synchronous recalculation after BOM upload using `frappe.db.set_value()`
- ✅ Fixed `project_qty` logic (root assemblies only)
- ✅ Fixed cascade recalculation for make/buy changes
- ✅ Cleaned up redundant calculation calls in hooks
- ✅ Documented approach and rationale

**Files Modified:**
1. `clevertech/clevertech/doctype/bom_upload/bom_upload_enhanced.py` - project_qty logic
2. `clevertech/project_component_master/bom_hooks.py` - recalculation function
3. `clevertech/clevertech/doctype/project_component_master/project_component_master.py` - cascade function

**Testing Checklist:**
- [x] BOM upload calculates quantities immediately
- [x] Root assemblies get project_qty from Excel
- [x] Child items get project_qty=0
- [x] Child items with "Buy" parents have total_qty_limit=0
- [ ] Cascade works when parent changes from "Buy" to "Make"
- [ ] Material Request validation uses correct total_qty_limit

---

### Project Tracking Report Implementation (2026-02-03)

**Report Name:** Project Tracking
**Module:** Clevertech
**Files Created:**
- `clevertech/clevertech/report/project_tracking/__init__.py`
- `clevertech/clevertech/report/project_tracking/project_tracking.json`
- `clevertech/clevertech/report/project_tracking/project_tracking.py`
- `clevertech/clevertech/report/project_tracking/project_tracking.js`

**Design Decisions (Revised):**

1. **Show ALL Component Masters** - Not just "Buy" items
   - Added Make/Buy column to show status
   - Users can filter in report UI if needed
   - Procurement history shows even if item changed to "Make"

2. **Machine Code Source** - Fetched directly from Project Component Master
   - Initially attempted from `cost_center.custom_machine_code` via JOIN
   - **Fixed:** Changed to `pcm.machine_code` for direct fetch
   - Not stored redundantly in Cost Center

3. **WBS Code (Cost Center)** - Fallback lookup via machine_code
   - Primary: `pcm.cost_center` (if set directly on Component Master)
   - Fallback: JOIN to Cost Center matching `cc.custom_machine_code = pcm.machine_code`
   - Uses `COALESCE(pcm.cost_center, cc.name)` for best-effort display

4. **M-Code & G-Code** - Computed at runtime via parent traversal
   - Traverse `parent_component` chain to find ancestor starting with "M" or "G"
   - Requires `parent_component` links to be populated (see "Update Component Data" button)
   - Avoids complexity of maintaining on every edit

5. **Component Image** - Click-to-enlarge functionality
   - Column fieldtype: "Data" (not "Image" to enable custom rendering)
   - JavaScript formatter renders as `<img>` tag with onclick handler
   - Uses `frappe.ui.Dialog` to show full-size image in modal popup

6. **Report Filters** - Minimal
   - Project (required)
   - Section toggles: Show MR, Show RFQ, Show PO
   - Other filtering via column filters in UI

**Sections Implemented:**
| Section | Columns | Toggle |
|---------|---------|--------|
| 1. Default | 12 cols (Project, Machine, WBS, M-Code, G-Code, Image, Item, Name, Desc, Make/Buy, Qty, UOM) | Always |
| 4. Material Request | 4 cols (MR No, MR Qty, ETA, Pending for MR) | show_mr |
| 5. RFQ & Quotation | 16 cols (4 vendors × 3 fields + 4 comparison) | show_rfq |
| 6. PO & Delivery | 9 cols (PO#, Date, Qty, Pending, GRN#, Delivery, Date, Pending, Status) | show_po |

**Deferred:**
- Section 2: BOM Data (can add later)
- Section 3: Budget vs Actual (can add later)
- Section 7: Quality Status (can add later)
- Section 8: Production (can add later)
- Pagination (Frappe datatable handles client-side; add server-side if needed)

---

#### Post-Implementation Fixes (2026-02-03)

**Issue 1: Machine Code and WBS Code Not Displaying**

*Problem:*
- Machine code and WBS code (cost_center) columns showing NULL for project SMR260002 (BOM-HASH)
- Initial query was fetching `cc.custom_machine_code as machine_code` from Cost Center table

*Root Cause:*
- Machine code should be fetched directly from Project Component Master, not Cost Center
- Cost center field was NULL in PCM records (not populated during Component Master creation)

*Fix (project_tracking.py):*
```python
# BEFORE:
SELECT
    cc.custom_machine_code as machine_code,  # WRONG - from Cost Center
    pcm.cost_center,
    ...
FROM `tabProject Component Master` pcm
LEFT JOIN `tabCost Center` cc ON cc.name = pcm.cost_center

# AFTER:
SELECT
    pcm.machine_code,  # CORRECT - from Project Component Master
    COALESCE(pcm.cost_center, cc.name) as cost_center,  # Fallback lookup
    ...
FROM `tabProject Component Master` pcm
LEFT JOIN `tabItem` item ON item.name = pcm.item_code
LEFT JOIN `tabCost Center` cc ON cc.custom_machine_code = pcm.machine_code  # Match by machine_code
```

*Result:*
- Machine code now displays correctly
- Cost center displays via fallback lookup when not directly set
- For project SMR260002: Machine code "BOMHASHTest1" → Cost Center "BOM Hash Test - CT"

---

**Issue 2: Component Images Showing as URLs Instead of Rendering**

*Problem:*
- Image column showing raw URL text instead of displaying image thumbnail
- No way to view full-size image

*Fix (project_tracking.js):*
Added custom formatter with click-to-enlarge functionality:
```javascript
// Render images with click to enlarge
if (column.fieldname === "component_image" && data.component_image) {
    let img_url = data.component_image;
    let item_code = data.item_code || 'Component Image';
    return `<img src="${img_url}"
                 alt="Component"
                 style="max-width:60px;max-height:60px;object-fit:contain;cursor:pointer;"
                 onclick="(function() {
                     let d = new frappe.ui.Dialog({
                         title: '${item_code}',
                         fields: [{
                             fieldtype: 'HTML',
                             fieldname: 'image_html'
                         }]
                     });
                     d.fields_dict.image_html.$wrapper.html('<img src=\\'${img_url}\\' style=\\'max-width:100%;height:auto;\\' />');
                     d.show();
                 })()">`;
}
```

*Note:* Required `bench build --app clevertech` to compile JavaScript changes.

---

**Issue 3: M-Code and G-Code Not Displaying**

*Problem:*
- M-Code and G-Code columns showing NULL for all items
- Function `get_ancestor_code()` traverses `parent_component` chain to find ancestors with item codes starting with "M" or "G"
- For project SMR240004: 47 Component Masters at `bom_level > 1` had NULL `parent_component` values

*Root Cause:*
- `parent_component` links were not populated when Component Masters were initially created
- Workflow: Component Masters created first → BOMs backfilled later → `parent_component` needs retroactive population

*Solution (utils.py):*
Added `backfill_parent_components()` function integrated into "Update Component Data" button:

```python
def backfill_parent_components(project):
    """
    Backfill parent_component links for all Component Masters in a project
    based on the BOM structure.

    Logic:
    - For each Component Master with an active_bom
    - Get all items from that BOM
    - Find the corresponding Component Master for each BOM item
    - Set that Component Master's parent_component to point to this Component Master
    """
    updated_count = 0

    # Get all Component Masters with active BOMs
    component_masters = frappe.get_all(
        "Project Component Master",
        filters={
            "project": project,
            "has_bom": 1,
            "active_bom": ["is", "set"]
        },
        fields=["name", "item_code", "active_bom"]
    )

    for cm in component_masters:
        # Get all items from this BOM
        bom_items = frappe.get_all(
            "BOM Item",
            filters={"parent": cm.active_bom},
            fields=["item_code", "qty"]
        )

        for bom_item in bom_items:
            # Find the Component Master for this BOM item
            child_cm_name = frappe.db.get_value(
                "Project Component Master",
                {"project": project, "item_code": bom_item.item_code},
                "name"
            )

            if not child_cm_name:
                continue  # BOM item doesn't have a Component Master

            # Get current parent_component value
            current_parent = frappe.db.get_value(
                "Project Component Master",
                child_cm_name,
                "parent_component"
            )

            # Update if different or not set
            if current_parent != cm.name:
                frappe.db.set_value(
                    "Project Component Master",
                    child_cm_name,
                    "parent_component",
                    cm.name,
                    update_modified=False
                )
                updated_count += 1

    return updated_count
```

*Integration (utils.py):*
Modified `update_component_data()` function to call backfill as Step 0:
```python
# Step 0: Backfill parent_component links from BOM structure
parent_links_updated = 0
try:
    parent_links_updated = backfill_parent_components(project)
except Exception as e:
    frappe.log_error(...)
    errors.append(f"Parent backfill: {str(e)}")

# Step 1-5: Existing logic (machine code cascade, BOM usage rebuild, etc.)
...
```

*Updated UI (project.js):*
Modified "Update Component Data" button description to include parent backfilling:
```javascript
frappe.confirm(
    __(
        "This will:<br>" +
        "1. Backfill parent_component links from BOM structure<br>" +
        "2. Cascade machine codes from root Component Masters to all children<br>" +
        "3. Rebuild BOM Usage tables<br>" +
        "4. Backfill procurement records<br><br>" +
        "<b>Prerequisites:</b><br>" +
        "• Manually set machine_code on all root Component Masters first<br>" +
        "• This will overwrite any existing machine_code values on child components<br><br>" +
        "Continue?"
    ),
    ...
)
```

*Requirements:*
- Parent Component Masters must have `active_bom` field populated
- `active_bom` is set during BOM Upload or when linking existing BOMs to Component Masters
- Orphaned items (level > 1 but not in any BOM) will remain unlinked

---

#### Key Technical Clarifications

**BOM Level Numbering:**
- Level 1 = Root items (no parent)
- Level 2+ = Child items (have parents)
- Query for orphaned items: `bom_level > 1 AND parent_component IS NULL`

**Project Field:**
- Stores Project ID (e.g., "SMR260002"), not Project Name (e.g., "BOM-HASH")
- Report filter accepts Project link, automatically uses ID for queries

**Workflow:**
1. Component Masters created (via BOM Upload or manual entry)
2. BOMs created/linked to Component Masters (sets `active_bom` field)
3. "Update Component Data" button clicked:
   - Backfills `parent_component` links from BOM structure
   - Cascades `machine_code` from roots to descendants
   - Rebuilds BOM Usage tables
   - Backfills procurement records
4. M-Code/G-Code display works after `parent_component` links populated

---

**Phase 6: Testing** ⏳ (Pending)
- Unit tests for Component Master auto-calculations
- Integration tests for enhanced BOM Upload
- MR/PO validation tests
- Make/buy cascade recalculation tests

---

---

### Bug Fixes (2026-02-02)

#### Fix 1: BOM Version Change Not Removing Old BOM Usage Entries

**Problem:**
When a new BOM version was created via `_proceed_with_confirmed_changes` in `bom_upload_enhanced.py`:
1. Old BOM was deactivated (`is_active=0`, `is_default=0`)
2. `active_bom` was cleared to `None` BEFORE new BOM was created
3. When new BOM was submitted, `on_bom_submit` checked `component_master.active_bom` which was now `None`
4. `_handle_bom_version_change` never ran → old BOM Usage entries remained → `bom_version_history` not logged
5. Result: Duplicate BOM Usage entries (both old and new versions), causing incorrect `total_qty_required` calculations

**Fix (bom_upload_enhanced.py):**
1. **Removed `active_bom` clearing** — Keep `active_bom` pointing to old (deactivated) BOM
2. **Added `confirmed_set` check** — Confirmed items always get recreated regardless of hash comparison
3. When new BOM is submitted, `on_bom_submit` naturally detects version change and calls `_handle_bom_version_change`

```python
# BEFORE (lines 1064-1069 deleted):
frappe.db.set_value("Project Component Master", cm.name, "active_bom", None)

# AFTER: Don't clear active_bom, let on_bom_submit handle version change detection
# Added comment explaining the flow
```

**Files Changed:**
- `clevertech/clevertech/doctype/bom_upload/bom_upload_enhanced.py`

---

#### Fix 2: BOM Usage Not Populated When BOMs Already Exist

**Problem:**
When uploading a file where BOMs already exist but Component Masters don't:
1. BOM Upload creates Component Masters ✅
2. BOM Upload tries to create BOMs but they already exist → SKIPS
3. `on_bom_submit` never triggers (no new BOM submitted)
4. BOM Usage tables never populated ❌
5. `active_bom` never linked to Component Master ❌

**Fix (bom_upload_enhanced.py):**
Modified `_link_boms_to_component_masters` to:
1. Link `active_bom` to Component Masters (existing behavior)
2. Track which BOMs were linked (not created)
3. Call `populate_bom_usage_tables` for linked BOMs

```python
# Track BOMs that were linked (not created)
linked_boms = []
...
if bom_name:
    ...
    linked_boms.append({"name": bom_name, "item": cm_data.item_code})

# Populate BOM Usage for linked BOMs
if linked_boms:
    populate_bom_usage_tables(project, linked_boms)
```

**Files Changed:**
- `clevertech/clevertech/doctype/bom_upload/bom_upload_enhanced.py` (added import + modified `_link_boms_to_component_masters`)

---

#### Fix 3: Duplicate Items in BOM Not Consolidated in Update Component Data

**Problem:**
When same item appears multiple times in BOM items table:
- `on_bom_submit` consolidates quantities correctly (Item A: 5+3 = 8) ✅
- `populate_bom_usage_tables` (used by "Update Component Data" button) didn't consolidate — second call overwrote first (Item A: 5 → 3) ❌

**Fix (bulk_generation.py):**
Added same consolidation logic as `on_bom_submit`:

```python
# BEFORE:
for item in bom_doc.items:
    add_or_update_bom_usage(..., qty_per_unit=item.qty)  # OVERWRITES!

# AFTER:
# Consolidate duplicate items in BOM (sum quantities)
item_quantities = {}
for item in bom_doc.items:
    if item.item_code in item_quantities:
        item_quantities[item.item_code] += float(item.qty or 0)
    else:
        item_quantities[item.item_code] = float(item.qty or 0)

# Process consolidated items
for item_code, total_qty in item_quantities.items():
    add_or_update_bom_usage(..., qty_per_unit=total_qty)  # CORRECT!
```

**Files Changed:**
- `clevertech/project_component_master/bulk_generation.py`

---

#### Summary of Scenarios After Fixes

| Scenario | Before Fixes | After Fixes |
|----------|--------------|-------------|
| Fresh BOM upload | ✅ Works | ✅ Works |
| BOM version change | ❌ Duplicate BOM Usage, no history | ✅ Old entries removed, history logged |
| BOMs exist, Components don't | ❌ No BOM Usage, no active_bom link | ✅ BOM Usage populated, active_bom linked |
| Duplicate items in BOM (Update Component Data) | ❌ Wrong qty (last only) | ✅ Correct consolidated qty |

---

### Technical Reference: BOM Hash Comparison & Version Change Flow (2026-02-02)

#### 1. Hash Creation Algorithm

**Two hash calculation functions exist for different contexts:**

**A. `calculate_bom_structure_hash(bom_doc)` — For existing BOM documents**
Location: `project_component_master/bom_hooks.py:948-964`
```python
def calculate_bom_structure_hash(bom_doc):
    """Calculate MD5 hash of BOM structure from BOM document."""
    if not bom_doc.items:
        return None

    # Create sorted list of (item_code, qty) tuples
    structure = sorted(
        [(item.item_code, float(item.qty)) for item in bom_doc.items],
        key=lambda x: x[0]
    )

    # Convert to JSON string and hash
    structure_str = json.dumps(structure, sort_keys=True)
    return hashlib.md5(structure_str.encode()).hexdigest()
```

**B. `calculate_tree_structure_hash(children)` — For Excel tree nodes**
Location: `clevertech/doctype/bom_upload/bom_upload_enhanced.py:1325-1345`
```python
def calculate_tree_structure_hash(children):
    """Calculate MD5 hash from Excel tree node children."""
    if not children:
        return None

    structure = sorted(
        [(child["item_code"], float(child.get("qty", 1))) for child in children],
        key=lambda x: x[0]
    )
    structure_str = json.dumps(structure, sort_keys=True)
    return hashlib.md5(structure_str.encode()).hexdigest()
```

**Hash Format:** 32-character MD5 hex string (e.g., `"a1b2c3d4e5f6..."`)

**Important:** Hash is calculated from **direct children only** (item_code + qty), sorted alphabetically. Does NOT include grandchildren or other BOM item fields.

---

#### 2. Hash Storage Location

**Source of Truth:** `BOM.custom_bom_structure_hash` field (on BOM DocType)

**Legacy:** `Project Component Master.bom_structure_hash` field (still exists but NOT used for comparison)

**Why BOM is source of truth:**
- BOM is immutable after submit (hash won't change)
- Component Master's hash could become stale if BOM is updated externally
- Enables backfilling for old BOMs that predate the hash system

---

#### 3. Hash Comparison Flow During Upload

**Location:** `_determine_component_status()` in `bom_upload_enhanced.py:621-704`

```
┌─────────────────────────────────────────────────────────────────┐
│                    analyze_upload()                              │
│                         │                                        │
│                         ▼                                        │
│         _determine_component_status(item_code, node)             │
│                         │                                        │
│     ┌───────────────────┼───────────────────┐                   │
│     ▼                   ▼                   ▼                   │
│ No Component    No active_bom         Has active_bom            │
│   Master?       on CM?                                          │
│     │                   │                   │                   │
│     ▼                   ▼                   ▼                   │
│ Return "new"      Return "new"      Compare hashes              │
│                                            │                    │
│                         ┌──────────────────┴──────────────────┐ │
│                         ▼                                      ▼│
│                   Get hash from BOM              Calculate hash │
│                   (custom_bom_structure_hash)    from Excel tree│
│                         │                                      ││
│                         ▼                                       │
│                   Hash is NULL?                                 │
│                   ┌─────┴─────┐                                 │
│                   ▼           ▼                                 │
│                  Yes         No                                 │
│                   │           │                                 │
│                   ▼           │                                 │
│              BACKFILL:        │                                 │
│         Calculate from BOM    │                                 │
│         Store in BOM field    │                                 │
│                   │           │                                 │
│                   └─────┬─────┘                                 │
│                         ▼                                       │
│                  Compare hashes                                 │
│                   ┌─────┴─────┐                                 │
│                   ▼           ▼                                 │
│               Match?      Different?                            │
│                   │           │                                 │
│                   ▼           ▼                                 │
│           Return "unchanged"  Check procurement                 │
│                               Return "changed" + blocking info  │
└─────────────────────────────────────────────────────────────────┘
```

---

#### 4. Backfilling Logic for NULL Hashes

**Problem:** Old BOMs (created before hash system) have `custom_bom_structure_hash = NULL`

**Solution:** Backfill on-demand during comparison

**Location:** `_determine_component_status()` lines 672-682, also in `_proceed_with_confirmed_changes()` lines 1107-1116

```python
# Get existing hash from BOM (not Component Master)
existing_hash = frappe.db.get_value(
    "BOM", component_master.active_bom, "custom_bom_structure_hash"
)

# Backfill if NULL - calculate from actual BOM items
if not existing_hash:
    bom_doc = frappe.get_doc("BOM", component_master.active_bom)
    existing_hash = calculate_bom_doc_hash(bom_doc)
    if existing_hash:
        # Store the backfilled hash on BOM (persists for future comparisons)
        frappe.db.set_value(
            "BOM", component_master.active_bom,
            "custom_bom_structure_hash", existing_hash,
            update_modified=False  # Don't change modified timestamp
        )
```

**Key Points:**
- Backfill happens silently during upload analysis
- Hash is stored on BOM permanently (won't need recalculation next time)
- `update_modified=False` prevents changing BOM's modified timestamp

---

#### 5. Version Change Confirmation Flow

**When hash comparison detects a change:**

```
┌─────────────────────────────────────────────────────────────────┐
│                Hash Different Detected                          │
│                         │                                        │
│                         ▼                                        │
│         _check_procurement_blocking(project, item, old_bom)     │
│                         │                                        │
│     ┌───────────────────┼───────────────────┐                   │
│     ▼                   ▼                   ▼                   │
│ No MR/RFQ/PO      MR or RFQ exists      PO exists              │
│     │                   │                   │                   │
│     ▼                   ▼                   ▼                   │
│ blocking_level    blocking_level      Has Manager role?        │
│ = "confirm"       = "block"           ┌─────┴─────┐            │
│     │                   │             ▼           ▼            │
│     │                   │           Yes         No             │
│     │                   │             │           │            │
│     │                   │             ▼           ▼            │
│     │                   │      "confirm"    "manager_required" │
│     │                   │      (with warning)                  │
│     └─────────┬─────────┴─────────────┴───────────┘            │
│               ▼                                                 │
│      Return to client with status                              │
│               │                                                 │
│     ┌─────────┼─────────┬─────────────────────┐                │
│     ▼         ▼         ▼                     ▼                │
│ requires_  procurement_ manager_         success               │
│ confirmation blocked    required          (can proceed)        │
│     │         │         │                     │                │
│     ▼         ▼         ▼                     │                │
│ Show      Show block  Show block             │                │
│ confirm   dialog      dialog                 │                │
│ dialog    (MR/RFQ)    (need role)            │                │
│     │                                         │                │
│     ▼                                         │                │
│ User enters remarks                           │                │
│ Clicks "Proceed"                              │                │
│     │                                         │                │
│     ▼                                         │                │
│ confirm_version_change() ←────────────────────┘                │
│     │                                                          │
│     ▼                                                          │
│ _proceed_with_confirmed_changes()                              │
└─────────────────────────────────────────────────────────────────┘
```

---

#### 6. `_proceed_with_confirmed_changes()` Step-by-Step

**Location:** `bom_upload_enhanced.py:1007-1131`

**Called when:** User confirms version change via `confirm_version_change()` whitelisted method

**Step-by-step flow:**

```python
def _proceed_with_confirmed_changes(doc, confirmed_items, remarks_map):
    """
    Process confirmed BOM version changes.

    Args:
        doc: BOM Upload document
        confirmed_items: List of item_codes user confirmed
        remarks_map: Dict mapping item_code to user's remarks
    """

    # Step 1: Initialize (parse Excel, build tree)
    ws = load_workbook(...)
    image_loader = SheetImageLoader(ws) if available
    rows = parse_rows_dynamic(ws)
    tree = build_tree(rows)

    # Step 2: Ensure Items exist
    ensure_items_for_all_nodes(tree, ws, image_loader, item_counters)

    # Step 3: Deactivate old BOMs for confirmed items
    for item_code in confirmed_items:
        cm = get_component_master(project, item_code, machine_code)
        if cm and cm.active_bom:
            # Deactivate old BOM
            old_bom = frappe.get_doc("BOM", cm.active_bom)
            old_bom.is_active = 0
            old_bom.is_default = 0
            old_bom.save()

            # IMPORTANT: Do NOT clear active_bom here!
            # Keep reference so on_bom_submit can detect version change

    # Step 4: Build can_create list
    for node in all_assemblies:
        if item_code in confirmed_set:
            # Confirmed items always get recreated
            can_create.append(node)
            continue

        # For others, compare hash (with backfill if NULL)
        existing_hash = get_hash_from_bom(cm.active_bom)
        if not existing_hash:
            existing_hash = calculate_and_backfill(cm.active_bom)

        if new_hash != existing_hash:
            can_create.append(node)

    # Step 5: Create BOMs and link to Component Masters
    result = create_boms_and_link_components(tree, project, analysis, ...)

    # Step 6: Recalculate all Component Master quantities
    recalculate_component_masters_for_project(project)

    return result
```

---

#### 7. How `on_bom_submit` Handles Version Change

**Location:** `project_component_master/bom_hooks.py:100-157`

**Key insight:** Because `_proceed_with_confirmed_changes` keeps `active_bom` pointing to the old (deactivated) BOM, `on_bom_submit` can detect the version change:

```python
def on_bom_submit(doc, method):
    """Hook called when BOM is submitted."""

    # Get Component Master
    component_master = get_component_master(doc.project, doc.item)
    if not component_master:
        return  # Not tracked

    # Detect version change
    old_bom = component_master.active_bom
    if old_bom and old_bom != doc.name:
        # Different BOM was active — this is a VERSION CHANGE
        _handle_bom_version_change(doc.project, doc.item, old_bom, doc.name)
    elif not old_bom:
        # First BOM being linked
        _add_initial_bom_version(doc.project, doc.item, doc.name)

    # Add BOM Usage entries for new BOM (consolidated)
    item_quantities = {}
    for item in doc.items:
        item_quantities[item.item_code] = item_quantities.get(item.item_code, 0) + item.qty

    for item_code, total_qty in item_quantities.items():
        add_or_update_bom_usage(project, item_code, doc.name, total_qty)

    # Update Component Master fields (sets active_bom to new BOM)
    update_component_master_bom_fields(doc.project, doc.item, doc.name)
```

**`_handle_bom_version_change()` does:**
1. Logs version change to `bom_version_history` child table
2. Removes old BOM's usage entries from ALL child Component Masters
3. Checks for removed items with existing procurement (warns user)
4. Checks for qty reductions causing over-procurement (warns user)

---

#### 8. Complete Flow Diagram: BOM Upload with Version Change

```
User uploads PE2 Excel
         │
         ▼
create_boms_with_validation()
         │
         ▼
Step 3: Create Component Masters (active_bom=null initially)
         │
         ▼
Step 4: analyze_upload()
         │
         ├──→ _determine_component_status() for each assembly
         │         │
         │         ▼
         │    Compare hash (from BOM) vs hash (from Excel)
         │    Backfill NULL hashes
         │         │
         │         ▼
         │    Return: new / unchanged / changed / loose_blocked
         │
         ▼
Hash changed detected?
    │
    ├──→ No: Continue to Step 6 (create BOMs)
    │
    └──→ Yes: Return "requires_confirmation" to client
              │
              ▼
         Client shows confirmation dialog
         User enters remarks, clicks Proceed
              │
              ▼
         confirm_version_change() [whitelisted]
              │
              ▼
         _proceed_with_confirmed_changes()
              │
              ├──→ Deactivate old BOMs (is_active=0)
              │    Keep active_bom reference (for version detection)
              │
              └──→ create_boms_and_link_components()
                        │
                        ▼
                   create_bom_recursive() → BOM submitted
                        │
                        ▼
                   on_bom_submit() hook fires
                        │
                        ▼
                   Detects old_bom != new_bom (VERSION CHANGE!)
                        │
                        ├──→ _handle_bom_version_change()
                        │         │
                        │         ├──→ Log to bom_version_history
                        │         └──→ Remove old BOM usage entries
                        │
                        ├──→ Add new BOM usage entries (consolidated)
                        │
                        └──→ update_component_master_bom_fields()
                                  │
                                  └──→ Sets active_bom = new BOM
```

---

### Feature: Procurement Records Backfill (2026-02-03)

#### Overview

Added procurement history backfill to the "Update Component Data" button on Project form. This scans existing MRs, RFQs, POs, and PRs and populates the `procurement_records` child table on Component Masters.

#### Updated Workflow

**"Update Component Data" button now performs:**
1. ✅ Cascade `machine_code` from root Component Masters to children
2. ✅ Rebuild BOM Usage tables (with duplicate item consolidation)
3. ✅ **NEW:** Backfill procurement records (MR, RFQ, PO, PR)
4. ✅ Recalculate quantities and update procurement status

#### Implementation

**New function `backfill_procurement_records(project)`:**
Location: `project_component_master/utils.py:180-298`

```python
def backfill_procurement_records(project):
    """
    Backfill procurement records for all Component Masters in a project.
    Scans existing MRs, RFQs, POs, and PRs and adds them to Component Master procurement_records.

    This is idempotent - existing records are skipped.
    """
    # Document types with their field configurations
    # (doctype, item_doctype, date_field, has_rate, project_field)
    doc_types = [
        ("Material Request", "Material Request Item", "transaction_date", False, "project"),
        ("Request for Quotation", "Request for Quotation Item", "transaction_date", False, "project_name"),
        ("Purchase Order", "Purchase Order Item", "transaction_date", True, "project"),
        ("Purchase Receipt", "Purchase Receipt Item", "posting_date", True, "project"),
    ]
    ...
```

**Key points:**
- **Idempotent:** Checks if record already exists before adding (no duplicates)
- **Field differences handled:**
  - RFQ Item uses `project_name` instead of `project`
  - MR/RFQ items don't have `rate` field
  - Purchase Receipt uses `posting_date` instead of `transaction_date`
- **Records added include:**
  - `document_type`, `document_name`, `quantity`, `rate`, `amount`
  - `date`, `status`, `procurement_source`, `bom_version`

#### Updated Summary Message

```
✓ Roots processed: X
✓ Machine codes updated: X Component Masters
✓ BOM usage rebuilt: X BOMs
✓ Procurement records added: X (skipped Y existing)  ← NEW
```

#### Files Modified

- `project_component_master/utils.py`:
  - Added `backfill_procurement_records()` function
  - Updated `update_component_data()` to call backfill as Step 5
  - Updated summary message and return dict

---

### Feature: BOM Version Change Diff Display (2026-02-03)

#### Overview

When BOM structure changes are detected during upload, the confirmation dialog now shows exactly what changed:
- **+ Added:** Items new to the BOM (green)
- **- Removed:** Items no longer in the BOM (red)
- **~ Qty Changed:** Items with quantity changes showing old → new (yellow)

#### Implementation

**New function `calculate_bom_diff(old_bom_name, new_children)`:**
Location: `bom_upload/bom_upload_enhanced.py` (after `calculate_tree_structure_hash`)

```python
def calculate_bom_diff(old_bom_name, new_children):
    """
    Calculate diff between old BOM and new tree children.
    Shows what items were added, removed, or had qty changes.

    Returns:
        dict: {
            "added": [{"item_code": str, "qty": float}, ...],
            "removed": [{"item_code": str, "qty": float}, ...],
            "qty_changed": [{"item_code": str, "old_qty": float, "new_qty": float}, ...]
        }
    """
```

**Key points:**
- Only calculated for BOMs detected as "changed" (hash mismatch)
- Consolidates duplicate items before comparison
- Minimal performance impact (~100-200ms for 5 changed BOMs)

#### Files Modified

- `bom_upload/bom_upload_enhanced.py`:
  - Added `calculate_bom_diff()` function
  - Updated `_determine_component_status()` to include `bom_diff` in "changed" status details

- `bom_upload/bom_upload.js`:
  - Updated `_show_confirmation_dialog()` to display the diff with color-coded changes

#### Remarks Storage

When user confirms BOM version changes:
1. **Immediate storage:** `version_change_remarks` field on Project Component Master
2. **Version history:** `change_remarks` field in `bom_version_history` child table

---

### Phase 5G: Multi-Level Make/Buy Cascade Recalculation & Validation (2026-02-03)

**Context:**
During production use, discovered critical issues with BOM quantity calculations in multi-level hierarchies when Make/Buy flags are changed, particularly for components at level 2 and below.

#### Issue 1: BOM Hash Comparison with Inactive BOMs (Identified, Not Fixed)

**Problem Discovery:**
In `bom_upload_enhanced.py:736-779`, when `component_master.active_bom` is set, the code directly uses that BOM reference for hash comparison **without verifying if the BOM is still active** (`is_active=1`).

**Root Cause:**
- `active_bom` field in Project Component Master is a stored reference
- Gets set when BOM is first linked
- **Is NOT automatically cleared** when that BOM is deactivated
- Can point to an old, inactive BOM version

**Impact:**
- When BOM is deactivated (e.g., during version change), `active_bom` still points to the old BOM
- Hash comparison uses the **inactive BOM's hash** instead of the current active BOM
- Upload incorrectly reports "unchanged" even when BOM structure has changed

**Code Location:**
```python
# bom_upload_enhanced.py:736-779
# When component_master.active_bom IS SET, uses it directly:
existing_hash = frappe.db.get_value(
    "BOM", component_master.active_bom, "custom_bom_structure_hash"
)
# ❌ No check if this BOM is still is_active=1!
```

**Correct Logic:**
Lines 657-682 show the correct approach - when `active_bom` is NULL, it searches for `is_active=1` BOMs.

**Recommendation:**
Before using `component_master.active_bom` for hash comparison, verify:
```python
if component_master.active_bom:
    bom_status = frappe.db.get_value(
        "BOM", component_master.active_bom,
        ["is_active", "is_default", "docstatus"],
        as_dict=True
    )
    if not bom_status or bom_status.is_active != 1:
        # Search for current active BOM instead
        component_master.active_bom = frappe.db.get_value(...)
```

**Status:** ⚠️ Identified but not fixed (user requested not to touch BOM upload code at this time)

---

#### Issue 2: Multi-Level Hierarchy Calculation Using Wrong Parent Field

**Problem Discovery:**
When switching a level 2+ component from "Buy" to "Make", child quantities were not updating correctly.

**Example Hierarchy:**
```
Level 1: M00000027264 (Make, total_qty_limit=1.00)
  └─ Level 2: G00000054189 (Make, total_qty_limit=0.00) ← Should be 1.00!
       └─ Level 3: A00000006515 (bom_qty_required=0.00) ← Should be 14.00!
```

**Root Cause:**
In `project_component_master.py:calculate_bom_qty_required()`, the calculation used `parent.project_qty`:

```python
# OLD (WRONG):
usage.total_qty_required = (usage.qty_per_unit or 0) * (parent.project_qty or 0)
```

**Problem:**
- For level 1 components: `project_qty` is set from Excel (e.g., 1.00) ✓
- For level 2+ components: `project_qty` is always 0.00 (by design in `bom_upload_enhanced.py:468`) ❌
- Formula: `14 × 0.00 = 0.00` → Wrong!

**Solution:**
Use `parent.total_qty_limit` instead, which is `MAX(project_qty, bom_qty_required)`:

```python
# NEW (CORRECT):
usage.total_qty_required = (usage.qty_per_unit or 0) * (parent.total_qty_limit or 0)
```

**Why This Works:**
- Level 1: `total_qty_limit = project_qty` (from Excel)
- Level 2: `total_qty_limit = MAX(0, bom_qty_required)` where `bom_qty_required` is calculated from parent
- Level 3: `total_qty_limit` cascades down from level 2

**Files Modified:**
- `clevertech/clevertech/doctype/project_component_master/project_component_master.py:106-152`
  - Changed calculation in `calculate_bom_qty_required()` to use `total_qty_limit`
  - Updated docstring to document the change

**Status:** ✅ Fixed (2026-02-03)

---

#### Issue 3: Non-Recursive Recalculation (One Level Deep)

**Problem Discovery:**
When changing a component's Make/Buy flag, only **direct children** were recalculated. Grandchildren and deeper levels were not updated.

**Example:**
```
Change M00000027264 from Buy → Make:
  ✓ G00000054189 (level 2) gets recalculated
  ✗ A00000006515 (level 3) does NOT get recalculated
```

**Root Cause:**
`recalculate_children_bom_qty()` only iterated through direct children and did not recurse deeper.

**Solution:**
Implemented **recursive recalculation** with safety measures:

```python
def recalculate_children_bom_qty(self, recursive=False, _depth=0, _processed=None):
    # Safety: Max depth limit (10 levels)
    if _depth > MAX_DEPTH:
        frappe.log_error(...)
        return 0

    # Safety: Circular reference detection
    if self.name in _processed:
        return 0

    # Process children...
    for child in children:
        # Recalculate this child
        child_doc.calculate_bom_qty_required()

        # Recursively recalculate grandchildren if child has BOM
        if recursive and child_doc.has_bom and child_doc.active_bom:
            child_affected = child_doc.recalculate_children_bom_qty(
                recursive=True,
                _depth=_depth + 1,
                _processed=_processed
            )
```

**Safety Features:**
1. **Depth Limit:** Maximum 10 levels (prevents runaway recursion)
2. **Circular Reference Detection:** Tracks processed items in a set
3. **Single Commit:** Only commits at root level (_depth=0)
4. **Error Logging:** Logs if depth limit is exceeded

**Performance:**
- Typical BOM depth: 3-5 levels
- Recursion stops automatically when leaf items (no BOM) are reached
- G00000054189 example: Processed 103 child components in <2 seconds

**Files Modified:**
- `clevertech/clevertech/doctype/project_component_master/project_component_master.py:154-197`
  - Made `recalculate_children_bom_qty()` recursive
  - Added depth tracking and circular reference protection

**Status:** ✅ Fixed (2026-02-03)

---

#### Issue 4: User Feedback and Validation

**Problem:**
Users had no visibility into what was happening during Make/Buy changes. Particularly confusing when changing a component to "Make" while parent was "Buy" (resulting in zero quantities).

**Solution 1: Warning When Parent is "Buy"**

Added validation in `before_save()` that checks if changing to "Make" but all parents are "Buy":

```python
def _validate_make_with_buy_parents(self):
    # Check all parents' Make/Buy status
    all_parents_buy = all(p["make_or_buy"] == "Buy" for p in parent_statuses)

    if all_parents_buy:
        frappe.msgprint(
            msg="Warning: Changing to Make but parent is Buy. "
                "This component and children will have zero quantities...",
            title="Make/Buy Configuration Warning",
            indicator="orange"
        )
```

**Message Shows:**
- Which parent assemblies are "Buy"
- Impact: Zero procurement quantities
- Recommendation: Change parent to "Make" first

**Solution 2: Recalculation Progress Messages**

Added three-stage messaging during recalculation:

1. **Blue Info (Start):**
   ```
   Make/Buy changed from Buy to Make for G00000054189.
   Triggering recursive recalculation for all child components...
   ```

2. **Green Success (Normal):**
   ```
   Successfully recalculated quantities for 103 child component(s).
   ```

3. **Orange Note (Zero Quantities):**
   ```
   Recalculated 103 child component(s).

   Note: All quantities set to zero because parent assembly is Buy.
   Child procurement is covered by parent's procurement.
   ```

**Context-Aware Logic:**
- If `total_qty_limit=0` after recalculation → Orange message explaining why
- If `total_qty_limit>0` → Green success message

**Files Modified:**
- `clevertech/clevertech/doctype/project_component_master/project_component_master.py:27-69`
  - Added `_validate_make_with_buy_parents()` validation
- `clevertech/clevertech/doctype/project_component_master/project_component_master.py:71-104`
  - Added context-aware user feedback messages

**Status:** ✅ Fixed (2026-02-03)

---

#### Testing Results

**Test Case 1: Multi-Level Hierarchy with Root "Make"**
```
Before:
  Level 1: D00000084229 (Make, total_qty_limit=1.00)
  Level 2: A00000000479 (bom_qty_required=0.00) ← Wrong

After Fix:
  Level 1: D00000084229 (Make, total_qty_limit=1.00)
  Level 2: A00000000479 (bom_qty_required=6.00) ✓ Correct!
```

**Test Case 2: Multi-Level Hierarchy with Root "Buy"**
```
Before:
  Level 1: M00000027264 (Buy, total_qty_limit=1.00)
  Level 2: G00000054189 (Make, total_qty_limit=0.00) ← Correctly zero
  Level 3: A00000006515 (bom_qty_required=0.00) ← Correctly zero

After changing M00000027264 to "Make":
  Level 1: M00000027264 (Make, total_qty_limit=1.00)
  Level 2: G00000054189 (Make, total_qty_limit=1.00) ✓ Auto-updated!
  Level 3: A00000006515 (bom_qty_required=14.00) ✓ Auto-updated!
```

**Test Case 3: Changing Level 2 to "Make" While Parent is "Buy"**
```
Action: Change G00000054189 to "Make" (parent M00000027264 still "Buy")

Messages Shown:
  1. Orange Warning: "Parent M00000027264 is Buy..."
  2. Blue Info: "Triggering recursive recalculation..."
  3. Orange Note: "All quantities set to zero because parent is Buy"

Result: All children correctly have zero quantities (as expected)
```

**Test Case 4: Recursive Depth**
```
G00000054189 has 103 total components across multiple levels
Action: Change Make/Buy flag

Result:
  - Recalculated 103 components recursively
  - Completed in <2 seconds
  - No errors, no circular reference issues
```

---

#### Business Impact

**Before Fixes:**
- Level 2+ component quantities incorrectly calculated
- Manual intervention required to update all descendant quantities
- Risk of procurement errors due to incorrect total_qty_limit

**After Fixes:**
- Automatic cascade recalculation for entire BOM hierarchy
- Clear user feedback about what's happening and why
- Warnings prevent user confusion when parent is "Buy"
- Consistent quantities across all levels

**Performance:**
- Recursive recalculation is fast (<2 seconds for 103 components)
- Safety measures prevent infinite loops
- Single commit at root level reduces database overhead

---

**Files Modified:**
1. `clevertech/clevertech/doctype/project_component_master/project_component_master.py`
   - `calculate_bom_qty_required()`: Use `total_qty_limit` instead of `project_qty`
   - `recalculate_children_bom_qty()`: Made recursive with safety measures
   - `_validate_make_with_buy_parents()`: New validation method
   - `before_save()`: Added validation call
   - `on_update()`: Added context-aware user feedback

**Database Changes:** None (logic changes only)

**Dependencies:** None (uses existing Frappe/ERPNext APIs)

---

### Decision 18: M-Code and G-Code Hierarchy Mapping (2026-02-04)

#### Background: BOM Hierarchy Structure

The engineering BOM follows a fixed hierarchy under each Machine Code:

```
Machine Code (SolidWorks ID)     → P0000000003033
    └── M-Code (Root Assembly)   → M001 (item_code starts with "M")
        ├── G-Code (Sub-Assembly) → G001 (item_code starts with "G")
        │   ├── D-Code            → D001
        │   └── Raw Material      → A001
        └── G-Code (Sub-Assembly) → G002 (item_code starts with "G")
            └── Raw Material      → A001  ← Same item under multiple G-codes!
```

**Key Points:**
- **Machine Code**: SolidWorks ID (e.g., P0000000003033) - stored at header level
- **M-Code**: Root assembly under machine, item_code starts with "M"
- **G-Code**: Sub-assembly under M-code, item_code starts with "G"
- **D-Code/Raw Materials**: Components under G-codes (various prefixes: D, A, etc.)
- **No nested G-codes**: G-codes are NOT nested under other G-codes

#### Problem: Multi-Parent Items

A raw material (e.g., A001) can appear under **multiple G-codes**:
- A001 under G001 → M-Code: M001, G-Code: G001
- A001 under G002 → M-Code: M001, G-Code: G002

The Project Tracking Report needs to show **ALL** G-code mappings for such items, not just one.

**Current Limitation:**
The header-level `parent_component` field only stores ONE parent, losing the multi-parent information.

#### Solution: Store M-Code and G-Code at Multiple Levels

**1. bom_usage Child Table (for items with parents)**

Each row in `bom_usage` represents one usage path. Add fields to track the hierarchy:

| Field | Type | Purpose |
|-------|------|---------|
| `parent_bom` | Link → BOM | Existing: The parent BOM |
| `parent_item` | Link → Item | Existing: Parent item (fetched from BOM) |
| `parent_component` | Link → PCM | NEW: Parent Component Master (for traversal) |
| `m_code` | Data | NEW: M-code for this usage path |
| `g_code` | Data | NEW: G-code for this usage path |
| `qty_per_unit` | Float | Existing: Qty per unit of parent |

**Example for A001 (multi-parent):**

| parent_bom | parent_component | m_code | g_code | qty_per_unit |
|------------|------------------|--------|--------|--------------|
| BOM-G001 | PCM-G001-xxx | M001 | G001 | 2.0 |
| BOM-G002 | PCM-G002-xxx | M001 | G002 | 1.0 |

**2. Header Level (for items WITHOUT bom_usage)**

Items at the root or without parent BOMs need m_code and g_code at header:

| Item Type | Has bom_usage? | m_code | g_code |
|-----------|----------------|--------|--------|
| M001 (M-code itself) | No | M001 | NULL |
| G001 (G-code itself) | Yes (under M001) | M001 | G001 |
| A001 (raw material) | Yes (multiple) | Use bom_usage | Use bom_usage |
| Loose item (manual) | No | Set manually | Set manually |

#### Data Model Changes

**1. Component BOM Usage (Child Table) - Add Fields:**
```json
{
  "fieldname": "parent_component",
  "fieldtype": "Link",
  "options": "Project Component Master",
  "label": "Parent Component",
  "description": "Component Master of the parent item (for hierarchy traversal)"
},
{
  "fieldname": "m_code",
  "fieldtype": "Data",
  "label": "M-Code",
  "read_only": 1,
  "description": "Root assembly code (derived from hierarchy)"
},
{
  "fieldname": "g_code",
  "fieldtype": "Data",
  "label": "G-Code",
  "read_only": 1,
  "description": "Sub-assembly code (derived from hierarchy)"
}
```

**2. Project Component Master (Header) - Add Fields:**
```json
{
  "fieldname": "m_code",
  "fieldtype": "Data",
  "label": "M-Code",
  "description": "Root assembly code (for items without bom_usage)"
},
{
  "fieldname": "g_code",
  "fieldtype": "Data",
  "label": "G-Code",
  "description": "Sub-assembly code (for items without bom_usage or single-parent items)"
}
```

#### Population Logic

**When populating bom_usage (in bom_hooks.py):**

```python
def add_or_update_bom_usage(project, item_code, parent_bom, qty_per_unit, parent_item=None):
    # Get parent Component Master
    if not parent_item and parent_bom:
        parent_item = frappe.db.get_value("BOM", parent_bom, "item")

    parent_cm = get_component_master(project, parent_item)
    parent_component = parent_cm.name if parent_cm else None

    # Derive M-code and G-code from parent hierarchy
    m_code, g_code = derive_codes_from_parent(parent_cm, parent_item)

    # Add/update bom_usage row with all fields
    component_master.append("bom_usage", {
        "parent_bom": parent_bom,
        "parent_component": parent_component,
        "m_code": m_code,
        "g_code": g_code,
        "qty_per_unit": qty_per_unit
    })

def derive_codes_from_parent(parent_cm, parent_item):
    """
    Derive M-code and G-code based on parent item.

    Rules:
    - If parent starts with "M" → m_code = parent, g_code = NULL
    - If parent starts with "G" → m_code = parent's m_code, g_code = parent
    - Otherwise → traverse parent_component chain to find nearest M and G
    """
    if not parent_item:
        return None, None

    if parent_item.startswith("M"):
        return parent_item, None
    elif parent_item.startswith("G"):
        # Parent is G-code, get M-code from parent CM's m_code or traverse
        m_code = parent_cm.m_code if parent_cm else None
        return m_code, parent_item
    else:
        # Parent is below G-level, traverse up
        return traverse_for_codes(parent_cm)
```

#### Implementation: Hierarchy Population (bom_upload_enhanced.py)

**Flow during BOM Upload:**

```
create_boms_and_link_components()
    ├── create_bom_recursive()           # Bottom-up BOM creation
    ├── _link_boms_to_component_masters() # Set active_bom reference
    │       └── populate_bom_usage_tables()  # Populate bom_usage with parent_bom, qty
    ├── _populate_hierarchy_codes()       # NEW: Populate parent_component, m_code, g_code
    └── recalculate_component_masters()   # Update qty calculations
```

**`_populate_hierarchy_codes(project, only_missing=True)`** in `bom_upload_enhanced.py`:

- Runs AFTER BOMs are linked (so hierarchy is complete)
- Only updates CMs where `parent_component`, `m_code`, or `g_code` is NULL
- Uses `_find_parent_item_via_bom()` to find parent from BOM structure
- Derives codes based on item prefix:
  - If item starts with "M" → m_code = item, g_code = NULL
  - If item starts with "G" → m_code from parent, g_code = item
  - Otherwise → inherit m_code and g_code from parent CM

**`add_or_update_bom_usage()` in `bom_hooks.py`:**

Now populates all hierarchy fields in each bom_usage row:

```python
component_master.append("bom_usage", {
    "parent_bom": parent_bom,
    "parent_component": parent_component,  # Link to parent CM
    "m_code": m_code,                      # Derived from hierarchy
    "g_code": g_code,                      # Derived from hierarchy
    "qty_per_unit": qty_per_unit
})
```

**`_derive_codes_from_parent(parent_cm, parent_item)`:**

```python
# If parent starts with "M" → m_code = parent, g_code = NULL
if parent_item.startswith("M"):
    return parent_item, None

# If parent starts with "G" → m_code from parent CM, g_code = parent
if parent_item.startswith("G"):
    m_code = parent_cm.m_code or _traverse_for_m_code(parent_cm)
    return m_code, parent_item

# Otherwise → traverse parent_component chain
m_code = parent_cm.m_code or _traverse_for_m_code(parent_cm)
g_code = parent_cm.g_code or _traverse_for_g_code(parent_cm)
return m_code, g_code
```

#### Implementation: Project Tracking Report

**Key Concept: One row per BOM usage path (not per Component Master)**

For multi-parent items (A001 under G001 and G002), the report shows **SEPARATE ROWS**:

```
M001 | G001 | A001 | 10 | MR-001 | 10 | ...  (from BOM-D001)
M001 | G002 | A001 | 5  | MR-002 | 3  | ...  (from BOM-D002)
```

**Report Data Source:**

```python
def get_data(filters):
    # 1. Get all bom_usage rows - one row per M-code/G-code path
    bom_usage_rows = frappe.db.sql("""
        SELECT
            cbu.parent as component_master,
            cbu.parent_bom,
            cbu.m_code,
            cbu.g_code,
            cbu.qty_per_unit,
            cbu.total_qty_required,
            pcm.item_code, pcm.item_name, ...
        FROM `tabComponent BOM Usage` cbu
        INNER JOIN `tabProject Component Master` pcm ON pcm.name = cbu.parent
        WHERE pcm.project = %(project)s
    """)

    # 2. Get CMs WITHOUT bom_usage (M-codes themselves, loose items)
    cms_without_bom_usage = frappe.db.sql("""
        SELECT pcm.name, pcm.m_code, pcm.g_code, ...
        FROM `tabProject Component Master` pcm
        WHERE NOT EXISTS (SELECT 1 FROM `tabComponent BOM Usage` cbu WHERE cbu.parent = pcm.name)
    """)

    # 3. Combine all rows
    all_rows = bom_usage_rows + cms_without_bom_usage
```

**Procurement Tracking per BOM Path:**

```python
def get_procurement_data_by_bom(project):
    """
    Fetch procurement data keyed by (item_code, bom_no).

    Linkage:
    - MR Item.bom_no = parent D-code's BOM (set via "Get Items from BOM")
    - bom_usage.parent_bom = same D-code's BOM
    - Match: MR Item.bom_no = bom_usage.parent_bom
    """
    # Query MR Items with bom_no
    mr_items = frappe.db.sql("""
        SELECT mri.item_code, mri.bom_no, mri.qty, mr.name as mr_no
        FROM `tabMaterial Request Item` mri
        INNER JOIN `tabMaterial Request` mr ON mr.name = mri.parent
        WHERE mri.project = %(project)s AND mr.docstatus = 1
    """)

    # Key by (item_code, bom_no) tuple
    for item in mr_items:
        key = (item.item_code, item.bom_no)
        result["mr"][key] = {"doc_names": [...], "qty": X}

    # Chain: MR → PO (via material_request_item) → PR (via purchase_order_item)
```

#### Files Modified

1. **component_bom_usage.json** - Added `parent_component`, `m_code`, `g_code` fields ✅
2. **project_component_master.json** - Added `m_code`, `g_code` fields to header ✅
3. **bom_hooks.py** - Updated `add_or_update_bom_usage()` with `_derive_codes_from_parent()` ✅
4. **bom_upload_enhanced.py** - Added `_populate_hierarchy_codes()` function ✅
5. **project_tracking.py** - Complete rewrite for per-BOM-path tracking ✅

#### Status

- [x] Design documented (2026-02-04)
- [x] `parent_component`, `m_code`, `g_code` fields added to Component BOM Usage
- [x] `m_code`, `g_code` fields added to Project Component Master header
- [x] Population logic in bom_hooks.py (`add_or_update_bom_usage`, `_derive_codes_from_parent`)
- [x] Hierarchy population in bom_upload_enhanced.py (`_populate_hierarchy_codes`)
- [x] Project Tracking Report rewritten for per-BOM-path rows with per-path procurement
- [ ] Backfill function for existing data (use `_populate_hierarchy_codes(project, only_missing=False)`)

---

**Document Version:** 3.4
**Last Updated:** 2026-02-04
**Authors:** Saket-TT & BharatBodh Team
**Status:** Phases 1–4H Complete ✅ (including Make/Buy flag, ALL items scope, three-layer validation MR+RFQ+PO, basic BOM version warning, cascade recalculation, tiered blocking during BOM Upload, BOM version history tracking, image upload enhancement, comprehensive summary, and dynamic column mapping with Excel format validation). Phase 5 Machine Code implementation complete ✅, BOM Hash Comparison RCA documented (fix pending), Component Master calculation issues fixed ✅ (frappe.db.set_value() approach, project_qty logic, cascade recalculation), BOM Usage bug fixes complete ✅ (version change cleanup, existing BOMs handling, duplicate item consolidation), Procurement records backfill feature complete ✅, BOM diff display in confirmation dialog complete ✅. **Phase 5G Multi-Level Make/Buy Cascade complete ✅** (total_qty_limit calculation fix, recursive recalculation with safety measures, user feedback and validation). **Decision 18: M-Code/G-Code Hierarchy Mapping complete ✅** (bom_usage hierarchy fields, _populate_hierarchy_codes in BOM upload, Project Tracking Report per-BOM-path rows with per-path procurement tracking). Phases 5 (Reports) and 6 (Testing) pending.
