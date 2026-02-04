# BOM Upload Enhanced - Documentation

File: `clevertech/doctype/bom_upload/bom_upload_enhanced.py`

---

## Part 1: Technical Flowchart (Developer Reference)

### 1.1 Main Entry Point: `create_boms_with_validation()` (Line 192)

```mermaid
flowchart TB
    subgraph Entry["Entry Point: create_boms_with_validation(docname)"]
        A[Start] --> A1[frappe.get_doc 'BOM Upload', docname]
        A1 --> V1{doc.bom_file?}
        V1 -->|No| E1[❌ frappe.throw<br/>'Please attach a BOM Excel file first']
        V1 -->|Yes| V2{doc.project?}
        V2 -->|No| E2[❌ frappe.throw<br/>'Please select a Project first']
        V2 -->|Yes| V3{doc.machine_code?}
        V3 -->|No| E3[❌ frappe.throw<br/>'Machine Code is required']
        V3 -->|Yes| LOAD
    end

    subgraph LOAD["Load Excel File"]
        L1[frappe.get_doc 'File', file_url] --> L2[file_doc.get_content]
        L2 --> L3[openpyxl.load_workbook<br/>io.BytesIO, data_only=True]
        L3 --> L4[ws = wb.active]
        L4 --> L5{HAS_IMAGE_LOADER?}
        L5 -->|Yes| L6[image_loader = SheetImageLoader ws]
        L5 -->|No| L7[image_loader = None]
        L6 --> PARSE
        L7 --> PARSE
    end

    subgraph PARSE["Step 1: Parse Excel (Line 231)"]
        P1[parse_rows_dynamic ws] --> P2[build_tree rows]
        P2 --> P3{tree empty?}
        P3 -->|Yes| E4[❌ frappe.throw<br/>'No components found']
        P3 -->|No| ITEMS
    end

    subgraph ITEMS["Step 2: Create Items (Line 239)"]
        I1[item_counters = dict<br/>created, existing, updated, failed] --> I2[ensure_items_for_all_nodes<br/>tree, ws, image_loader, counters]
        I2 --> CM
    end

    subgraph CM["Step 3: Create Component Masters (Line 245)"]
        C1[cm_counters = create_component_masters_for_all_items<br/>tree, project, machine_code] --> ANALYZE
    end

    subgraph ANALYZE["Step 4: Analyze Upload (Line 248)"]
        AN1[analysis = analyze_upload<br/>tree, project, machine_code] --> BLOCK
    end

    subgraph BLOCK["Step 5: Blocking Checks (Line 251-324)"]
        B1{analysis.loose_blocked?} -->|Yes| R1[Return status: 'blocked'<br/>reason: 'loose_items_not_enabled']
        B1 -->|No| B2{analysis.changed_components?}
        B2 -->|No| CREATE
        B2 -->|Yes| B3[Categorize by blocking_level]
        B3 --> B4[hard_blocked = block level]
        B3 --> B5[manager_blocked = manager_required + !can_proceed]
        B3 --> B6[confirmable = confirm level OR manager_required + can_proceed]
        B4 --> B7{hard_blocked not empty?}
        B7 -->|Yes| R2[Return status: 'procurement_blocked'<br/>reason: 'active_mr_rfq']
        B7 -->|No| B8{manager_blocked not empty?}
        B8 -->|Yes| R3[Return status: 'manager_required'<br/>reason: 'active_po_no_role']
        B8 -->|No| B9{confirmable not empty?}
        B9 -->|Yes| R4[Return status: 'requires_confirmation'<br/>User must confirm with remarks]
        B9 -->|No| CREATE
    end

    subgraph CREATE["Step 6 & 7: Create BOMs (Line 327)"]
        CR1[result = create_boms_and_link_components<br/>tree, project, analysis, ws, image_loader] --> CR2[Build summary dict]
        CR2 --> CR3[_build_summary_message]
        CR3 --> CR4[frappe.db.commit]
        CR4 --> CR5[Return result]
    end

    style E1 fill:#ffcccc
    style E2 fill:#ffcccc
    style E3 fill:#ffcccc
    style E4 fill:#ffcccc
    style R1 fill:#ffcccc
    style R2 fill:#ffcccc
    style R3 fill:#ffcccc
    style R4 fill:#fff3cd
    style CR5 fill:#ccffcc
```

### 1.2 Dynamic Column Mapping: `map_excel_columns()` (Line 58)

```mermaid
flowchart TB
    subgraph MapColumns["map_excel_columns(ws)"]
        M1[Define header_mapping dict<br/>12 fields with expected headers] --> M2[Scan Row 2 columns 1-100]
        M2 --> M3[Build headers_in_excel dict<br/>col_letter → header_value]
        M3 --> M4[For each field in header_mapping]
        M4 --> M5{Header found<br/>in headers_in_excel?}
        M5 -->|Yes| M6[found_columns field = col_letter]
        M5 -->|No| M7[missing_columns.append field]
        M6 --> M8{More fields?}
        M7 --> M8
        M8 -->|Yes| M4
        M8 -->|No| M9{missing_columns?}
        M9 -->|Yes| M10[❌ frappe.throw<br/>'Invalid Excel Format'<br/>List missing columns]
        M9 -->|No| M11[Return found_columns dict]
    end

    subgraph Headers["Required Headers (Row 2)"]
        H1[position → 'Position']
        H2[item_code → 'Item no']
        H3[description → 'Description']
        H4[qty → 'Qty']
        H5[revision → 'Rev.']
        H6[extended_description → 'DESCRIZIONE_ESTESA']
        H7[material → 'MATERIAL']
        H8[part_number → 'Part_number']
        H9[weight → 'WEIGHT']
        H10[manufacturer → 'MANUFACTURER']
        H11[treatment → 'TIPO_TRATTAMENTO']
        H12[uom → 'UM']
        H13[level → 'LivelloBom' ⚠️ CRITICAL]
    end

    style M10 fill:#ffcccc
    style M11 fill:#ccffcc
    style H13 fill:#fff3cd
```

