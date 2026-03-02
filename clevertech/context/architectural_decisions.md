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

### Decision 19: G-Code State Filtering (Non-Released Design Exclusion)

**Problem:** During BOM Upload, Excel file may contain G-code assemblies (designs) that are not yet released for production. Processing unreleased designs would:
- Create Items, BOMs, and Component Masters for incomplete/draft designs
- Allow procurement for designs still under development
- Clutter the system with work-in-progress assemblies

**Business Requirement:** Only process G-code assemblies where STATE column (column J in Excel) = "RELEASED". Exclude all unreleased designs and their entire child component trees.

**Decision:**
- Implement tree filtering AFTER parsing but BEFORE analysis/creation
- Filter criterion: G-codes with `STATE != "RELEASED"` (or blank) are excluded
- Scope: Only G-codes are checked (not M-codes or A-codes)
- Impact: When a G-code is filtered out, its entire subtree (all children) is excluded
- User notification: Show orange msgprint with list of skipped G-codes and total items excluded

**Implementation:**
- Function: `filter_tree_by_g_code_state(tree)` in `bom_upload_enhanced.py` (lines 619-692)
- Called at line 239 after `build_tree()` and before `analyze_upload()`
- Returns: `(filtered_tree, skipped_info)` where skipped_info contains count and details
- STATE values are case-insensitive (converted to uppercase for comparison)

**Example:**
```
Excel contains:
G00000012345 - STATE: "RELEASED" → ✅ Processed (and all children)
G00000067890 - STATE: "DRAFT"    → ❌ Skipped (entire subtree excluded)
G00000099999 - STATE: (blank)    → ❌ Skipped (treated as not released)
M00000011111 - STATE: (any)      → ✅ Processed (M-codes not filtered by STATE)
```

**Rationale:**
- G-codes represent assembly designs with STATE lifecycle (Draft → Released → Obsolete)
- M-codes and A-codes are manufactured/purchased parts with different workflow
- Filtering at tree level (before Item creation) prevents database pollution
- Entire subtree exclusion prevents orphaned child components

**Trade-offs:**
- ✅ Clean separation of released vs unreleased designs
- ✅ Prevents accidental procurement of draft designs
- ❌ Cannot partially import a G-code (all-or-nothing per G-code)
- ❌ User must ensure STATE column is populated correctly in Excel

**Status:** ✅ Implemented (2026-02-10 documentation update)

---

### Decision 20: G-Code Level Procurement Validation

**Problem:** Current procurement validation (Material Request / Purchase Order) validates against Component Master's `total_qty_limit`, which is the SUM across ALL G-code assemblies in a machine. When procuring for a specific G-code assembly via "Get Items from BOM", this allows over-procurement for one G-code at the expense of others.

**Example:**
```
Item: Screw-M5 in Machine M99999999
├── Used in G12345678: needs 60 units
└── Used in G87654321: needs 40 units
Component Master total_qty_limit: 100

Current behavior: Can procure 100 for G12345678 alone ❌
Desired behavior: Max 60 for G12345678, Max 40 for G87654321 ✅
```

**Decision:**
Implement **three-layer validation** for procurement:
1. **Machine-code filter** (already implemented - Bug 1 fix 2026-02-09)
2. **G-code filter** (NEW) - validate against specific G-code's aggregate limit
3. **Quantity validation** (already implemented)

**Technical approach:**
- Use existing `g_code` field in `Component BOM Usage` child table (from Decision 18)
- When MR has `bom_no` field populated (from "Get Items from BOM"):
  - Extract G-code from BOM's item field
  - Filter bom_usage rows where `g_code = <selected_g_code>`
  - Sum `total_qty_required` for all matching rows
  - Validate against this G-code-specific limit
- Fallback to CM-level `total_qty_limit` for manual MRs without BOM reference

**Why g_code field works:**
- G-code propagates through ALL nesting levels (D → D → D → ...)
- Logic in `_derive_codes_from_parent()` (bom_hooks.py lines 947-991):
  - First D-code under G-code inherits: `g_code = G12345678`
  - Subsequent D-codes inherit from parent CM
  - Fallback: `_traverse_for_g_code()` walks up hierarchy if needed
- Result: All items under G12345678 have `g_code = "G12345678"` in their bom_usage rows

**Works with both fetch modes:**
- `fetch_exploded = 1` (all leaf items): ✅ Leaf items inherit g_code through chain
- `fetch_exploded = 0` (level 1 only): ✅ Direct children have g_code set

**No additional field needed:**
- Question: Should we add `g_code_qty_limit` to bom_usage?
- Answer: ❌ No - `total_qty_required` already serves this purpose
- Reason: Same item can appear in multiple paths under one G-code → need to sum anyway
- Performance: Summing is O(n) where n < 10 typically (negligible)

**Implementation:**
```python
# G-code filtering (NEW)
if mr_item.bom_no:
    g_code_item = frappe.db.get_value("BOM", mr_item.bom_no, "item")
    g_code_limit = sum(
        row.total_qty_required
        for row in component.bom_usage
        if row.g_code == g_code_item
    )
    qty_limit = g_code_limit if g_code_limit > 0 else component.total_qty_limit
else:
    qty_limit = component.total_qty_limit  # Manual MR fallback
```

**Files to modify:**
- `material_request_validation.py` (add G-code filter)
- `purchase_order_validation.py` (add G-code filter)

**Benefits:**
- ✅ More accurate - prevents over-allocation to one G-code
- ✅ Business-aligned - procurement tracks per-assembly limits
- ✅ Simple implementation - uses existing g_code field
- ✅ Backward compatible - fallback for manual MRs
- ✅ Works with any nesting depth - g_code propagates correctly

**Trade-offs:**
- ✅ Slightly more complex validation logic (one extra sum operation)
- ⚠️ Only effective when MR created via "Get Items from BOM" (has bom_no)
- ⚠️ Manual MRs still use CM-level limit (acceptable - manual entry is rare)

**Relationship to previous decisions:**
- Extends Decision 9 (MR validation hard-block) with G-code granularity
- Depends on Decision 18 (M-Code/G-Code Hierarchy Mapping) for g_code field
- Resolves deferred "Bug 3: BOM-Level Validation Gap" from 2026-02-09 fixes

**Status:** 📋 Design complete (2026-02-10), implementation pending approval

---

