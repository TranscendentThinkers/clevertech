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
| 6 | [implementation_status.md](implementation_status.md) | Phase-by-phase log (1 → 6), bug fixes, hash-comparison deep dive, Project Tracking report spec + post-impl fixes, G-code State filtering, G-code level validation analysis | 4349 |
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
| `routes.yaml` (this dir) | maps all of the above |

---

*Generated 2026-02-06. Last updated 2026-02-10. Authoritative source: `../clevertech_context.md`.*