### 1.3 Parse Rows: `parse_rows_dynamic()` (Line 139)

```mermaid
flowchart TB
    subgraph ParseRows["parse_rows_dynamic(ws)"]
        P1[col_map = map_excel_columns ws] --> P2[rows = empty list]
        P2 --> P3[For r in range 3 to max_row+1]
        P3 --> P4[code_raw = ws col_map.item_code + r]
        P4 --> P5{code_raw empty?}
        P5 -->|Yes| P6[continue - skip row]
        P5 -->|No| P7[Build row dict]
        P7 --> P8[rows.append row]
        P8 --> P9{More rows?}
        P6 --> P9
        P9 -->|Yes| P3
        P9 -->|No| P10[Return rows]
    end

    subgraph RowDict["Row Dict Structure"]
        R1[row_num: r]
        R2[position: ws.position or ws.B]
        R3[item_code: clean_code code_raw]
        R4[description: ws.description]
        R5[extended_description: ws.extended_description]
        R6[qty: to_float ws.qty, default=1]
        R7[revision: ws.revision]
        R8[material: ws.material]
        R9[part_number: ws.part_number]
        R10[weight: to_float ws.weight, default=0]
        R11[manufacturer: ws.manufacturer]
        R12[treatment: ws.treatment]
        R13[uom: normalize_uom ws.uom]
        R14[level: int ws.level or 0 ⚠️]
        R15[children: empty list]
    end

    style R14 fill:#fff3cd
```

### 1.4 Create Items: `ensure_items_for_all_nodes()` (Line 367)

```mermaid
flowchart TB
    subgraph EnsureItems["ensure_items_for_all_nodes(tree, ws, image_loader, counters)"]
        E1[For each node in tree] --> E2[ensure_item_exists<br/>item_code, description, extended_desc,<br/>uom, row_num, ws, image_loader,<br/>material, treatment, weight,<br/>part_number, manufacturer, revision]
        E2 --> E3[result = 'created' OR 'existing' OR 'updated' OR 'failed']
        E3 --> E4[counters result += 1]
        E4 --> E5{node.children?}
        E5 -->|Yes| E6[ensure_items_for_all_nodes<br/>node.children, ws, image_loader, counters]
        E5 -->|No| E7{More nodes?}
        E6 --> E7
        E7 -->|Yes| E1
        E7 -->|No| E8[Return counters]
    end
```

### 1.5 Create Component Masters: `create_component_masters_for_all_items()` (Line 411)

```mermaid
flowchart TB
    subgraph CreateCM["create_component_masters_for_all_items(tree, project, machine_code)"]
        C1[counters = created, existing, updated, failed] --> C2[all_nodes = _get_all_nodes tree]
        C2 --> C3[For each node in all_nodes]
        C3 --> C4[item_code = node.item_code]
        C4 --> C5[is_assembly = bool node.children]
        C5 --> C6{frappe.db.exists<br/>PCM: project + item + machine?}
        C6 -->|Yes| C7[_merge_make_or_buy existing, node]
        C7 --> C8{updated?}
        C8 -->|Yes| C9[counters.updated += 1]
        C8 -->|No| C10[counters.existing += 1]
        C6 -->|No| C11[Create New CM]
    end

    subgraph NewCM["Create New Component Master"]
        N1{item_code starts with<br/>T, Y, or E?}
        N1 -->|Yes| N2[released_for_procurement = 'No']
        N1 -->|No| N3[released_for_procurement = 'Yes']
        N2 --> N4{level == 1?}
        N3 --> N4
        N4 -->|Yes| N5[project_qty = node.qty]
        N4 -->|No| N6[project_qty = 0]
        N5 --> N7{item_code starts with M or G?}
        N6 --> N7
        N7 -->|Yes| N8[default_make_or_buy = 'Make']
        N7 -->|No| N9[default_make_or_buy = 'Buy']
        N8 --> N10{is_assembly?}
        N9 --> N10
        N10 -->|Yes| N11[has_bom = 1<br/>active_bom = None<br/>bom_structure_hash = calculate_tree_structure_hash]
        N10 -->|No| N12[has_bom = 0]
        N11 --> N13[cm.insert ignore_permissions=True]
        N12 --> N13
        N13 --> N14{Success?}
        N14 -->|Yes| N15[counters.created += 1]
        N14 -->|No| N16[counters.failed += 1<br/>frappe.log_error]
    end

    C9 --> C17{More nodes?}
    C10 --> C17
    N15 --> C17
    N16 --> C17
    C17 -->|Yes| C3
    C17 -->|No| C18[Return counters]

    style N16 fill:#ffcccc
```

### 1.6 Analyze Upload: `analyze_upload()` (Line 568)

