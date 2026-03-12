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
✓ Root assemblies (M level)      — has_bom=1, make_or_buy=Make (default)
✓ Sub-assemblies (G level)       — has_bom=1, make_or_buy=Make (default)
✓ Sub-assemblies (D level)       — has_bom=1, make_or_buy=blank (ambiguous, user decides)
✓ Leaf D-code items (no BOM)     — has_bom=0, make_or_buy=Buy (default, 2026-03-05)
✓ Raw materials (RM/other level) — has_bom=0, make_or_buy=Buy (default)
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

**Scope: applies to ALL nodes, including leaf nodes (AL/RM items)**

The check runs on every node in the uploaded BOM tree — not just assembly nodes (M/G/D).
Raw material / purchased component items (e.g. AL codes) can also be marked `is_loose_item=1`
on the Project Component Master. If `can_be_converted_to_bom=0`, BOM creation is hard-blocked.

A blocked **leaf node** cascades upward: any parent assembly that depends on it is also blocked.

Code paths enforcing this (all three must be consistent):
| File | Function | Notes |
|---|---|---|
| `bom_upload_phase1.py` | `_check_loose_items()` | Used by "Create BOM - Phase 1" button. **Bug fixed:** previously skipped leaf nodes via `if not node.get("children"): continue` |
| `bom_upload_enhanced.py` | `analyze_upload()` | Runs leaf node loop separately after assembly loop |
| `bom_upload_enhanced.py` | `_proceed_with_confirmed_changes()` | Confirmation flow; **bug fixed:** previously had no loose check at all |

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

**Make/Buy Enforcement at MR & PO Level (2026-02-11):**

Both MR and PO validation hard-block "Make" items. The system uses two complementary guards:

| Guard | What it blocks | How |
|-------|---------------|-----|
| Make/Buy flag | Assemblies (M, G, D-Make) | `make_or_buy == "Make"` → `frappe.throw()` |
| total_qty_limit = 0 | RMs under Buy parent | Qty check: `total > 0` exceeds limit of 0 |

Together these cover every procurement scenario without needing parent-chain traversal:

| Item | make_or_buy | total_qty_limit | MR/PO allowed? | Reason |
|------|-------------|-----------------|----------------|--------|
| M-code (machine) | Make | any | NO | Make block |
| G-code (assembly) | Make | any | NO | Make block |
| D-code (Buy) | Buy | > 0 | YES | Buy with limit |
| D-code (Make) | Make | any | NO | Make block |
| RM under D (Buy parent) | Buy | 0 | NO | Zero limit |
| RM under D (Make parent) | Buy | > 0 | YES | Limit from BOM explosion |
| RM directly under G | Buy | > 0 | YES | Limit from BOM explosion |

Files: `material_request_validation.py` (line 78), `purchase_order_validation.py` (line 93)

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

**Status:** ✅ Implemented (2026-02-10) in `material_request_validation.py` and `purchase_order_validation.py`

---

### Decision 21: Topological Sort for CM Recalculation

**Problem:** `recalculate_component_masters_for_project()` processed Component Masters in arbitrary order (alphabetical by name). When Make/Buy changes cascade through a BOM hierarchy, child CMs were often processed BEFORE their parent CMs. This caused children to read stale `total_qty_limit` values (often 0) from parents, resulting in incorrect quantity calculations throughout the hierarchy.

**Example of the bug:**
```
1. Upload BOM: Machine M → G-code G → D-code D → Raw Material RM
2. Initial state: D is "Buy" → RM has total_qty_limit=0 (parent covers procurement)
3. User changes D to "Make" → triggers recalculation
4. BUG: If RM processed before D:
   - RM reads D's total_qty_limit (still 0 - not recalculated yet)
   - RM stays at 0 (incorrect)
5. Correct: Process D first, THEN RM:
   - D recalculates: total_qty_limit = 100
   - RM reads D's total_qty_limit = 100
   - RM correctly calculates: total_qty_limit = 100
```

**Decision:**
Implement **topological sorting** using Kahn's algorithm to ensure parent CMs are always processed before their children in the dependency graph.

