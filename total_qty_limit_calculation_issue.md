# Issue: total_qty_limit Not Calculating During BOM Upload

## Problem Statement

When uploading BOMs via the enhanced BOM upload, Component Master fields (`bom_qty_required`, `total_qty_limit`, etc.) are not being calculated automatically, even though:
1. The calculation methods exist in `project_component_master.py` (`before_save()` hook)
2. We've added explicit calculation calls in `bom_hooks.py`
3. Manual `save()` via console DOES trigger calculations correctly

## Current Behavior

### What Works ✓
```python
# In console:
cm = frappe.get_doc("Project Component Master", "PCM-SMR260002-001646")
cm.save()  # This triggers before_save() → calculations run → values persist
frappe.db.commit()
```

### What Doesn't Work ✗
```python
# In bom_hooks.py during on_bom_submit:
component_master = get_component_master(project, item_code)
component_master.calculate_bom_qty_required()
component_master.calculate_total_qty_limit()
component_master.save(ignore_permissions=True)
frappe.db.commit()  # Values still show as 0.00 in database!
```

## Code Context

### Component Master Calculation Methods
**File:** `project_component_master.py`

```python
def before_save(self):
    """Calculate auto-fields before saving."""
    self.calculate_bom_qty_required()
    self.calculate_total_qty_limit()
    self.calculate_procurement_totals()
    self.update_procurement_status()
    # ... other calculations

def calculate_bom_qty_required(self):
    """Calculate from bom_usage table"""
    if not self.bom_usage:
        if self.is_loose_item:
            self.bom_qty_required = 0
        else:
            self.bom_qty_required = self.project_qty or 0
        return

    total = 0
    for usage in self.bom_usage:
        parent = frappe.db.get_value(
            "Project Component Master",
            {"project": self.project, "item_code": usage.parent_item},
            ["project_qty", "make_or_buy"],
            as_dict=True
        )
        if parent and parent.make_or_buy == "Make":
            usage.total_qty_required = (usage.qty_per_unit or 0) * (parent.project_qty or 0)
            total += usage.total_qty_required
    self.bom_qty_required = total

def calculate_total_qty_limit(self):
    """MAX(project_qty, bom_qty_required)"""
    project = self.project_qty or 0
    bom = self.bom_qty_required or 0
    self.total_qty_limit = max(project, bom)
```

### BOM Submit Hook (Current Implementation)
**File:** `bom_hooks.py`

```python
def on_bom_submit(doc, method=None):
    """Called when BOM is submitted"""
    # ... validation code ...

    # Process all child items
    for item in doc.items:
        add_or_update_bom_usage(
            project=doc.project,
            item_code=item.item_code,
            parent_bom=doc.name,
            qty_per_unit=item.qty
        )

    # Update parent BOM item
    update_component_master_bom_fields(
        project=doc.project,
        item_code=doc.item,
        bom_name=doc.name
    )

    frappe.db.commit()  # Added to persist changes

def update_component_master_bom_fields(project, item_code, bom_name):
    """Update BOM fields and trigger calculations"""
    component_master = get_component_master(project, item_code)
    if not component_master:
        return

    # Update BOM fields
    component_master.has_bom = 1
    component_master.active_bom = bom_name
    component_master.bom_structure_hash = calculate_bom_structure_hash(bom_doc)

    # Explicitly trigger calculations
    component_master.calculate_bom_qty_required()
    component_master.calculate_total_qty_limit()
    component_master.calculate_procurement_totals()
    component_master.update_procurement_status()

    component_master.flags.ignore_validate = True
    component_master.flags.ignore_mandatory = True
    component_master.save(ignore_permissions=True)

def add_or_update_bom_usage(project, item_code, parent_bom, qty_per_unit):
    """Add/update bom_usage entry for child items"""
    component_master = get_component_master(project, item_code)
    if not component_master:
        return

    # ... append or update bom_usage ...

    # Explicitly trigger calculations
    component_master.calculate_bom_qty_required()
    component_master.calculate_total_qty_limit()
    component_master.calculate_procurement_totals()
    component_master.update_procurement_status()

    component_master.flags.ignore_validate = True
    component_master.flags.ignore_mandatory = True
    component_master.save(ignore_permissions=True)
```

## Proposed Solutions (Need Developer Input)

### Approach 1: Use db_set() Instead of save() ⭐
**Hypothesis:** `save()` within hooks might not persist calculated values due to transaction/ORM issues