```mermaid
flowchart TB
    subgraph Analyze["analyze_upload(tree, project, machine_code)"]
        A1[all_assemblies = _get_assembly_nodes tree] --> A2[graph = _build_dependency_graph all_assemblies]
        A2 --> A3[categorized = new, unchanged, changed, loose_blocked]
        A3 --> A4[For each item_code, data in graph]
        A4 --> A5[status, details = _determine_component_status<br/>item_code, data.node, project, machine_code]
        A5 --> A6[data.status = status<br/>data.details = details]
        A6 --> A7[categorized status .append item_code]
        A7 --> A8{More items?}
        A8 -->|Yes| A4
        A8 -->|No| A9[changed_set = set categorized.changed]
        A9 --> A10[loose_blocked_set = set categorized.loose_blocked]
        A10 --> A11[blocked_by_changes = _find_blocked_ancestors<br/>graph, changed_set, loose_blocked_set]
        A11 --> A12[Build can_create list<br/>new + unchanged NOT in blocked_set]
        A12 --> A13[Return analysis dict]
    end

    subgraph AnalysisResult["Analysis Result Structure"]
        R1[can_create: list of nodes safe to create]
        R2[changed_components: list of graph entries for changed]
        R3[loose_blocked: list of graph entries for loose_blocked]
        R4[blocked_by_dependencies: dict item → blocking reasons]
        R5[summary: total, new, unchanged, changed, loose_blocked, can_create, blocked]
    end
```

### 1.7 Determine Component Status: `_determine_component_status()` (Line 630)

```mermaid
flowchart TB
    subgraph DetermineStatus["_determine_component_status(item_code, node, project, machine_code)"]
        D1[component_master = frappe.db.get_value<br/>PCM: project + item + machine<br/>Fields: name, is_loose_item, can_be_converted,<br/>bom_structure_hash, active_bom] --> D2{CM exists?}
        D2 -->|No| D3[Return 'new', first_time: True]
        D2 -->|Yes| D4{is_loose_item AND<br/>NOT can_be_converted_to_bom?}
        D4 -->|Yes| D5[Return 'loose_blocked', message]
        D4 -->|No| D6{active_bom set?}
    end

    subgraph NoBomLinked["No active_bom linked yet"]
        N1[Find existing BOM:<br/>item + project + is_active + is_default + docstatus=1] --> N2{BOM found<br/>with project?}
        N2 -->|No| N3[Find BOM without project filter]
        N2 -->|Yes| N4[existing_bom = name]
        N3 --> N5{BOM found?}
        N5 -->|No| N6[Return 'new', first_time: False]
        N5 -->|Yes| N4
        N4 --> N7[new_hash = calculate_tree_structure_hash children]
        N7 --> N8[existing_hash = BOM.custom_bom_structure_hash]
        N8 --> N9{existing_hash NULL?}
        N9 -->|Yes| N10[Backfill: calculate_bom_doc_hash<br/>Store in BOM]
        N9 -->|No| N11[Compare hashes]
        N10 --> N11
        N11 --> N12{new_hash == existing_hash?}
        N12 -->|Yes| N13[Return 'unchanged',<br/>existing_bom_not_linked: True]
        N12 -->|No| N14[blocking_info = _check_procurement_blocking]
        N14 --> N15[bom_diff = calculate_bom_diff]
        N15 --> N16[Return 'changed', details with<br/>blocking_level, bom_diff, etc.]
    end

    subgraph HasBomLinked["active_bom is set"]
        H1[new_hash = calculate_tree_structure_hash children] --> H2[existing_hash = BOM.custom_bom_structure_hash]
        H2 --> H3{existing_hash NULL?}
        H3 -->|Yes| H4[Backfill hash from BOM doc]
        H3 -->|No| H5[Compare hashes]
        H4 --> H5
        H5 --> H6{new_hash == existing_hash?}
        H6 -->|Yes| H7[Return 'unchanged', bom: active_bom]
        H6 -->|No| H8[blocking_info = _check_procurement_blocking]
        H8 --> H9[bom_diff = calculate_bom_diff]
        H9 --> H10[Return 'changed', details]
    end

    D6 -->|No| N1
    D6 -->|Yes| H1

    style D3 fill:#ccffcc
    style D5 fill:#ffcccc
    style N6 fill:#ccffcc
    style N13 fill:#ccffcc
    style N16 fill:#fff3cd
    style H7 fill:#ccffcc
    style H10 fill:#fff3cd
```

### 1.8 Check Procurement Blocking: `_check_procurement_blocking()` (Line 938)

