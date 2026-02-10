# Bug 3: BOM-Level Validation Design (NOT IMPLEMENTED - READY FOR FUTURE)

**Status:** 📋 Design approved, ready for implementation when needed
**Date analyzed:** 2026-02-09
**Current behavior:** Uses CM-level `total_qty_limit` (aggregate across all BOM paths)
**Proposed behavior:** Two-layer validation (BOM-specific + CM-level cap)

---

## Problem Statement

**Current limitation:**
CM's `total_qty_limit` is the SUM across ALL BOM paths an item appears in. When creating MR from a specific BOM via "Get Items from BOM", validation should enforce that specific path's limit, not the aggregate.

**Example:**
```
BOM-M001 (Machine M001)
  ├─ BOM-G001
  │   └─ A001 (qty=2 per unit) → bom_usage: total_qty_required=2
  └─ BOM-G002
      └─ A001 (qty=3 per unit) → bom_usage: total_qty_required=3

Component Master for A001:
  - total_qty_limit = 5 (2+3, aggregate)

Current behavior:
  - User creates MR from BOM-G001 for 10 units
  - MR item: A001, qty=30 (10 × 3)
  - Validation checks: 30 > 5 (total_qty_limit) → BLOCKS ❌
  - But should check: 30 > 20 (10 × 2 for G001 path) → BLOCKS correctly ✓

Desired behavior:
  - Layer 1: Check against bom_usage.total_qty_required for BOM-G001 path (20)
  - Layer 2: Check against CM total_qty_limit as overall cap (5)
```

---

## How ERPNext "Get Items from BOM" Works

**User action:**
1. Opens Material Request
2. Clicks "Get Items from BOM"
3. Selects a BOM (e.g., BOM-M001)
4. ERPNext populates MR items with **immediate children** of that BOM

**Critical insight:**
- Each MR item gets `bom_no = BOM-M001` (the top-level BOM user selected)
- Each MR item is an **immediate child** item from BOM-M001's explosion
- ERPNext does NOT expand grandchildren (that's the parent BOM's responsibility)

**Example:**
```
BOM-M001 items:
  - G001 (qty=2) → MR item: G001, qty=20, bom_no=BOM-M001
  - A001 (qty=5) → MR item: A001, qty=50, bom_no=BOM-M001

(If G001 has children, they are NOT added to this MR)
```

**Matching logic:**
```
MR item.bom_no (BOM-M001) == bom_usage.parent_bom (BOM-M001) ✓

This works because:
- MR item is an immediate child of BOM-M001
- bom_usage row has parent_bom = BOM-M001 (the immediate parent)
- Direct match!
```

---

## Proposed Solution: Two-Layer Validation

### Layer 1: BOM-Specific Validation (when bom_no is set)

**Logic:**
```python
# In _validate_item_qty(), after getting component

# Check if MR item came from "Get Items from BOM"
if item.bom_no:
    # Try to find matching bom_usage row
    bom_usage = frappe.db.get_value(
        "Component BOM Usage",
        {
            "parent": component.name,
            "parent_bom": item.bom_no
        },
        ["total_qty_required", "parent_item"],
        as_dict=True
    )

    if bom_usage:
        # LAYER 1: Validate against this specific BOM path
        bom_limit = bom_usage.total_qty_required or 0

        # Get existing MR qty for this SPECIFIC bom_no
        # (filter by machine_code too, from Bug 1 fix)
        if machine_code:
            existing_bom_qty = frappe.db.sql("""
                SELECT COALESCE(SUM(mri.qty), 0)
                FROM `tabMaterial Request Item` mri
                INNER JOIN `tabMaterial Request` mr ON mri.parent = mr.name
                INNER JOIN `tabCost Center` cc ON mr.custom_cost_center = cc.name
                WHERE mr.custom_project_ = %s
                  AND mri.item_code = %s
                  AND mri.bom_no = %s
                  AND cc.custom_machine_code = %s
                  AND mr.docstatus < 2
                  AND mr.name != %s
            """, (project, item_code, item.bom_no, machine_code, mr_name))[0][0] or 0
        else:
            # Fallback without machine filter
            existing_bom_qty = frappe.db.sql("""
                SELECT COALESCE(SUM(mri.qty), 0)
                FROM `tabMaterial Request Item` mri
                INNER JOIN `tabMaterial Request` mr ON mri.parent = mr.name
                WHERE mr.custom_project_ = %s
                  AND mri.item_code = %s
                  AND mri.bom_no = %s
                  AND mr.docstatus < 2
                  AND mr.name != %s
            """, (project, item_code, item.bom_no, mr_name))[0][0] or 0

        total_bom_procurement = existing_bom_qty + mr_qty
        max_allowed_bom = max(0, bom_limit - existing_bom_qty)

        if total_bom_procurement > bom_limit:
            frappe.throw(
                _(
                    "Cannot add {0} units of {1} to Material Request.<br><br>"
                    "<b>BOM-Specific Limit Exceeded:</b><br>"
                    "<table class='table table-bordered' style='width:auto;margin-top:10px'>"
                    "<tr><td>Parent BOM:</td><td><b>{2}</b></td></tr>"
                    "<tr><td>Parent Item:</td><td><b>{3}</b></td></tr>"
                    "<tr><td>BOM Path Limit:</td><td style='text-align:right'><b>{4}</b></td></tr>"
                    "<tr><td>Existing MRs (this BOM):</td><td style='text-align:right'>{5}</td></tr>"
                    "<tr><td>This MR:</td><td style='text-align:right'>{6}</td></tr>"
                    "<tr class='text-danger'><td>Total:</td><td style='text-align:right'><b>{7}</b></td></tr>"
                    "<tr class='text-success'><td>Max Allowed:</td><td style='text-align:right'><b>{8}</b></td></tr>"
                    "</table>"
                    "<br><small><i class='fa fa-info-circle'></i> "
                    "This item is used in multiple BOMs. Limit shown is for THIS specific BOM path.</small>"
                ).format(
                    mr_qty,
                    frappe.bold(item_code),
                    item.bom_no,
                    bom_usage.parent_item,
                    bom_limit,
                    existing_bom_qty,
                    mr_qty,
                    total_bom_procurement,
                    max_allowed_bom
                ),
                title=_("BOM Path Limit Exceeded")
            )

        # Layer 1 passed, continue to Layer 2
```