**Technical implementation:**
```python
def _get_cms_in_topological_order(project):
    """Return CM names in topological order (parents before children)."""
    # 1. Build item_code → cm_name mapping
    cms = frappe.get_all("Project Component Master",
                        filters={"project": project},
                        fields=["name", "item_code"])
    item_to_cm = {cm["item_code"]: cm["name"] for cm in cms}

    # 2. Build dependency graph from bom_usage (child depends on parent)
    dependencies = {cm["name"]: set() for cm in cms}
    in_degree = {cm["name"]: 0 for cm in cms}

    bom_usages = frappe.db.sql("""
        SELECT parent AS child_cm, parent_item
        FROM `tabComponent BOM Usage`
        WHERE parent IN %(cm_names)s
    """, {"cm_names": list(cm_names)}, as_dict=True)

    for usage in bom_usages:
        child_cm = usage["child_cm"]
        parent_cm = item_to_cm.get(usage["parent_item"])
        if parent_cm and parent_cm in cm_names:
            dependencies[child_cm].add(parent_cm)
            in_degree[child_cm] += 1

    # 3. Kahn's algorithm: process nodes with in_degree=0 first
    queue = [cm for cm in cm_names if in_degree[cm] == 0]
    result = []

    while queue:
        queue.sort()  # Deterministic ordering
        current = queue.pop(0)
        result.append(current)

        for dependent in cm_names:
            if current in dependencies[dependent]:
                dependencies[dependent].remove(current)
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

    return result
```

**Why Kahn's algorithm:**
- ✅ Natural fit for dependency resolution (process nodes with no dependencies first)
- ✅ Handles cycles gracefully (returns partial order, logs remaining nodes)
- ✅ O(V + E) complexity - efficient for typical BOM hierarchies (V < 1000, E < 5000)
- ✅ Deterministic (sorted queue prevents random ordering)

**Benefits:**
- ✅ Fixes cascade recalculation bugs throughout the system
- ✅ Guarantees correct quantity calculations regardless of CM creation order
- ✅ Safe for production - no data loss, only ordering change
- ✅ Works with arbitrary BOM depths and multiple parents per item

**Trade-offs:**
- ⚠️ Slightly slower than simple alphabetical sort (negligible - milliseconds for 1000 CMs)
- ⚠️ Adds complexity to recalculation logic (well-documented, tested)

**Files modified:**
- `project_component_master/bom_hooks.py` lines 1202-1306

**Status:** ✅ Implemented and tested (2026-02-11)

---

### Decision 22: Machine Code vs Item Code Separation

**Problem:** Tests and potentially production code confused `machine_code` (a separate identifier for machine isolation) with `item_code` (the actual machine assembly item code). This caused CM lookups to fail or return incorrect CMs when the same item existed in multiple machines.

**Example of confusion:**
```
WRONG:
  MACHINE_1_CODE = "MT4000084237"  # This is an item_code, not a machine_code!

CORRECT:
  MACHINE_1_CODE = "VT0000000001"  # Actual machine identifier
  MACHINE_1_ITEM = "MT4000084237"  # Item code for the machine assembly
```

**Decision:**
Clarify and enforce the separation:
- **`machine_code`**: A unique identifier for a physical machine/production line (e.g., "VT0000000001", "P00000000023")
  - Used for CM isolation (filtering)
  - Stored on Cost Center and Component Master
  - Format: [V|P|etc.]T + 10 digits

- **`item_code`**: The ERPNext Item code for any component, including machines (e.g., "MT4000084237")
  - Used for Item/BOM lookups
  - Appears in BOM hierarchies
  - Format: [M|G|D|A|etc.]T + 10 digits

**Why this matters:**
1. **CM Isolation**: When same item (e.g., "AT0000012345") exists in multiple machines, we need `machine_code` to filter the correct CM
2. **Cost Center Linkage**: Material Requests link to Cost Center → derive `machine_code` → filter CMs correctly
3. **BOM Upload**: BOM upload receives `machine_code` as parameter, stamps all CMs with it

**Pattern for CM lookups:**
```python
# ALWAYS include machine_code filter when available
filters = {"project": project, "item_code": item_code}
if machine_code:
    filters["machine_code"] = machine_code

cm = frappe.db.get_value("Project Component Master", filters, ["field1", "field2"], as_dict=True)
```

**Files where this pattern is critical:**
- `project_component_master.py` (4 methods fixed with machine_code filters)
- `material_request_validation.py` (derives machine_code from Cost Center)
- `purchase_order_validation.py` (derives machine_code from Cost Center)
- `bom_upload_enhanced.py` (receives machine_code as parameter)

**Benefits:**
- ✅ Prevents cross-machine CM contamination
- ✅ Enables same item in multiple machines with independent quantity limits
- ✅ Clear conceptual model (machine identity vs. item identity)

**Trade-offs:**
- ⚠️ Requires discipline - developers must remember machine_code filtering pattern
- ⚠️ Legacy code may lack machine_code (fallback to project-only filter acceptable for single-machine projects)