```mermaid
flowchart TB
    subgraph CheckBlocking["_check_procurement_blocking(project, item_code, old_bom_name)"]
        C1{old_bom_name?} -->|No| C2[Return can_proceed: True<br/>blocking_level: 'none']
        C1 -->|Yes| C3[old_bom_items = frappe.get_all<br/>BOM Item: parent = old_bom_name]
        C3 --> C4[blocking_level = 'none'<br/>procurement_docs = empty list]
        C4 --> C5[For each bom_item in old_bom_items]
        C5 --> C6[child_item = bom_item.item_code]
    end

    subgraph CheckMR["Check Material Requests"]
        M1[mrs = _get_material_requests project, child_item] --> M2{mrs not empty?}
        M2 -->|Yes| M3[Add MRs to procurement_docs<br/>blocking_level = max 'confirm']
        M2 -->|No| M4[Continue]
    end

    subgraph CheckRFQ["Check RFQs"]
        R1[rfqs = _get_rfqs project, child_item] --> R2{rfqs not empty?}
        R2 -->|Yes| R3[Add RFQs to procurement_docs<br/>blocking_level = max 'confirm']
        R2 -->|No| R4[Continue]
    end

    subgraph CheckPO["Check Purchase Orders"]
        P1[pos = _get_purchase_orders project, child_item] --> P2{pos not empty?}
        P2 -->|Yes| P3[Add POs to procurement_docs<br/>blocking_level = max 'manager_required']
        P2 -->|No| P4[Continue]
    end

    subgraph FinalDecision["Determine Can Proceed"]
        F1{blocking_level == 'none'?} -->|Yes| F2[blocking_level = 'confirm']
        F1 -->|No| F3[Keep current level]
        F2 --> F4{blocking_level?}
        F3 --> F4
        F4 -->|confirm| F5[can_proceed = True<br/>message: 'Confirmation with remarks required']
        F4 -->|block| F6[can_proceed = False<br/>message: 'Active MR/RFQ blocks']
        F4 -->|manager_required| F7{_can_override_po_block?<br/>Has Manager Role?}
        F7 -->|Yes| F8[can_proceed = True<br/>message: 'Manager override available']
        F7 -->|No| F9[can_proceed = False<br/>message: 'Manager role required']
        F5 --> F10[Return result dict]
        F6 --> F10
        F8 --> F10
        F9 --> F10
    end

    C6 --> M1
    M3 --> R1
    M4 --> R1
    R3 --> P1
    R4 --> P1
    P3 --> C7{More bom_items?}
    P4 --> C7
    C7 -->|Yes| C5
    C7 -->|No| F1

    style F5 fill:#fff3cd
    style F6 fill:#ffcccc
    style F8 fill:#fff3cd
    style F9 fill:#ffcccc
```

### 1.9 Confirm Version Change: `confirm_version_change()` (Line 1045)

```mermaid
flowchart TB
    subgraph Confirm["confirm_version_change(docname, confirmations)"]
        C1[Parse confirmations JSON if string] --> C2[doc = frappe.get_doc BOM Upload]
        C2 --> C3[project = doc.project<br/>machine_code = doc.machine_code]
        C3 --> C4{machine_code?}
        C4 -->|No| C5[❌ frappe.throw 'Machine Code required']
        C4 -->|Yes| C6[For each conf in confirmations]
        C6 --> C7[item_code = conf.item_code<br/>remarks = conf.remarks]
        C7 --> C8[cm_name = frappe.db.get_value PCM]
        C8 --> C9{cm_name exists?}
        C9 -->|Yes| C10[frappe.db.set_value<br/>version_change_remarks = remarks]
        C9 -->|No| C11[Skip]
        C10 --> C12{More confirmations?}
        C11 --> C12
        C12 -->|Yes| C6
        C12 -->|No| C13[_proceed_with_confirmed_changes<br/>doc, confirmed_item_codes]
    end

    style C5 fill:#ffcccc
```

### 1.10 Proceed with Confirmed Changes: `_proceed_with_confirmed_changes()` (Line 1094)

```mermaid
flowchart TB
    subgraph Proceed["_proceed_with_confirmed_changes(doc, confirmed_items)"]
        P1[Re-parse Excel file] --> P2[rows = parse_rows_dynamic ws]
        P2 --> P3[tree = build_tree rows]
        P3 --> P4[ensure_items_for_all_nodes tree]
        P4 --> P5[For each item_code in confirmed_items]
        P5 --> P6[cm = frappe.db.get_value PCM<br/>name, active_bom]
        P6 --> P7{cm.active_bom exists?}
        P7 -->|Yes| P8[Deactivate old BOM:<br/>is_active = 0, is_default = 0<br/>Save with ignore_validate]
        P7 -->|No| P9[Skip deactivation]
        P8 --> P10{More confirmed_items?}
        P9 --> P10
        P10 -->|Yes| P5
        P10 -->|No| P11[Build can_create list]
    end

    subgraph BuildCanCreate["Build can_create List"]
        B1[all_assemblies = _get_assembly_nodes tree] --> B2[For each node in all_assemblies]
        B2 --> B3{item_code in confirmed_set?}
        B3 -->|Yes| B4[Add to can_create]
        B3 -->|No| B5{Has active_bom?}
        B5 -->|No| B6[Add to can_create]
        B5 -->|Yes| B7[Compare hashes]
        B7 --> B8{Hash changed?}
        B8 -->|Yes| B9[Add to can_create]
        B8 -->|No| B10[Skip - unchanged]
        B4 --> B11{More nodes?}
        B6 --> B11
        B9 --> B11
        B10 --> B11
        B11 -->|Yes| B2
        B11 -->|No| B12[analysis.can_create = list]
    end

    P11 --> B1
    B12 --> P13[create_boms_and_link_components<br/>tree, project, analysis, ws, image_loader]
    P13 --> P14[frappe.db.commit]
    P14 --> P15[Return result]
```

### 1.11 Create BOMs and Link: `create_boms_and_link_components()` (Line 1225)

