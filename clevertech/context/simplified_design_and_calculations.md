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