**Status:** ✅ Clarified and enforced (2026-02-11), 4 methods fixed in project_component_master.py

---

## Decision: BOM Global Uniqueness + Machine-Level Retain Logic

**Date:** 2026-03-05
**Status:** ✅ Implemented (2026-03-05)

---

### Problem

BOMs were being created with `project` field set (e.g., `project=SO250038`). This caused a three-way inconsistency between the hash check, the duplicate guard, and BOM creation:

| Check | Project filter? |
|---|---|
| Hash check in `create_bom_recursive` | No — finds BOM from ANY project |
| `before_insert` hook in `bom.py` | Yes — only checks same project |
| BOM creation | Yes — tags BOM with current project |

**Bug this causes:**
```
1. Machine A uploads item G  → BOM-001 (project=A, hash=H1)
2. Machine B uploads same G, no change → hash finds BOM-001 (H1=H1) → skip → B CM links to BOM-001
3. Machine A changes G → BOM-002 (project=A, hash=H2) → now global active default
4. Machine B re-uploads, no design change (Excel still H1):
   hash finds BOM-002 (H2 != H1) → creates BOM-003  WRONG
   Machine B had no design change but got a new BOM version
```

---

### Decision 1: Global BOM Uniqueness

BOMs are shared catalog items, not project-specific. Remove project from BOM creation and from the duplicate guard. Hash check is already global — no change needed.

| | Before | After |
|---|---|---|
| BOM.project | Set to uploading project | Blank |
| Hash check | Global (unchanged) | Global (unchanged) |
| before_insert duplicate check | Per-project | Global |

Result: One canonical BOM per item. New version only created when structure genuinely changes, regardless of which machine triggers the upload.

---

### Decision 2: Machine-Level Retain Logic

**Problem after global uniqueness:** Machine A changes item → BOM-002 becomes global default. Machine B re-uploads with no design change → hash compares against BOM-002 (H2) → mismatch with Excel (H1) → unnecessarily creates BOM-003.

**Business rule (confirmed):** If Machine B's Excel structure matches what Machine B's CM already has (CM.active_bom hash), Machine B's design has not changed → retain current BOM, do not upgrade to global default, do not create new version.

**Hash check order (new):**
```
For each assembly node during Machine B upload:
  new_hash = MD5 of Excel children

  Step 1 — CM-level check (per-machine):
    cm_hash = hash on Machine B CM.active_bom
    If cm_hash == new_hash → Machine B design unchanged → RETAIN → skip

  Step 2 — Global check (unchanged from today):
    If global active BOM hash == new_hash → skip

  Step 3 — Neither match:
    Machine B design genuinely changed → create new BOM version (blank project)
```

CM.active_bom is the per-machine version reference. BOMs are global; each machine's CM independently tracks which version it is on.

**Why _link_boms_to_component_masters (Change 3) is also needed:**
Even if create_bom_recursive decides "retain" in step 7, _link_boms_to_component_masters runs in step 8 and would silently override it by assigning the global active BOM (BOM-002) to Machine B's CM. The retained_items set prevents this.

---

### Implementation: 4 Files, 4 Changes

**Change 1: bom_upload.py — create_bom_recursive()**
- Add optional parameter: cm_bom_hashes=None (dict of item_code -> hash)
- Before global hash check: compare cm_bom_hashes.get(item_code) with new_hash
  - If match → return "retain" (new return value, distinct from False)
- Remove "project": project from BOM doc creation
- Pass cm_bom_hashes through recursive child calls

**Change 2: bom_upload_phase1.py — _create_boms_for_tree() + main function**
- Before step 7: pre-load cm_bom_hashes from DB:
  - Get all CMs for this project+machine_code with has_bom=1
  - For each CM with active_bom set: fetch custom_bom_structure_hash from BOM
  - Build dict: {item_code: hash}
- Pass cm_bom_hashes into _create_boms_for_tree
- _create_boms_for_tree collects retained_items (items where result == "retain")
- Pass retained_items to _link_boms_to_component_masters

**Change 3: bom_upload_enhanced.py — _link_boms_to_component_masters()**
- Add optional parameter: retained_items=None (set of item_codes)
- If cm_data.item_code in retained_items → skip (do not update active_bom)
- Else → existing logic unchanged

**Change 4: bom.py — before_insert hook**
- Remove "project": doc.project from duplicate check filter
- Now checks ALL active BOMs globally (consistent with hash check)

---

### Return values from create_bom_recursive after change

