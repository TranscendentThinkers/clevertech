# Clevertech Context — Index

> **Reading order:** New to the system? Start here, then follow the links below.
> This index replaces the monolithic `../clevertech_context.md` as the entry point.
> The original file is kept intact and is the authoritative source; these topic files
> are extracted views for faster navigation.

---

## File Map

| # | File | What's inside | Lines |
|---|------|---------------|-------|
| 1 | [business_and_requirements.md](business_and_requirements.md) | Company profile, workflow, 7 core requirements | 111 |
| 2 | [current_system_and_issues.md](current_system_and_issues.md) | Existing BOM Upload logic, 6 limitations, 2 known-issue RCAs (column shift, active_bom stale) | 281 |
| 3 | [architectural_decisions.md](architectural_decisions.md) | Decisions 1–20: Component Master DocType, hierarchy, BOM versioning + demotion, loose items, hash detection, ancestor-chain blocking, make/buy, import strategy, G-code State filtering, G-code level validation | 937 |
| 4 | [simplified_design_and_calculations.md](simplified_design_and_calculations.md) | Phase 4B final design: project_qty / bom_qty_required / total_qty_limit rules, 3 data flows, loose-item states, make/buy cascade, Decisions 14–16 | 743 |
| 5 | [design_evolution_and_architecture.md](design_evolution_and_architecture.md) | 7 evolution iterations (scope → qty logic → blocking → state model …), final system-component diagram + 3 day-by-day scenarios | 253 |
| 6 | [implementation_status.md](implementation_status.md) | Phase-by-phase log (1 → 6), bug fixes, hash-comparison deep dive, Project Tracking report spec + post-impl fixes, G-code State filtering, G-code level validation analysis + implementation | 4471 |
| 7 | [appendix_and_conclusions.md](appendix_and_conclusions.md) | Success criteria, future enhancements, 5 design principles, conclusion summary | 99 |

---

## Quick Lookup

| I want to find … | Go to |
|---|---|
| Why was Project Component Master created? | [architectural_decisions.md](architectural_decisions.md) — Decision 1 |
| How does BOM hash comparison work? | [architectural_decisions.md](architectural_decisions.md) — Decision 6; [implementation_status.md](implementation_status.md) — "BOM Hash Comparison & Version Change Flow" |
| BOM demotion vs deactivation | [architectural_decisions.md](architectural_decisions.md) — Decision 3A; [simplified_design_and_calculations.md](simplified_design_and_calculations.md) — Decision 16 |
| Impacted parent BOMs after child change | [architectural_decisions.md](architectural_decisions.md) — Decision 3A (controlled upward propagation); [simplified_design_and_calculations.md](simplified_design_and_calculations.md) — Scenario B |
| How total_qty_limit is calculated | [simplified_design_and_calculations.md](simplified_design_and_calculations.md) — "Core Principles" + multi-level example |
| Make/Buy routing and cascade | [simplified_design_and_calculations.md](simplified_design_and_calculations.md) — Decision 14 |
| Loose item conversion states | [architectural_decisions.md](architectural_decisions.md) — Decision 4; [simplified_design_and_calculations.md](simplified_design_and_calculations.md) — "Loose Item Handling" |
| MR / RFQ / PO validation hard-block | [architectural_decisions.md](architectural_decisions.md) — Decision 9; [implementation_status.md](implementation_status.md) — Phases 3A, 4C, 4D |
| Excel column-shift bug & fix | [current_system_and_issues.md](current_system_and_issues.md) — Issue 1; [implementation_status.md](implementation_status.md) — Phase 4H |
| Machine code per-machine isolation | [implementation_status.md](implementation_status.md) — Decision 16 (Separate CMs per Machine) |
| BOM version change not creating new BOM | [implementation_status.md](implementation_status.md) — Bug Fix 2026-02-05 (recursion + hash check) |
| Stale BOM references (outdated child BOMs) | [implementation_status.md](implementation_status.md) — "Impacted Parent BOMs & Stale BOM References" |
| Project Tracking report columns | [implementation_status.md](implementation_status.md) — Phase 5 report spec |
| `frappe.db.set_value()` pattern for hooks | [implementation_status.md](implementation_status.md) — "Phase 5 Fix: Calculation Issues" |
| How the import strategy works (Decision 12) | [architectural_decisions.md](architectural_decisions.md) — Decision 12 & 12A |
| G-code STATE filtering (non-released designs) | [architectural_decisions.md](architectural_decisions.md) — Decision 19; [implementation_status.md](implementation_status.md) — "G-Code State Filtering" |
| G-code level procurement validation | [architectural_decisions.md](architectural_decisions.md) — Decision 20; [implementation_status.md](implementation_status.md) — "G-Code Level Procurement Validation" |
| Phase 1 BOM Upload (simple version, no procurement blocking) | [implementation_status.md](implementation_status.md) — "Phase 1 BOM Upload [2026-02-22]" |
| `design_status` field values on PCM (In Creation / Released / Obsolete) | [implementation_status.md](implementation_status.md) — "Design Status Validation & State Mapping [2026-02-23]" |
| STATE → design_status mapping in BOM upload (case-insensitive) | [implementation_status.md](implementation_status.md) — "Design Status Validation & State Mapping [2026-02-23]" — §2 |
| State warning confirmation dialog in Phase 1 upload | [implementation_status.md](implementation_status.md) — "Design Status Validation & State Mapping [2026-02-23]" — §3 |
| MR blocked if design_status is not Released | [implementation_status.md](implementation_status.md) — "Design Status Validation & State Mapping [2026-02-23]" — §5 |
| Cost Center project auto-fills from machine code (`fetch_from` + `read_only`) | [implementation_status.md](implementation_status.md) — "2026-02-28" — §2 |
| Item `custom_project` mandatory when is_machine_code checked | [implementation_status.md](implementation_status.md) — "2026-02-28" — §1 |
| Cost center set in PCM after BOM upload | [implementation_status.md](implementation_status.md) — "2026-02-28" — §3 |
| Make/Buy blank by default for new PCMs (not auto-set) | [implementation_status.md](implementation_status.md) — "2026-02-28" — §4 |
| Excel BOM root item must start with P or V (row 1 "Item no:" validation) | [implementation_status.md](implementation_status.md) — "2026-02-28" — §5 |
| BOM version change warning non-blocking (msgprint not throw) | [implementation_status.md](implementation_status.md) — "2026-02-28" — §6 |
| E-code items blocked in BOM upload (hard block with item list) | [implementation_status.md](implementation_status.md) — "2026-02-28" — §7 |
| budgeted_rate_calculated — BOM total_cost for assemblies, last_purchase_rate for leaves | [implementation_status.md](implementation_status.md) — "Budgeted Rate (Calculated) Smart Population" |
| RFQ portal old rates fix | [implementation_status.md](implementation_status.md) — "RFQ Portal Override [2026-02-14]" |
| Supply Chain Workflow Reports (MR→RFQ, RFQ→PO, PO→Delivery) | [implementation_status.md](implementation_status.md) — "Supply Chain Workflow Reports [2026-02-15]" |
| RFQ Get Items override (filter already-RFQed MR items) | [implementation_status.md](implementation_status.md) — "RFQ Get Items Override [2026-02-15]" |
| What phases are done vs pending | [implementation_status.md](implementation_status.md) — top of file |