```mermaid
flowchart TB
    subgraph CreateBOMs["create_boms_and_link_components(tree, project, analysis, ws, image_loader)"]
        C1[counters: created, skipped, failed, errors] --> C2[can_create_codes = set of item_codes from analysis.can_create]
        C2 --> C3[For each node in tree]
        C3 --> C4[_create_bom_for_node<br/>node, project, can_create_codes, ws, image_loader]
        C4 --> C5[Accumulate counters and errors]
        C5 --> C6{More nodes?}
        C6 -->|Yes| C3
        C6 -->|No| C7[_link_boms_to_component_masters project]
    end

    subgraph CreateNode["_create_bom_for_node (Line 1288)"]
        N1{node.children?} -->|No| N2[Return - leaf node, no BOM]
        N1 -->|Yes| N3{item_code in can_create_codes?}
        N3 -->|No| N4[skipped += 1]
        N3 -->|Yes| N5[create_bom_recursive<br/>node, project, ws, image_loader]
        N5 --> N6{Success?}
        N6 -->|Yes| N7[created += 1]
        N6 -->|No| N8[failed += 1<br/>errors.append]
        N7 --> N9[For each child with children]
        N8 --> N9
        N2 --> N10[Return]
        N4 --> N10
        N9 --> N11[Recurse: _create_bom_for_node child]
        N11 --> N10
    end

    C7 --> C8[_populate_hierarchy_codes project, only_missing=True]
    C8 --> C9[recalculate_component_masters_for_project project]
    C9 --> C10{recalc errors?}
    C10 -->|Yes| C11[errors.extend recalc_result.errors]
    C10 -->|No| C12[Continue]
    C11 --> C13[Return result dict:<br/>status, created, skipped, failed, errors]
    C12 --> C13
```

### 1.12 Link BOMs to Component Masters: `_link_boms_to_component_masters()` (Line 1340)

```mermaid
flowchart TB
    subgraph LinkBOMs["_link_boms_to_component_masters(project)"]
        L1[cms = frappe.get_all PCM<br/>project + has_bom=1<br/>Fields: name, item_code, active_bom] --> L2[linked_boms = empty list]
        L2 --> L3[For each cm_data in cms]
        L3 --> L4[Find active default BOM<br/>item + project + is_active + is_default + docstatus=1]
        L4 --> L5{BOM found with project?}
        L5 -->|No| L6[Find BOM without project filter]
        L5 -->|Yes| L7[bom_name = result]
        L6 --> L8{BOM found?}
        L8 -->|No| L9[Skip - no BOM exists]
        L8 -->|Yes| L7
        L7 --> L10{cm_data.active_bom == bom_name?}
        L10 -->|Yes| L11[Skip - already linked]
        L10 -->|No| L12[cm = frappe.get_doc PCM]
        L12 --> L13[cm.active_bom = bom_name]
        L13 --> L14[cm.bom_structure_hash = calculate_bom_doc_hash]
        L14 --> L15[cm.save ignore_permissions, ignore_validate]
        L15 --> L16[linked_boms.append bom_name, item]
        L9 --> L17{More cms?}
        L11 --> L17
        L16 --> L17
        L17 -->|Yes| L3
        L17 -->|No| L18{linked_boms not empty?}
        L18 -->|Yes| L19[populate_bom_usage_tables project, linked_boms]
        L18 -->|No| L20[Done]
        L19 --> L20
    end
```

### 1.13 Populate Hierarchy Codes: `_populate_hierarchy_codes()` (Line 1425)

```mermaid
flowchart TB
    subgraph PopulateHierarchy["_populate_hierarchy_codes(project, only_missing=True)"]
        P1{only_missing?} -->|Yes| P2[SQL: Get CMs where<br/>parent_component OR m_code OR g_code IS NULL]
        P1 -->|No| P3[Get ALL CMs for project]
        P2 --> P4[Build item_to_cm lookup]
        P3 --> P4
        P4 --> P5[For each cm_data in cms]
        P5 --> P6{item_code starts with M?}
        P6 -->|Yes| P7[m_code = item_code<br/>g_code = None]
        P6 -->|No| P8{item_code starts with G?}
        P8 -->|Yes| P9[g_code = item_code<br/>Find parent for m_code]
        P8 -->|No| P10[Find parent via BOM<br/>Inherit m_code, g_code from parent CM]
        P7 --> P11[parent_item = _find_parent_item_via_bom]
        P9 --> P11
        P10 --> P11
        P11 --> P12[parent_component = item_to_cm.get parent_item]
        P12 --> P13{needs_parent OR needs_m_code OR needs_g_code?}
        P13 -->|Yes| P14[frappe.db.set_value updates]
        P13 -->|No| P15[Skip]
        P14 --> P16{More cms?}
        P15 --> P16
        P16 -->|Yes| P5
        P16 -->|No| P17{updated > 0?}
        P17 -->|Yes| P18[frappe.db.commit]
        P17 -->|No| P19[Done]
        P18 --> P19
    end
```

### 1.14 Hash Calculation: `calculate_tree_structure_hash()` (Line 1616)

```mermaid
flowchart LR
    subgraph TreeHash["calculate_tree_structure_hash(children)"]
        T1[children list] --> T2{children empty?}
        T2 -->|Yes| T3[Return None]
        T2 -->|No| T4[Create tuples:<br/>item_code, float qty]
        T4 --> T5[Sort by item_code]
        T5 --> T6[JSON.dumps sort_keys=True]
        T6 --> T7[MD5 hash encode]
        T7 --> T8[Return hexdigest]
    end
```

### 1.15 BOM Diff Calculation: `calculate_bom_diff()` (Line 1639)