| Return | Meaning |
|---|---|
| True | New BOM version created |
| False | Skipped — global hash matched or no children |
| "retain" | Skipped — CM current BOM matches Excel → retain per-machine version |

---

### Full Example After Fix

```
BOM-001 (global, blank project, hash=H1)
Machine A CM → BOM-001 | Machine B CM → BOM-001

Machine A changes item (hash=H2):
  Step 1: cm_hash(A)=H1 != H2 | Step 2: global H1 != H2 | Step 3: BOM-002 created (global, H2)
  Machine A CM → BOM-002

Machine B re-uploads, no design change (Excel hash=H1):
  Step 1: cm_hash(B)=H1 == new_hash=H1 → RETAIN
  No new BOM. _link_boms skips Machine B CM (in retained_items).
  Machine B CM stays on BOM-001

Machine B re-uploads later with change (Excel hash=H3):
  Step 1: cm_hash(B)=H1 != H3 | Step 2: global H2 != H3 | Step 3: BOM-003 created (global, H3)
  Machine B CM → BOM-003
  Machine A CM still on BOM-002 (unaffected until Machine A re-uploads)
```

---

### What Does NOT Change
- machine_code on CM — still used for CM isolation (procurement, MR, PO)
- project on CM — still set, still used for project scoping
- Hash calculation logic — same MD5, just with CM-level pre-check added before global check
- All other Phase 1 steps — items, hierarchy codes, recalculation unchanged
- Existing BOMs with project set — no migration needed, hash check finds them regardless

---

### Implementation Bugs Found and Fixed (2026-03-05)

**Bug 1: Stale hash — CM has bom_structure_hash but no active_bom**

Root cause: Step 5 (`create_component_masters_for_all_items`) pre-sets `bom_structure_hash`
on newly created CMs from the Excel tree, before any BOM is created. When Step 7 loaded
`cm_bom_hashes`, it included these new CMs → retain check fired → BOM creation skipped →
`active_bom` stayed None.

Fix: Only include CMs with `active_bom` set in `cm_bom_hashes`:
```python
cm_bom_hashes = {
    r.item_code: r.bom_structure_hash
    for r in cm_records
    if r.bom_structure_hash and r.active_bom  # active_bom guard added
}
```

**Bug 2: False-positive version change dialog in Step 6**

Root cause: `_scan_for_bom_version_changes` compared Excel hash vs global active BOM hash.
In the retain scenario (Machine A Excel=H1, global BOM=H2), it flagged H1≠H2 as a version
change → showed confirmation dialog even though this machine's design hadn't changed.

Fix: Load `cm_bom_hashes` before Step 6 (moved from before Step 7). Pass it to
`_scan_for_bom_version_changes`. Skip nodes where `cm_bom_hashes.get(item_code) == new_hash`.

**Bug 3: Cross-machine CM contamination in Step 8**

Root cause: `_link_boms_to_component_masters` fetched ALL CMs for the project (all machines).
When Machine A uploaded and created BOM-002, Step 8 updated Machine B's CM to BOM-002 too,
overwriting Machine B's independently tracked version.

Fix: Add `machine_code=None` parameter to `_link_boms_to_component_masters`. Phase 1 passes
`machine_code` so only the uploading machine's CMs are updated. The call from the full upload
flow (`bom_upload_enhanced.py`) passes no machine_code → unchanged behavior for that path.

---

### Pending Change Request: BOM Version History Not Updated

**Date raised:** 2026-03-05
**Status:** 🔲 Pending — not yet scoped or implemented

**Observation:** `bom_version_history` child table on CM is not being updated when BOM versions
change via Phase 1 upload. E.g. PCM-SMR260001-000638 shows only one history entry even though
active_bom changed from BOM-001 to BOM-003.

**Root cause:** `on_bom_submit` (in `bom_hooks.py`) calls `_handle_bom_version_change` and
`_add_initial_bom_version` to maintain version history. Since we removed `project` from BOM
docs (global uniqueness change), `on_bom_submit` now hits `if not doc.project: return` at
line 107 and exits before updating any CM. Version history is therefore never written.

**Considerations before implementing:**
- `_handle_bom_version_change` and `_add_initial_bom_version` use `get_component_master(project, item_code)` which has no `machine_code` filter. With multiple machines per item, it may update the wrong machine's CM.
- The call should be made from `_link_boms_to_component_masters` where the correct CM is already loaded — avoids the ambiguity.
- Must be wrapped in try/except so any failure is logged but never blocks the upload.
- Note: old BOMs are NOT "deactivated" — they just lose `is_default`. Only `is_current` on the history row changes.
- This was not part of the original change request — raise as a new CR before implementing.