```python
def update_component_master_bom_fields(project, item_code, bom_name):
    component_master = get_component_master(project, item_code)

    # Save basic fields first
    component_master.has_bom = 1
    component_master.active_bom = bom_name
    component_master.save(ignore_permissions=True)

    # Calculate values
    component_master.calculate_bom_qty_required()
    component_master.calculate_total_qty_limit()
    component_master.calculate_procurement_totals()
    component_master.update_procurement_status()

    # Update DB directly, bypassing ORM
    component_master.db_set("bom_qty_required", component_master.bom_qty_required, update_modified=False)
    component_master.db_set("total_qty_limit", component_master.total_qty_limit, update_modified=False)
    component_master.db_set("total_qty_procured", component_master.total_qty_procured, update_modified=False)
    component_master.db_set("procurement_status", component_master.procurement_status, update_modified=False)
```

**Pros:** Bypasses ORM issues, direct DB write
**Cons:** Doesn't trigger hooks, requires explicit field listing

### Approach 2: Force Reload After Save
**Hypothesis:** Doc might be stale after save

```python
def update_component_master_bom_fields(project, item_code, bom_name):
    component_master = get_component_master(project, item_code)

    component_master.has_bom = 1
    component_master.active_bom = bom_name
    component_master.save(ignore_permissions=True)

    # Reload to get fresh doc
    component_master.reload()

    # Now calculate and save again
    component_master.save(ignore_permissions=True)
```

### Approach 3: Use on_update Hook Instead
**Hypothesis:** `before_save` might not run with certain flags

Move calculations from `before_save()` to `on_update()` in Component Master:

```python
# In project_component_master.py
def on_update(self):
    """After save, recalculate if needed"""
    self.calculate_bom_qty_required()
    self.calculate_total_qty_limit()
    self.calculate_procurement_totals()
    self.update_procurement_status()

    # Update DB directly without triggering another save
    self.db_update()
```

### Approach 4: Defer Calculations to After Commit
**Hypothesis:** Transaction isolation preventing reads of uncommitted bom_usage data

```python
def on_bom_submit(doc, method=None):
    # ... process all items ...

    frappe.db.commit()

    # After commit, trigger calculations
    frappe.enqueue(
        "clevertech.project_component_master.bom_hooks.recalculate_component_masters",
        project=doc.project,
        bom_name=doc.name
    )
```

### Approach 5: Debug Why before_save Isn't Running
Add logging to determine if `before_save()` is being called:

```python
# In project_component_master.py
def before_save(self):
    """Calculate auto-fields before saving."""
    frappe.log_error(f"before_save called for {self.name}, ignore_validate={self.flags.ignore_validate}")

    self.calculate_bom_qty_required()
    self.calculate_total_qty_limit()
    # ... etc
```

## Questions for Developers

1. **Does `ignore_validate=True` skip `before_save()` hook?**
   - Documentation is unclear
   - Need to test or check Frappe source code

2. **Why does console `save()` work but hook `save()` doesn't?**
   - Transaction scope difference?
   - Context/permissions difference?

3. **Is there a Frappe best practice for calculations in hooks?**
   - Should we use `db_set()` for calculated fields?
   - Should calculations be in `before_save()` or `on_update()`?

4. **Transaction isolation - could bom_usage reads be returning stale data?**
   - When we calculate `bom_qty_required`, it reads from `bom_usage` child table
   - If that data isn't committed yet, calculations would return 0

5. **Should we use `frappe.flags` or context managers for better transaction control?**

## Test Case to Reproduce

```python
# Via bench console
cm = frappe.get_doc("Project Component Master", "PCM-SMR260002-001646")
print(f"Before: bom_qty={cm.bom_qty_required}, limit={cm.total_qty_limit}")

cm.save()
frappe.db.commit()

# Verify in DB
result = frappe.db.sql("""
    SELECT bom_qty_required, total_qty_limit
    FROM `tabProject Component Master`
    WHERE name='PCM-SMR260002-001646'
""", as_dict=True)
print(f"After: {result[0]}")  # This works! Values are 1.0, 1.0
```

```python
# During BOM upload (bom_hooks.py)
# Same code structure, but values stay 0.00 in database!
```

## Immediate Workaround

For now, users can manually trigger calculation by opening Component Master form and clicking Save, or by running:

```python
# Update all Component Masters for a project
cms = frappe.get_all("Project Component Master", filters={"project": "SMR260002"})
for cm_data in cms:
    cm = frappe.get_doc("Project Component Master", cm_data.name)
    cm.save()
frappe.db.commit()
```

## Files Involved

1. `clevertech/clevertech/doctype/project_component_master/project_component_master.py` - Calculation logic
2. `clevertech/project_component_master/bom_hooks.py` - BOM submit hooks
3. `clevertech/hooks.py` - Hook registration

## Next Steps

**Need developer review to determine:**
- Why `save()` in hooks doesn't persist calculated values
- Best approach from the 5 options above
- Whether this is a Frappe ORM limitation or our implementation issue