```mermaid
flowchart TB
    subgraph BOMDiff["calculate_bom_diff(old_bom_name, new_children)"]
        D1[Get old_bom_doc items<br/>Consolidate by item_code] --> D2[Get new_children<br/>Consolidate by item_code]
        D2 --> D3[old_set = set old_items.keys]
        D3 --> D4[new_set = set new_items.keys]
        D4 --> D5[added = new_set - old_set]
        D5 --> D6[removed = old_set - new_set]
        D6 --> D7[For items in intersection:<br/>Compare quantities with tolerance 0.0001]
        D7 --> D8[qty_changed = items with different qty]
        D8 --> D9[Return added, removed, qty_changed]
    end
```

---

## Part 2: Testing Flowchart (QA Reference)

### 2.1 Test Scenarios Overview

```mermaid
flowchart TB
    subgraph TestCategories["Test Categories"]
        TC1[Input Validation Tests] --> TV1[Missing file<br/>Missing project<br/>Missing machine code]
        TC2[Excel Format Tests] --> TV2[Valid format<br/>Missing columns<br/>Wrong headers<br/>Empty data]
        TC3[Item Creation Tests] --> TV3[New items<br/>Existing items<br/>Item updates]
        TC4[Component Master Tests] --> TV4[New CM creation<br/>CM merge logic<br/>Prefix rules M/G/T/Y/E]
        TC5[BOM Analysis Tests] --> TV5[New components<br/>Unchanged components<br/>Changed components<br/>Loose blocked items]
        TC6[Blocking Tests] --> TV6[No procurement<br/>MR exists<br/>RFQ exists<br/>PO exists<br/>Manager role override]
        TC7[Confirmation Tests] --> TV7[User confirms<br/>Old BOM deactivation<br/>New BOM creation]
        TC8[Output Tests] --> TV8[Summary counts<br/>Error handling<br/>Transaction commit]
    end
```

### 2.2 Input Validation Test Flow

```mermaid
flowchart TB
    subgraph InputTests["Input Validation Tests"]
        I1[Start: Click 'Create BOMs with Validation'] --> I2{BOM File Attached?}
        I2 -->|No| I3[✅ EXPECT: Error message<br/>'Please attach a BOM Excel file first']
        I2 -->|Yes| I4{Project Selected?}
        I4 -->|No| I5[✅ EXPECT: Error message<br/>'Please select a Project first']
        I4 -->|Yes| I6{Machine Code Entered?}
        I6 -->|No| I7[✅ EXPECT: Error message<br/>'Machine Code is required']
        I6 -->|Yes| I8[✅ PROCEED to Excel parsing]
    end

    style I3 fill:#e6ffe6
    style I5 fill:#e6ffe6
    style I7 fill:#e6ffe6
    style I8 fill:#e6ffe6
```

### 2.3 Excel Format Test Flow

```mermaid
flowchart TB
    subgraph ExcelTests["Excel Format Tests"]
        E1[Upload Excel File] --> E2{Row 2 has all<br/>required headers?}
        E2 -->|No| E3[✅ EXPECT: Error listing missing columns<br/>Shows found headers for debugging]
        E2 -->|Yes| E4{Data rows exist<br/>Row 3 onwards?}
        E4 -->|No| E5[✅ EXPECT: Error<br/>'No components found in the Excel file']
        E4 -->|Yes| E6{Item codes valid<br/>Not empty?}
        E6 -->|Empty rows| E7[✅ EXPECT: Empty rows skipped silently]
        E6 -->|Valid| E8[✅ PROCEED to Item creation]
    end

    subgraph RequiredHeaders["Required Headers to Test"]
        H1[Position]
        H2[Item no ⚠️ Critical]
        H3[Description]
        H4[Qty]
        H5[Rev.]
        H6[DESCRIZIONE_ESTESA]
        H7[MATERIAL]
        H8[Part_number]
        H9[WEIGHT]
        H10[MANUFACTURER]
        H11[TIPO_TRATTAMENTO]
        H12[UM]
        H13[LivelloBom ⚠️ Critical - may shift columns]
    end

    style E3 fill:#e6ffe6
    style E5 fill:#e6ffe6
    style E7 fill:#e6ffe6
    style E8 fill:#e6ffe6
    style H13 fill:#fff3cd
```

### 2.4 Component Master Creation Test Flow

```mermaid
flowchart TB
    subgraph CMTests["Component Master Tests"]
        C1[Process Item from Excel] --> C2{CM already exists<br/>for Project + Item + Machine?}
        C2 -->|Yes - Existing CM| C3{Excel has Make/Buy value?}
        C3 -->|Yes| C4[✅ VERIFY: CM make_or_buy updated to Excel value]
        C3 -->|No| C5[✅ VERIFY: CM make_or_buy unchanged]
        C2 -->|No - New CM| C6{Item code prefix?}
    end

    subgraph PrefixRules["Prefix Rules to Test"]
        P1[Prefix T, Y, E] --> P2[✅ VERIFY: released_for_procurement = 'No']
        P3[Prefix M, G] --> P4[✅ VERIFY: make_or_buy = 'Make']
        P5[Other prefixes] --> P6[✅ VERIFY: make_or_buy = 'Buy'<br/>released_for_procurement = 'Yes']
    end

    subgraph AssemblyRules["Assembly vs Leaf Tests"]
        A1{Has children in Excel?}
        A1 -->|Yes - Assembly| A2[✅ VERIFY: has_bom = 1<br/>active_bom = NULL initially<br/>bom_structure_hash calculated]
        A1 -->|No - Leaf/RM| A3[✅ VERIFY: has_bom = 0]
    end

    subgraph LevelRules["BOM Level Rules"]
        L1{Level = 1 - Root?}
        L1 -->|Yes| L2[✅ VERIFY: project_qty = Excel qty value]
        L1 -->|No - Level 2+| L3[✅ VERIFY: project_qty = 0]
    end

    C6 --> P1
    C6 --> P3
    C6 --> P5
    P2 --> A1
    P4 --> A1
    P6 --> A1
    A2 --> L1
    A3 --> L1

    style C4 fill:#e6ffe6
    style C5 fill:#e6ffe6
    style P2 fill:#e6ffe6
    style P4 fill:#e6ffe6
    style P6 fill:#e6ffe6
    style A2 fill:#e6ffe6
    style A3 fill:#e6ffe6
    style L2 fill:#e6ffe6
    style L3 fill:#e6ffe6
```