### Layer 2: CM-Level Cap (always enforce)

```python
# LAYER 2: Overall CM limit (current implementation)
# This runs AFTER Layer 1, as a final safeguard
qty_limit = component.total_qty_limit or 0
total_procurement = existing_mr_qty + mr_qty  # All MRs, all BOMs, filtered by machine

if total_procurement > qty_limit:
    frappe.throw(
        # Current error message format
        # (already includes CM link from recent enhancement)
    )
```

---

## Edge Case: Item Under Multiple Sub-Assemblies

**Scenario:**
```
BOM-M001
  ├─ BOM-G001 → A001 (qty=2)
  └─ BOM-G002 → A001 (qty=3)

User: "Get Items from BOM" on BOM-M001
ERPNext behavior: May consolidate duplicate items
  → MR item: A001, qty=5, bom_no=BOM-M001

bom_usage table for A001:
  - Row 1: parent_bom=BOM-G001, total_qty_required=2
  - Row 2: parent_bom=BOM-G002, total_qty_required=3
  - No row for parent_bom=BOM-M001 ❌

Lookup: parent_bom=BOM-M001 → No match!
```

**Solution:**
When `bom_no` doesn't match any bom_usage row (item appears under multiple sub-assemblies):
1. **Fall back to Layer 2 (CM-level validation)**
2. This is correct because:
   - User is requesting consolidated qty across all paths
   - CM's `total_qty_limit` is the right cap (SUM of all paths)
   - Layer 1 is meant for single-path procurement

**Detection:**
```python
if item.bom_no and not bom_usage:
    # No matching bom_usage row found
    # This item likely appears under multiple sub-BOMs in the parent
    # Fall through to Layer 2 (CM-level validation)
    pass
```

---

## Implementation Checklist (For Future)

**Phase 1: MR Validation Only**
- [ ] Add `bom_no` parameter to `_validate_item_qty()` signature
- [ ] Pass `item.bom_no` from `validate_material_request_qty()` loop
- [ ] Query `Component BOM Usage` for matching `parent_bom`
- [ ] Build existing qty query filtered by `bom_no` and `machine_code`
- [ ] Implement Layer 1 validation with BOM-specific error message
- [ ] Ensure Layer 2 (CM-level) always runs as final safeguard
- [ ] Handle edge case: no matching bom_usage (fall back to Layer 2)
- [ ] Test with single-path BOM procurement
- [ ] Test with multi-path consolidated items
- [ ] Test with machine_code isolation (Bug 1 fix)

**Phase 2: PO Validation (if needed)**
- [ ] Check if PO Item has `bom_no` field (trace MR → PO linkage)
- [ ] If yes, apply same two-layer logic to PO validation
- [ ] If no, PO continues using only CM-level validation (current behavior)

**Phase 3: Error Messages**
- [x] Layer 2 message: Already has CM link (completed 2026-02-09)
- [ ] Layer 1 message: Include parent item name, BOM path, BOM-specific limit
- [ ] Consider showing both limits when both layers trigger

---

## Benefits of This Approach

1. **Tighter control:** Prevents over-procurement per BOM path
2. **Maintains safety net:** CM-level cap catches any gaps
3. **Handles edge cases:** Graceful fallback for multi-path items
4. **Backward compatible:** Items without `bom_no` still use CM-level validation
5. **Machine isolated:** Works with Bug 1 fix (machine_code filtering)
6. **No data model changes:** Uses existing `bom_no` field on MR Item

---

## Testing Scenarios (When Implementing)