---

### Non-Default Active BOM Not Recognised During First-Time CM Creation

**Date raised:** 2026-03-10
**Status:** ✅ Implemented (2026-03-10)

**Scenario (observed on a completed project):**
1. Item already has 4 BOMs in ERP — 1 default (BOM-004), 3 active non-default (BOM-001/002/003)
2. CMs do not exist yet — being created for the first time via BOM Upload
3. Excel BOM structure hash = hash of BOM-002 (active, non-default)
4. `_scan_for_bom_version_changes` compares Excel hash vs default BOM only (BOM-004) → mismatch → flags version change → shows confirmation dialog
5. User clicks Continue (expecting a new version to be created)
6. `create_bom_recursive` Step 2 checks default BOM hash only (BOM-004) → mismatch → tries to create new BOM
7. `before_insert` global duplicate guard (our change — no project filter) finds BOM-002 with identical structure → rejects as duplicate
8. G-code BOM not created → parent M-code BOM also blocked (correct cascade) → CMs end up with no BOM linked

**Root cause:**
Both `_scan_for_bom_version_changes` and `create_bom_recursive` Step 2 query `is_default=1` only.
They are blind to non-default active BOMs. The `before_insert` global guard is the only place that
looks globally — but it fires AFTER the decision to create has already been made, leaving the CM
with no BOM linked.

**Expected behaviour:**
When Excel hash matches a non-default active BOM:
- Do NOT flag as a version change (no dialog)
- Do NOT attempt to create a new BOM
- Link CM to the matching existing BOM (even though it is not the current default)

**Implementation — 5 changes across 3 files:**

1. **`bom_upload_phase1.py` — `_scan_for_bom_version_changes`**
   - Replaced `is_default=1` query with hash-based lookup across all `is_active=1` BOMs
   - If any active BOM matches Excel hash → no dialog (not a version change)
   - If no match → only flag as version change when a default BOM exists (to show "changing from X")
   - `ORDER BY creation DESC` ensures deterministic pick when multiple BOMs have same hash

2. **`bom_upload.py` — `create_bom_recursive`**
   - Before creating a new BOM, checks all `is_active=1` BOMs for a hash match
   - If match found → returns `("reuse", bom_name)` instead of proceeding to create
   - Prevents duplicate creation that `before_insert` would reject anyway

3. **`bom_upload_phase1.py` — `_create_boms_for_tree`**
   - Handles new `("reuse", bom_name)` return value from `create_bom_recursive`
   - Collects into `reuse_boms = {item_code: bom_name}` dict, counted as "skipped"
   - Passes `reuse_boms` back to Phase 1 main alongside `retained_items`

4. **`bom_upload_phase1.py` — Phase 1 main (Step 7→8)**
   - Extracts `reuse_boms` from `bom_counters`
   - Passes to `_link_boms_to_component_masters(reuse_boms=reuse_boms)`

5. **`bom_upload_enhanced.py` — `_link_boms_to_component_masters`**
   - New `reuse_boms=None` parameter
   - When `cm_data.item_code in reuse_boms` → uses that specific BOM name directly, bypasses default BOM query
   - Normal path (default BOM lookup) unchanged for all other items

**Fresh-project flow:** completely unaffected — `reuse_boms` is empty, all existing code paths unchanged.

---

## Decision: PO Cancel — Cascade to SQ Comparison and SQ

**Date:** 2026-03-11
**Status:** ✅ Implemented

### Problem
Cancelling a Purchase Order failed with a circular reference:
- User clicked Cancel on PO → ERPNext showed "Cancel All" dialog (SQ Comparison + SQ linked)
- User clicked Cancel All → ERPNext tried to cancel SQ → SQ checks back-links → finds PO still submitted → blocked
- After partial fix (cancel SQ Comparison in on_cancel) → new error: Frappe's `check_no_back_links_exist` found SQ (submitted) still referencing PO via `Supplier Quotation Item.purchase_order` → blocked PO cancellation

### Root Cause
Two separate issues:
1. **SQ Comparison** — custom doctype whose PO link lives in `tabSupplier Selection Item.purchase_order` (child row). ERPNext's standard Cancel All cannot discover child-row links → SQ Comparison never auto-cancelled.
2. **SQ** — standard doctype but Frappe's `check_no_back_links_exist` (runs in `run_post_save_methods`) blocks PO cancel if SQ is still submitted. ERPNext Cancel All tries to cancel SQ first but SQ was blocked by PO (circular).