### 2.5 BOM Change Detection Test Flow

```mermaid
flowchart TB
    subgraph ChangeTests["BOM Change Detection Tests"]
        D1[Analyze Assembly from Excel] --> D2{CM exists?}
        D2 -->|No| D3[✅ VERIFY: Status = NEW<br/>Can create BOM]
        D2 -->|Yes| D4{Active BOM linked?}
        D4 -->|No| D5[Check if BOM exists in system]
        D4 -->|Yes| D6[Compare hash with active BOM]
        D5 --> D7{BOM found?}
        D7 -->|No| D8[✅ VERIFY: Status = NEW]
        D7 -->|Yes| D9[Compare hash with found BOM]
        D6 --> D10{Hash matches?}
        D9 --> D10
        D10 -->|Yes| D11[✅ VERIFY: Status = UNCHANGED<br/>BOM creation skipped]
        D10 -->|No| D12[✅ VERIFY: Status = CHANGED<br/>Shows diff: added/removed/qty changed]
    end

    subgraph LooseItemTests["Loose Item Tests"]
        L1{CM is_loose_item = Yes?}
        L1 -->|Yes| L2{can_be_converted_to_bom = Yes?}
        L2 -->|No| L3[✅ VERIFY: Status = LOOSE_BLOCKED<br/>Upload blocked with message]
        L2 -->|Yes| L4[✅ VERIFY: Proceeds normally]
        L1 -->|No| L5[✅ VERIFY: Proceeds normally]
    end

    style D3 fill:#e6ffe6
    style D8 fill:#e6ffe6
    style D11 fill:#e6ffe6
    style D12 fill:#e6ffe6
    style L3 fill:#e6ffe6
    style L4 fill:#e6ffe6
    style L5 fill:#e6ffe6
```

### 2.6 Procurement Blocking Test Flow

```mermaid
flowchart TB
    subgraph BlockingTests["Procurement Blocking Tests"]
        B1[Changed component detected] --> B2[Check child items of old BOM]
        B2 --> B3{Any child has<br/>Material Request?}
        B3 -->|Yes| B4[✅ VERIFY: Blocking level = 'confirm'<br/>User can proceed with remarks]
        B3 -->|No| B5{Any child has RFQ?}
        B5 -->|Yes| B6[✅ VERIFY: Blocking level = 'confirm'<br/>User can proceed with remarks]
        B5 -->|No| B7{Any child has<br/>Purchase Order?}
        B7 -->|Yes| B8{User has Manager role?}
        B8 -->|Yes| B9[✅ VERIFY: Can proceed with manager override]
        B8 -->|No| B10[✅ VERIFY: BLOCKED<br/>'Manager role required' message]
        B7 -->|No| B11[✅ VERIFY: Blocking level = 'confirm'<br/>Needs confirmation only]
    end

    subgraph ConfirmationTests["User Confirmation Tests"]
        C1[User clicks Confirm] --> C2[Enter remarks for each changed item]
        C2 --> C3[✅ VERIFY: Remarks saved to CM.version_change_remarks]
        C3 --> C4[✅ VERIFY: Old BOM deactivated<br/>is_active = 0, is_default = 0]
        C4 --> C5[✅ VERIFY: New BOM created and submitted]
        C5 --> C6[✅ VERIFY: CM.active_bom updated to new BOM]
    end

    style B4 fill:#e6ffe6
    style B6 fill:#e6ffe6
    style B9 fill:#e6ffe6
    style B10 fill:#ffe6e6
    style B11 fill:#e6ffe6
    style C3 fill:#e6ffe6
    style C4 fill:#e6ffe6
    style C5 fill:#e6ffe6
    style C6 fill:#e6ffe6
```

### 2.7 BOM Creation & Linking Test Flow