### Test 1: Single-path BOM procurement
```
Setup:
  - BOM-G001 has A001, qty=2 per unit
  - bom_usage: total_qty_required=20 (for 10 units of G001)
  - CM total_qty_limit=50 (aggregate across all paths)

Test:
  - Create MR from BOM-G001 for 10 units
  - Add A001 qty=25

Expected:
  - Layer 1: 25 > 20 → Block (BOM path limit exceeded)
  - Error shows: "BOM Path Limit: 20, This BOM: 25"
```

### Test 2: Multi-path consolidated
```
Setup:
  - BOM-M001 has A001 under G001 (qty=2) and G002 (qty=3)
  - bom_usage rows: parent_bom=BOM-G001 (20), parent_bom=BOM-G002 (30)
  - CM total_qty_limit=50

Test:
  - Create MR from BOM-M001
  - ERPNext consolidates to A001 qty=5, bom_no=BOM-M001

Expected:
  - Layer 1: No match (parent_bom=BOM-M001 doesn't exist in bom_usage)
  - Layer 2: 5 < 50 → Allow
```

### Test 3: Layer 2 catches overage
```
Setup:
  - BOM-G001 has A001, bom_usage limit=20
  - CM total_qty_limit=15 (CM cap is stricter)

Test:
  - Create MR from BOM-G001, A001 qty=18

Expected:
  - Layer 1: 18 < 20 → Pass
  - Layer 2: 18 > 15 → Block (CM cap is stricter)
  - Error shows CM-level limit message
```

### Test 4: Multiple MRs for same BOM path
```
Setup:
  - BOM-G001 has A001, bom_usage limit=20
  - Existing: MR-001 from BOM-G001, A001 qty=10

Test:
  - Create MR-002 from BOM-G001, A001 qty=15

Expected:
  - Layer 1: existing=10, new=15, total=25 > 20 → Block
  - Error shows: "Existing MRs (this BOM): 10, Total: 25, Limit: 20"
```

### Test 5: Machine isolation with BOM path
```
Setup:
  - A001 exists in V20 (limit=10) and V21 (limit=30)
  - BOM-V20-G001 has A001, bom_usage limit=10
  - BOM-V21-G001 has A001, bom_usage limit=30

Test:
  - Create MR for V20, cost_center → V00000000020
  - Add A001 from BOM-V20-G001, qty=25

Expected:
  - Bug 1 ensures correct CM (V20) is picked
  - Layer 1: 25 > 10 → Block (V20's BOM path limit)
  - Should NOT check V21's limit or bom_usage
```

### Test 6: Items without bom_no (backward compatibility)
```
Setup:
  - Manual MR (not from "Get Items from BOM")
  - MR item: A001, qty=25, bom_no=NULL

Test:
  - Save MR

Expected:
  - Layer 1: Skipped (no bom_no)
  - Layer 2: Validates against CM total_qty_limit (current behavior)
  - Backward compatible ✓
```

---

## Code Changes Required

### File: `material_request_validation.py`

**1. Update function signature:**
```python
def _validate_item_qty(project, item_code, mr_qty, mr_name, machine_code=None, bom_no=None):
    """
    Args:
        ...
        bom_no: BOM reference from MR item (for Layer 1 validation)
    """
```

**2. Update caller:**
```python
def validate_material_request_qty(doc, method=None):
    # ...
    for item in doc.items:
        _validate_item_qty(
            project,
            item.item_code,
            item.qty,
            doc.name,
            machine_code,
            item.bom_no  # ← Add this
        )
```

**3. Add Layer 1 logic (see pseudocode above)**

### File: `purchase_order_validation.py`

**Only if PO Item has `bom_no` field:**
- Same changes as MR validation
- Check if `bom_no` is inherited from MR → PO linkage
- If not available, skip Layer 1 (PO continues with Layer 2 only)

---

## Notes

- **Current status:** Bugs 1, 2, 4 are FIXED and deployed ✅ (2026-02-09)
- **Bug 3 status:** Design complete, analysis confirmed feasible, NOT implemented ⏸️
- **Reason deferred:** CM-level validation (with Bug 1 fix) provides adequate protection for now
- **When to implement:** When users report need for tighter per-BOM-path controls
- **Complexity:** Medium (requires bom_usage lookup + new qty tracking query)
- **Risk:** Low (Layer 2 provides safety net, backward compatible)
- **Estimated effort:** 4-6 hours (implementation + testing)

---

## References

- **Implementation files:**
  - `clevertech/project_component_master/material_request_validation.py` — MR validation logic
  - `clevertech/project_component_master/purchase_order_validation.py` — PO validation logic

- **Data model:**
  - `component_bom_usage.json` — Child table with `parent_bom`, `total_qty_required`
  - `material_request_item.json` — Has `bom_no` field (standard ERPNext)

- **Context documentation:**
  - `clevertech/context/implementation_status.md` v3.11 — Bug 1, 2, 4 fixes documented
  - This file: Bug 3 design approved for future implementation

---

**Last updated:** 2026-02-09
**Author:** BharatBodh Team
**Reviewed by:** User (confirmed feasibility and approach)
