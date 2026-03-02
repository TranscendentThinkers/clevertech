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