```mermaid
flowchart TB
    subgraph BOMCreationTests["BOM Creation Tests"]
        BC1[Approved for BOM creation] --> BC2{Assembly node?}
        BC2 -->|No - Leaf| BC3[✅ VERIFY: No BOM created for leaf items]
        BC2 -->|Yes| BC4{In can_create list?}
        BC4 -->|No| BC5[✅ VERIFY: BOM creation skipped]
        BC4 -->|Yes| BC6[✅ VERIFY: BOM created with:<br/>• Correct item as parent<br/>• All children as BOM items<br/>• Quantities from Excel<br/>• Project linked]
        BC6 --> BC7[✅ VERIFY: BOM submitted docstatus=1]
        BC7 --> BC8[✅ VERIFY: BOM is_active=1, is_default=1]
    end

    subgraph LinkingTests["CM Linking Tests"]
        L1[After BOM creation] --> L2[✅ VERIFY: CM.active_bom points to new BOM]
        L2 --> L3[✅ VERIFY: CM.bom_structure_hash matches BOM hash]
        L3 --> L4[✅ VERIFY: BOM Usage table populated<br/>for all child items]
    end

    subgraph HierarchyTests["Hierarchy Code Tests"]
        H1[After linking] --> H2{Item is M-code?}
        H2 -->|Yes| H3[✅ VERIFY: CM.m_code = item_code<br/>CM.g_code = NULL]
        H2 -->|No| H4{Item is G-code?}
        H4 -->|Yes| H5[✅ VERIFY: CM.g_code = item_code<br/>CM.m_code = parent's M-code]
        H4 -->|No| H6[✅ VERIFY: CM inherits m_code, g_code from parent]
        H3 --> H7[✅ VERIFY: parent_component links to parent CM]
        H5 --> H7
        H6 --> H7
    end

    subgraph RecalcTests["Quantity Recalculation Tests"]
        R1[After hierarchy populated] --> R2[✅ VERIFY: total_qty_limit calculated correctly]
        R2 --> R3[✅ VERIFY: bom_qty_required populated from BOM structure]
    end

    style BC3 fill:#e6ffe6
    style BC5 fill:#e6ffe6
    style BC6 fill:#e6ffe6
    style BC7 fill:#e6ffe6
    style BC8 fill:#e6ffe6
    style L2 fill:#e6ffe6
    style L3 fill:#e6ffe6
    style L4 fill:#e6ffe6
    style H3 fill:#e6ffe6
    style H5 fill:#e6ffe6
    style H6 fill:#e6ffe6
    style H7 fill:#e6ffe6
    style R2 fill:#e6ffe6
    style R3 fill:#e6ffe6
```

### 2.8 Output Verification Test Flow

```mermaid
flowchart TB
    subgraph OutputTests["Output Verification Tests"]
        O1[Process Complete] --> O2[✅ VERIFY: Summary shows correct counts]
        O2 --> O3[Items: created / existing / updated / failed]
        O2 --> O4[BOMs: created / existing / failed]
        O2 --> O5[Component Masters: created / existing / updated / failed]
        O3 --> O6[✅ VERIFY: Total = sum of all categories]
        O4 --> O6
        O5 --> O6
        O6 --> O7{Any failures?}
        O7 -->|Yes| O8[✅ VERIFY: Errors logged to Error Log]
        O7 -->|No| O9[✅ VERIFY: Clean completion]
        O8 --> O10[✅ VERIFY: frappe.db.commit called]
        O9 --> O10
    end

    subgraph ErrorHandling["Error Handling Tests"]
        E1[Simulate failure scenarios] --> E2[Item creation fails]
        E2 --> E3[✅ VERIFY: Failure counted, process continues]
        E1 --> E4[CM creation fails]
        E4 --> E5[✅ VERIFY: Failure logged, process continues]
        E1 --> E6[BOM creation fails]
        E6 --> E7[✅ VERIFY: Error in errors list, other BOMs still created]
    end

    style O2 fill:#e6ffe6
    style O6 fill:#e6ffe6
    style O8 fill:#e6ffe6
    style O9 fill:#e6ffe6
    style O10 fill:#e6ffe6
    style E3 fill:#e6ffe6
    style E5 fill:#e6ffe6
    style E7 fill:#e6ffe6
```

### 2.9 Test Data Checklist

| Test Scenario | Required Test Data | Expected Result |
|---------------|-------------------|-----------------|
| Valid upload - new items | Excel with new item codes, Project, Machine Code | All items, CMs, BOMs created |
| Re-upload same data | Same Excel uploaded again | Status: UNCHANGED, no new BOMs |
| Changed BOM structure | Excel with modified children | Status: CHANGED, requires confirmation |
| Missing Excel column | Excel without 'LivelloBom' header | Validation error with missing column name |
| Loose item blocking | CM with is_loose_item=1, can_be_converted=0 | Upload blocked with specific message |
| MR blocking | Child item has Material Request | Confirmation required (not hard blocked) |
| PO blocking - no role | Child item has PO, user lacks Manager role | Hard blocked, manager required |
| PO blocking - with role | Child item has PO, user has Manager role | Can proceed with confirmation |
| T-prefix item | Item code starting with 'T' | released_for_procurement = 'No' |
| M-prefix item | Item code starting with 'M' | make_or_buy = 'Make' |
| Level 1 assembly | Root assembly in Excel | project_qty = Excel qty |
| Level 2+ item | Child item in Excel | project_qty = 0 |

---

## Part 3: Quick Reference

### Return Status Codes

| Status | Reason | User Action Required |
|--------|--------|---------------------|
| `success` | - | None - upload complete |
| `blocked` | `loose_items_not_enabled` | Enable 'Can be converted to BOM' on loose items |
| `procurement_blocked` | `active_mr_rfq` | Deactivate old BOMs manually (currently not used) |
| `manager_required` | `active_po_no_role` | Contact user with Component Master Manager role |
| `requires_confirmation` | - | Confirm changes with remarks |

### Key Database Tables Affected

| Table | Operation | When |
|-------|-----------|------|
| Item | INSERT/UPDATE | Step 2 - Item creation |
| Project Component Master | INSERT/UPDATE | Step 3 - CM creation |
| BOM | INSERT | Step 6 - BOM creation |
| BOM Item | INSERT | Step 6 - BOM creation |
| Component BOM Usage | INSERT | Step 7 - populate_bom_usage_tables |
| Component BOM Version History | INSERT | On version change confirmation |