### Key Frappe lifecycle insight
`on_cancel` fires **before** `check_no_back_links_exist` inside `run_post_save_methods`. Cancelling both SQ Comparison and SQ inside `on_cancel` means by the time Frappe does the back-link check, neither references a submitted PO.

### Solution
Added `on_cancel` function to `supply_chain/server_scripts/purchase_order.py`:
- Step 1: cancel all SQ Comparisons that reference this PO (via `tabSupplier Selection Item`)
- Step 2: cancel all SQs referenced by PO items (via `doc.items[].supplier_quotation`)
- Both check `docstatus == 1` before cancelling (idempotent)

Registered in `hooks.py` as a list alongside existing `procurement_hooks.on_po_cancel`:
```python
"on_cancel": [
    "clevertech.supply_chain.server_scripts.purchase_order.on_cancel",
    "clevertech.project_component_master.procurement_hooks.on_po_cancel",
],
```

Supply chain cancel runs first → procurement tracking cleanup runs second.

### UI gap — "Cancel All" dialog cancels linked docs before PO
After the server hook was in place, programmatic cancel (`po.cancel()`) worked but the UI still
failed. Root cause: Frappe's "Cancel All" button calls `cancel_all_linked_docs` which cancels
linked docs **first** (SQ before PO) → SQ blocked by PO still submitted → our hook never runs.

**Fix:** Set `frm.ignore_doctypes_on_cancel_all` in `public/js/purchase_order.js` `onload`:
```js
frm.ignore_doctypes_on_cancel_all = ["Supplier Quotation", "Supplier Quotation Comparison"];
```
This tells Frappe's UI to skip SQ and SQC from the "Cancel All" flow → PO cancels directly →
our `on_cancel` hook cascades to SQC and SQ in the correct order.

**Atomicity:** both hooks run inside the same DB transaction. If either cascade cancel fails,
the entire PO cancel rolls back.

**UX:** After cancel, a `frappe.msgprint(alert=True)` lists which SQ Comparison and SQ docs
were cancelled, so the user has visibility even though they no longer appear in the dialog.

---

### Decision N: BOM Upload Phase 1 — Background Job Architecture

**Status:** 🔲 Designed, not yet implemented

**Problem:** Large BOM upload files (e.g. SMR260016 — 1,306 rows) cause HTTP timeout during Phase 1 processing. The entire create_items + create_CMs + create_BOMs pipeline runs synchronously in a single HTTP request.

**Immediate fix (deployed):** `bench config http_timeout 600` + nginx/supervisor reload. Sufficient for current file sizes.

**Proper long-term fix — Background Job Wrapper:**

#### Python (3 new functions, existing code untouched)

1. **`create_boms_phase1_async(docname, confirmed, state_confirmed)`** — whitelisted, sync
   - Parses Excel + runs BOTH pre-checks (state warnings + BOM version scan) synchronously
   - Note: `_scan_for_bom_version_changes` is moved earlier here (reads-only, no writes) so both dialogs complete before enqueue
   - Once both confirmed → calls `frappe.enqueue(_run_phase1_bg, queue="long", timeout=600, docname=docname)`
   - Returns `{"status": "queued", "job_id": job.id}`

2. **`_run_phase1_bg(docname)`** — background worker (not whitelisted)
   - Calls `create_boms_phase1(docname, confirmed=1, state_confirmed=1)` — existing function, zero changes
   - Stores result in `frappe.cache().set_value(f"phase1_result_{docname}", result, expires_in_sec=3600)`
   - On exception: stores `{"status": "error", "error": str(e)}` in same cache key

3. **`get_phase1_async_status(job_id, docname)`** — whitelisted, sync polling endpoint
   - Uses `frappe.utils.background_jobs.get_job_status(job_id)` (Frappe v15 native)
   - If finished/failed → reads result from `frappe.cache().get_value(f"phase1_result_{docname}")`
   - Returns `{"status": "queued|started|finished|failed", "result": ...}`

#### JS (new button + polling, existing JS untouched)

- New button **"Create BOM - Phase 1 (Bg)"** alongside existing button
- Same confirmation dialog flow (state warning → version change) — handled by `create_boms_phase1_async`
- On `queued` response → disables button, shows "Processing in background..." indicator on form
- Polls `get_phase1_async_status` every 5 seconds via `setInterval`
- On `finished` → clears interval, renders same summary table as existing sync flow
- On `failed` → clears interval, shows error message

#### Key design decisions

