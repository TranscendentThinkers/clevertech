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

