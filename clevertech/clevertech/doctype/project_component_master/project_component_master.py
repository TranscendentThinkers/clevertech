# Copyright (c) 2026, Bharatbodh and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ProjectComponentMaster(Document):

	def before_save(self):
		"""Calculate auto-fields before saving."""
		# Detect make_or_buy change and cascade to children
		if not self.is_new() and self.has_value_changed("make_or_buy"):
			self.flags.make_or_buy_changed = True

			# Validate: Warn if changing to "Make" but all parents are "Buy"
			if self.make_or_buy == "Make" and self.bom_usage:
				self._validate_make_with_buy_parents()

		self.calculate_bom_qty_required()
		self.calculate_total_qty_limit()
		self.calculate_procurement_totals()
		self.update_procurement_status()
		self.calculate_budgeted_rate_rollup()
		self.update_bom_conversion_status()

	def _validate_make_with_buy_parents(self):
		"""
		Validate that changing to "Make" makes sense given parent's Make/Buy status.
		If all parents are "Buy", then changing this component to "Make" has no effect
		on procurement quantities (children will still have zero requirement).
		"""
		# Check all parents' Make/Buy status
		parent_statuses = []
		for usage in self.bom_usage:
			# Bug Fix 2026-02-11: Add machine_code filter to prevent cross-machine CM contamination
			filters = {"project": self.project, "item_code": usage.parent_item}
			if self.machine_code:
				filters["machine_code"] = self.machine_code

			parent = frappe.db.get_value(
				"Project Component Master",
				filters,
				["make_or_buy", "name"],
				as_dict=True
			)
			if parent:
				parent_statuses.append({
					"item": usage.parent_item,
					"make_or_buy": parent.make_or_buy,
					"name": parent.name
				})

		# Check if all parents are "Buy"
		all_parents_buy = all(p["make_or_buy"] == "Buy" for p in parent_statuses if p["make_or_buy"])

		if all_parents_buy and parent_statuses:
			# Build warning message with parent details
			parent_list = "<br>".join([
				f"• <b>{p['item']}</b> (Make/Buy: {p['make_or_buy']})"
				for p in parent_statuses
			])

			frappe.msgprint(
				msg=f"<b>Warning:</b> You are changing <b>{self.item_code}</b> to <b>Make</b>, "
				    f"but all its parent assemblies are set to <b>Buy</b>:<br><br>"
				    f"{parent_list}<br><br>"
				    f"<b>Impact:</b> This component and its children will have <b>zero procurement quantities</b> "
				    f"because they are covered by the parent's procurement.<br><br>"
				    f"<b>Recommendation:</b> If you want to procure this component and its children separately, "
				    f"change the parent assembly to <b>Make</b> first, then change this component to <b>Make</b>.",
				title="Make/Buy Configuration Warning",
				indicator="orange"
			)

	def on_update(self):
		"""After save, cascade recalculation if make_or_buy changed."""
		if getattr(self.flags, "make_or_buy_changed", False):
			# Show message to user about recursive recalculation
			old_value = self.get_doc_before_save().make_or_buy if not self.is_new() else None
			new_value = self.make_or_buy

			if old_value != new_value:
				frappe.msgprint(
					msg=f"Make/Buy changed from <b>{old_value or 'None'}</b> to <b>{new_value}</b> for {self.item_code}.<br>"
					    f"Triggering recursive recalculation for all child components in the BOM hierarchy...",
					title="Recalculating Child Components",
					indicator="blue"
				)

			# Trigger recursive recalculation
			affected_count = self.recalculate_children_bom_qty(recursive=True, _depth=0)

			if affected_count > 0:
				# Check if this component has zero total_qty_limit (indicates parent is "Buy")
				if self.total_qty_limit == 0 and new_value == "Make":
					frappe.msgprint(
						msg=f"Recalculated <b>{affected_count}</b> child component(s).<br><br>"
						    f"<b>Note:</b> All quantities set to <b>zero</b> because parent assembly is <b>Buy</b>. "
						    f"Child procurement is covered by parent's procurement.",
						title="Recalculation Complete",
						indicator="orange"
					)
				else:
					frappe.msgprint(
						msg=f"Successfully recalculated quantities for <b>{affected_count}</b> child component(s).",
						title="Recalculation Complete",
						indicator="green"
					)

	def calculate_bom_qty_required(self):
		"""
		Calculate BOM quantity required by summing from all BOMs using this component.
		Multiplies qty_per_unit by parent's total_qty_limit for correct totals.
		Also populates total_qty_required on each bom_usage row.

		IMPORTANT: Only counts parents where make_or_buy = "Make".
		If parent is "Buy" (procured as unit), this component is covered by parent's
		procurement and does NOT need separate procurement.

		For root assemblies (no bom_usage): bom_qty_required = project_qty
		For loose items "Pending Conversion" (no bom_usage): bom_qty_required = 0
		For components in BOMs (has bom_usage): SUM(parent.total_qty_limit × qty_per_unit)
		  where parent.make_or_buy = "Make"

		Note: Uses total_qty_limit instead of project_qty to handle multi-level hierarchies.
		For level 1 components, total_qty_limit = project_qty.
		For level 2+ components, total_qty_limit = MAX(project_qty, bom_qty_required).
		"""
		if not self.bom_usage:
			# Root assembly or loose item - no BOM usage rows
			if self.is_loose_item:
				self.bom_qty_required = 0
			else:
				self.bom_qty_required = self.project_qty or 0
			return

		# Has BOM usage rows — calculate from all parent BOMs where parent is "Make"
		total = 0
		for usage in self.bom_usage:
			# Bug Fix 2026-02-11: Add machine_code filter to prevent cross-machine CM contamination
			filters = {"project": self.project, "item_code": usage.parent_item}
			if self.machine_code:
				filters["machine_code"] = self.machine_code

			# Get parent's total quantity limit and make/buy flag
			parent = frappe.db.get_value(
				"Project Component Master",
				filters,
				["total_qty_limit", "make_or_buy"],
				as_dict=True
			)

			if parent and parent.make_or_buy == "Make":
				# Parent is assembled in-house — this component needs separate procurement
				usage.total_qty_required = (usage.qty_per_unit or 0) * (parent.total_qty_limit or 0)
				total += usage.total_qty_required
			else:
				# Parent is "Buy" — this component is covered by parent's procurement
				usage.total_qty_required = 0

		self.bom_qty_required = total

	def recalculate_children_bom_qty(self, recursive=False, _depth=0, _processed=None):
		"""
		When make_or_buy changes on this component, recalculate bom_qty_required
		for all children in this component's active BOM.

		If this was changed from Buy→Make, children now need separate procurement.
		If this was changed from Make→Buy, children are now covered by this component's procurement.

		Also updates bom_usage table from current BOM (self-healing).

		Args:
			recursive: If True, recursively recalculate all descendants in the BOM hierarchy
			_depth: Internal parameter to track recursion depth (max 10 levels)
			_processed: Internal parameter to track processed items (avoid infinite loops)

		Returns:
			int: Number of child components affected
		"""
		# Safety: Prevent infinite recursion
		MAX_DEPTH = 10
		if _depth > MAX_DEPTH:
			frappe.log_error(
				title=f"Max recursion depth reached for {self.item_code}",
				message=f"Stopped at depth {_depth} to prevent infinite recursion"
			)
			return 0

		if not self.active_bom:
			return 0

		# Track processed items to avoid circular references
		if _processed is None:
			_processed = set()

		if self.name in _processed:
			return 0

		_processed.add(self.name)

		# Get BOM and consolidate duplicate items (same as on_bom_submit)
		bom = frappe.get_doc("BOM", self.active_bom)
		item_quantities = {}
		for item in bom.items:
			if item.item_code in item_quantities:
				item_quantities[item.item_code] += float(item.qty or 0)
			else:
				item_quantities[item.item_code] = float(item.qty or 0)

		affected_count = 0

		# Update bom_usage and recalculate for each child
		for item_code, total_qty in item_quantities.items():
			# Bug Fix 2026-02-11: Add machine_code filter to prevent cross-machine CM contamination
			filters = {"project": self.project, "item_code": item_code}
			if self.machine_code:
				filters["machine_code"] = self.machine_code

			child_cm_name = frappe.db.get_value(
				"Project Component Master",
				filters,
				"name"
			)
			if child_cm_name:
				child_doc = frappe.get_doc("Project Component Master", child_cm_name)

				# Update bom_usage entry with current BOM data
				usage_updated = False
				for usage in child_doc.bom_usage:
					if usage.parent_bom == self.active_bom:
						if usage.qty_per_unit != total_qty:
							usage.qty_per_unit = total_qty
							usage_updated = True
						break

				# If bom_usage was updated, save it
				if usage_updated:
					child_doc.flags.ignore_validate = True
					child_doc.save(ignore_permissions=True)

				# Calculate all quantities
				child_doc.calculate_bom_qty_required()
				child_doc.calculate_total_qty_limit()
				child_doc.calculate_procurement_totals()
				child_doc.update_procurement_status()

				# Use frappe.db.set_value to persist calculated fields (bypasses save() in hooks)
				frappe.db.set_value(child_doc.doctype, child_doc.name, {
					"bom_qty_required": child_doc.bom_qty_required,
					"total_qty_limit": child_doc.total_qty_limit,
					"total_qty_procured": child_doc.total_qty_procured,
					"procurement_balance": child_doc.procurement_balance,
					"procurement_status": child_doc.procurement_status
				}, update_modified=False)

				affected_count += 1

				# Recursive call: If this child also has a BOM and make_or_buy is "Make",
				# recalculate its children as well
				if recursive and child_doc.has_bom and child_doc.active_bom:
					child_affected = child_doc.recalculate_children_bom_qty(
						recursive=True,
						_depth=_depth + 1,
						_processed=_processed
					)
					affected_count += child_affected

		# Commit all changes (only at root level)
		if _depth == 0:
			frappe.db.commit()

		return affected_count

	def calculate_total_qty_limit(self):
		"""
		Calculate total quantity limit: MAX(project_qty, bom_qty_required).

		This is the hard procurement limit enforced in Material Request validation.
		- project_qty: Manually entered by user (from Excel or manual entry)
		- bom_qty_required: Auto-calculated from BOM usage
		- Limit is the maximum of these two values
		"""
		project = self.project_qty or 0
		bom = self.bom_qty_required or 0
		self.total_qty_limit = max(project, bom)

	def calculate_procurement_totals(self):
		"""Sum all procurement records (MR and PO quantities)."""
		total = 0
		for record in self.procurement_records:
			if record.document_type in ("Material Request", "Purchase Order"):
				total += record.quantity or 0
		self.total_qty_procured = total
		self.procurement_balance = (self.total_qty_limit or 0) - total

	def update_procurement_status(self):
		"""Auto-set status based on quantities."""
		if not self.total_qty_procured:
			self.procurement_status = "Not Started"
		elif self.total_qty_procured > (self.total_qty_limit or 0):
			self.procurement_status = "Over-procured"
		elif self.total_qty_procured >= (self.total_qty_limit or 0):
			self.procurement_status = "Completed"
		else:
			self.procurement_status = "In Progress"

	def calculate_budgeted_rate_rollup(self):
		"""
		Populate budgeted_rate_calculated:
		- Assembly items (has_bom): read total_cost from the active BOM
		  (ERPNext already rolls up RM costs bottom-up on BOM submit)
		- Leaf items (no BOM): read last_purchase_rate from Item master
		"""
		if self.has_bom and self.active_bom:
			self.budgeted_rate_calculated = (
				frappe.db.get_value("BOM", self.active_bom, "total_cost") or 0
			)
		else:
			self.budgeted_rate_calculated = (
				frappe.db.get_value("Item", self.item_code, "last_purchase_rate") or 0
			)

	def update_bom_conversion_status(self):
		"""Update conversion status for loose items."""
		if not self.is_loose_item:
			self.bom_conversion_status = "Not Applicable"
			return

		if not self.can_be_converted_to_bom:
			self.bom_conversion_status = "Pending Conversion"
		elif len(self.bom_usage) == 0:
			self.bom_conversion_status = "Pending Conversion"
		elif len(self.bom_usage) == 1:
			self.bom_conversion_status = "Converted to BOM"
		else:
			self.bom_conversion_status = "Partial"