| Decision | Choice | Reason |
|---|---|---|
| Existing `create_boms_phase1` touched? | **No** | Called as-is with `confirmed=1, state_confirmed=1` |
| Pre-check duplication? | Excel parsed twice (wrapper + bg job) | Acceptable — fast read vs heavy DB writes |
| Result storage | `frappe.cache()` (Redis, 1hr TTL) | No schema change needed, Frappe-native |
| Queue | `long` | Frappe's long queue for tasks > 300s |
| Frappe version compatibility | v15.91.1 — uses `frappe.utils.background_jobs.get_job_status()` | Confirmed available |

#### Trade-off Accepted
- Excel file parsed twice per run (wrapper for pre-checks, background job for processing)
- Two buttons on the form during transition period (sync for small files, async for large)
- Background job result not visible in Frappe's standard job monitor UI (stored in cache, surfaced via polling)

---

### Decision N: Row-ID Matching for Supply Chain Cross-Doctype Validation

**Problem:** Validation scripts (RFQ→MR, SQ→RFQ, PO→SQ) and the Supplier Quotation Comparison (SQC) doctype all used `{parent}_{item_code}` as a dict key for lookup maps. When the same item code appears multiple times in a document (e.g. two rows of the same item with different qtys in an MR), later rows silently overwrite earlier ones → wrong qty compared → validation failed incorrectly or rows were dropped.

The same collision affected:
- SQC `get_comparison_report_data()` — HTML table showed duplicate items collapsed into one
- SQC Supplier Selection Table — only 1 row populated instead of 2
- PO creation from SQC — second row silently dropped
- Script Report `supplier_quotation_comparison_report.py` — same collapse in report output

**Solution: Key all cross-doctype lookup maps by Frappe child row `name` (unique row ID)**

Every child table row has an auto-generated unique `name` field. ERPNext stores cross-doctype row references:

| Reference field | Points to |
|---|---|
| `RFQ Item.material_request_item` | `Material Request Item.name` |
| `SQ Item.request_for_quotation_item` | `RFQ Item.name` |
| `PO Item.supplier_quotation_item` | `SQ Item.name` |

**Files changed:**

| File | Key changed from | Key changed to |
|---|---|---|
| `supply_chain/server_scripts/request_for_quotation.py` | `{mr}_{item_code}` | `material_request_item` row name |
| `supply_chain/server_scripts/supplier_quotation.py` | `{rfq}_{item_code}` | `request_for_quotation_item` row name |
| `supply_chain/server_scripts/purchase_order.py` | `{sq}_{item_code}` | `supplier_quotation_item` row name |
| `clevertech/doctype/supplier_quotation_comparison/supplier_quotation_comparison.py` | `(item_code, material_request)` tuple | `rfq_item.name` row ID |
| `clevertech/doctype/supplier_quotation_comparison/supplier_quotation_comparison.js` | `${item_code}|${material_request}` rowKey | `__lowest_supplier__` embedded per dataRow |
| `clevertech/report/supplier_quotation_comparison_report/supplier_quotation_comparison_report.py` | `{rfq}_{item_code}` | `rfq_item.name` row ID |

New hidden fields added to child doctypes (required `bench migrate`):
- `supplier_selection_item.rfq_item_row` (Data, hidden)
- `comparison_table_item.rfq_item_row` (Data, hidden)

**Why not sum qtys per item_code?**
Summing would fix the reported validation failure but has an edge case: two rows with qty 5 and qty 3 would pass sum-level validation (total 8) even if one row had qty 10 (exceeding its individual MR row limit). Row-ID matching is precise and correct.

**Trade-off Accepted:** Requires `request_for_quotation_item` / `supplier_quotation_item` fields to always be populated — enforced by the strict MR → RFQ → SQ → SQC → PO workflow.

**Pattern for future reference:**
- **Never** key cross-doctype lookup maps by `{parent}_{item_code}` — breaks when same item appears multiple times
- **Always** key by the child row `name` field (unique Frappe row ID)
- Use the cross-doctype reference field (e.g. `request_for_quotation_item`) to match rows across doctypes


---

### Decision N: PO Cancel — SQC Workflow-Aware Cancellation

**Problem:** When a PO is cancelled, our `on_cancel` hook cancels the linked SQC and SQ. This worked when SQC had no workflow (direct `sqc.cancel()`). After a workflow ("SQC Approval Workflow Without Conditions") was added to SQC, `sqc.cancel()` left the document in an inconsistent state (docstatus=2 but `workflow_state` still "Approved").

**Solution:** Detect if an active workflow exists on SQC at runtime. If yes, use `frappe.model.workflow.apply_workflow(sqc, "Cancel")` which goes through the proper `Approved → Cancelled` workflow transition (and sets both `workflow_state` and `docstatus=2`). If no workflow, fall back to direct `sqc.cancel()`.