---

## Cross-References

### Decisions referenced across multiple files

| Decision | Primary | Also referenced in |
|---|---|---|
| 3A — BOM versioning / demotion | architectural_decisions | simplified_design_and_calculations (D16), implementation_status (4E) |
| 5 / 13 — Quantity limit (MAX) | architectural_decisions | simplified_design_and_calculations (core principles) |
| 12 / 12A — Import strategy | architectural_decisions | implementation_status (4H) |
| 14 — Make/Buy | simplified_design_and_calculations | implementation_status (4C) |
| 16 — Version change tiers | simplified_design_and_calculations | implementation_status (4E) |

### Key source files ↔ context topics

| Source file | Primary context topic |
|---|---|
| `bom_upload_phase1.py` | implementation_status (Phase 1 BOM Upload) |
| `bom_upload_enhanced.py` | architectural_decisions, implementation_status |
| `bom_upload.py` | current_system_and_issues, architectural_decisions (D12) |
| `bom_hooks.py` | implementation_status (1A, 4D, 4F, 4I, 4J) |
| `project_component_master.py` | simplified_design_and_calculations, implementation_status (4, 4B) |
| `material_request_validation.py` | implementation_status (3A, 4C) |
| `rfq_validation.py` | implementation_status (4D) |
| `purchase_order_validation.py` | implementation_status (3A, 4C) |
| `procurement_hooks.py` | implementation_status (3, 4J) |
| `bulk_generation.py` | implementation_status (2A, bug fix 3) |
| `utils.py` | implementation_status (machine code cascade) |
| `project_tracking.py/.js` | implementation_status (Phase 5 report) |
| `bom.py` (server_scripts) | architectural_decisions (duplicate-check gate) |
| `rfq_portal.py` (supply_chain) | implementation_status (RFQ portal rate override) |
| `rfq_get_items.py` (supply_chain) | implementation_status (RFQ Get Items Override) |
| `rfq_to_po_tracker.py/.js` (supply_chain/report) | implementation_status (Report 2) |
| `po_to_delivery_tracker.py/.js` (supply_chain/report) | implementation_status (Report 3) |
| `routes.yaml` (this dir) | maps all of the above |

---

*Generated 2026-02-06. Last updated 2026-02-28 (v3.20: Item mandatory_depends_on, Cost Center fetch_from, BOM Upload cost_center/make_or_buy/P-V validation fixes, bom_hooks msgprint). Authoritative source: `../clevertech_context.md`.*