**File:** `supply_chain/server_scripts/purchase_order.py` — `on_cancel()`

**Key note:** SQ has no workflow, so `sq.cancel()` is unchanged.

---

### Decision N: RFQ Re-Creation Allowed When No PO Exists

**Problem:** `rfq_get_items.py` blocked RFQ creation for any MR item that already had a non-cancelled RFQ — regardless of whether a PO was created. This prevented re-quoting items where the supplier returned N/A or didn't respond.

**Solution:** Changed the exclusion condition to only block RFQ creation when the MR item has **both** a non-cancelled RFQ **and** a submitted PO. Items with RFQ but no PO are now allowed through for re-quoting.

**File:** `supply_chain/server_scripts/rfq_get_items.py` — `_get_mr_items_with_rfq()`

**Trade-off Accepted:** A second RFQ can now be created for items already in a submitted RFQ (if no PO exists). The `supplier_quotation.py` validation still enforces qty limits via row-ID matching against the specific RFQ item row.

---

### Decision N: Create RFQ Button — Standalone with Smart Item Filtering

**Problem:** The standard ERPNext "Request for Quotation" button in the MR Create dropdown fetches all items without any awareness of existing RFQs. For MRs with 100s of items, the user has no visibility into which items already have pending RFQs vs. which need a new RFQ.

**Solution:** Added a standalone "Create RFQ" button (not in the dropdown) that:
1. Calls `check_mr_rfq_status(mr_name)` to bucket items into: `has_po` (excluded), `has_rfq_no_po` (pending), `no_rfq` (fresh).
2. If `no_rfq > 0` and `has_rfq_no_po > 0` — shows a dialog asking the user to choose:
   - "Only N Remaining Items (no RFQ yet)" → `fetch_mode="remaining"`
   - "All N Items (excluding those with PO)" → `fetch_mode="all"`
3. If `has_rfq_no_po = 0` — fetches directly, no dialog.
4. If `no_rfq = 0` and `has_rfq_no_po > 0` — shows confirmation: "All N items already have pending RFQs. Create anyway?" → on confirm, `fetch_mode="all"`.
5. If both = 0 — shows "All items have POs" message and stops.

**Why not override the standard button?**
Frappe's `add_inner_button` skips adding if a button with the same label already exists in the group — the first registration wins. ERPNext registers the standard "Request for Quotation" button first (loaded before custom app). Removing then re-adding is fragile due to uncertain refresh handler execution order. A standalone button is simpler and avoids all timing issues.

**Why not just exclude pending RFQ items silently?**
Items where the supplier didn't quote or the rate was unacceptable need to be re-quoted. Silent exclusion was confusing for users managing large MRs. The dialog gives informed control.

**Exclusion rules:**
- `has_po` (RFQ + submitted PO) → always excluded (fully processed)
- `has_rfq_no_po` (RFQ but no PO) → user choice
- `no_rfq` (no RFQ) → always included

**Standard dropdown button behavior:** Still works via hooks override (`make_request_for_quotation` default `fetch_mode="remaining"`). Will be hidden from dropdown after signoff on the new button.

**Files:**
- `supply_chain/server_scripts/rfq_get_items.py` — `check_mr_rfq_status()`, `make_request_for_quotation(fetch_mode)`
- `public/js/material_request.js` — `clevertech_mr.create_rfq()`, `clevertech_mr._do_create_rfq()`

---

### Decision N: MR Item Project Field — Fix via JS, Not Report Query

**Problem:** Project tracking report used `mri.project` on MR items to filter by project. When `project` was removed from the BOM doctype, new MR items were created with `project = NULL`, causing those MRs to disappear from the report. The chain broke: no BOM project → no MR item project → no downstream SQ/PO item project.

**Solution:** Fixed at the source — `material_request.js` now sets `d.project = frm.doc.custom_project_` on each item row when exploding BOM items. Standard ERPNext then propagates `project` down the chain (MR item → RFQ item `project_name` → SQ item → PO item → PR item). The report query is unchanged.

**Why not fix the report query instead?**
Fixing the report to join through `mr.custom_project_` would work for MR but require tracing the full chain for PO/PR/SQ queries. The JS fix is simpler, correct at source, and keeps the existing client scripts (which set header-level `project`/`cost_center` on RFQ, SQ, PO) still valid.

**File:** `public/js/material_request.js`

**Note:** Existing MRs created after BOM project removal must be cancelled and re-amended to get `project` populated on items.
