# BOM Upload - Testing Guide

**Document Purpose:** QA Reference for testing BOM Upload with Validation feature
**Last Updated:** 2026-02-04

---

## 1. Test Categories Overview

```mermaid
flowchart TB
    subgraph TestCategories["Test Categories"]
        TC1[Input Validation] --> TV1[Missing file<br/>Missing project<br/>Missing machine code]
        TC2[Excel Format] --> TV2[Valid format<br/>Missing columns<br/>Wrong headers<br/>Empty data]
        TC3[Item Creation] --> TV3[New items<br/>Existing items<br/>Item updates]
        TC4[Component Master] --> TV4[New CM creation<br/>CM merge logic<br/>Prefix rules]
        TC5[BOM Analysis] --> TV5[New components<br/>Unchanged<br/>Changed<br/>Blocked]
        TC6[Procurement Blocking] --> TV6[No procurement<br/>MR exists<br/>RFQ exists<br/>PO exists]
        TC7[Confirmation Flow] --> TV7[User confirms<br/>Old BOM deactivation<br/>New BOM creation]
        TC8[Output Verification] --> TV8[Summary counts<br/>Error handling]
    end
```

---

## 2. Input Validation Tests

### Test Flow

```mermaid
flowchart TB
    subgraph InputTests["Input Validation Tests"]
        I1[Click 'Create BOMs with Validation'] --> I2{BOM File Attached?}
        I2 -->|No| I3[EXPECT: Error<br/>'Please attach a BOM Excel file first']
        I2 -->|Yes| I4{Project Selected?}
        I4 -->|No| I5[EXPECT: Error<br/>'Please select a Project first']
        I4 -->|Yes| I6{Machine Code Entered?}
        I6 -->|No| I7[EXPECT: Error<br/>'Machine Code is required']
        I6 -->|Yes| I8[PASS: Proceed to Excel parsing]
    end

    style I3 fill:#ffe6e6
    style I5 fill:#ffe6e6
    style I7 fill:#ffe6e6
    style I8 fill:#e6ffe6
```

### Test Cases

| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 1.1 | Missing BOM file | Leave file field empty, click button | Error: "Please attach a BOM Excel file first" |
| 1.2 | Missing Project | Attach file but no project selected | Error: "Please select a Project first" |
| 1.3 | Missing Machine Code | Attach file + select project, no machine code | Error: "Machine Code is required" |
| 1.4 | All inputs valid | Provide file + project + machine code | Process continues to Excel parsing |

---

## 3. Excel Format Tests

### Test Flow

```mermaid
flowchart TB
    subgraph ExcelTests["Excel Format Validation"]
        E1[Upload Excel File] --> E2{Row 2 has all<br/>required headers?}
        E2 -->|No| E3[EXPECT: Error listing<br/>missing columns]
        E2 -->|Yes| E4{Data rows exist?<br/>Row 3 onwards}
        E4 -->|No| E5[EXPECT: Error<br/>'No components found']
        E4 -->|Yes| E6{Item codes valid?}
        E6 -->|Empty rows| E7[EXPECT: Empty rows<br/>skipped silently]
        E6 -->|Valid| E8[PASS: Continue]
    end

    style E3 fill:#ffe6e6
    style E5 fill:#ffe6e6
    style E7 fill:#fff3cd
    style E8 fill:#e6ffe6
```

### Required Excel Headers (Row 2)

| Header Name | Field | Critical? |
|-------------|-------|-----------|
| Position | position | No |
| **Item no** | item_code | **Yes** |
| Description | description | No |
| Qty | qty | No |
| Rev. | revision | No |
| DESCRIZIONE_ESTESA | extended_description | No |
| MATERIAL | material | No |
| Part_number | part_number | No |
| WEIGHT | weight | No |
| MANUFACTURER | manufacturer | No |
| TIPO_TRATTAMENTO | treatment | No |
| UM | uom | No |
| **LivelloBom** | level | **Yes - Critical** |

### Test Cases

| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| 3.1 | Missing header | Remove 'LivelloBom' from Row 2 | Error listing missing column |
| 3.2 | Empty data | Excel with headers only, no data rows | Error: "No components found" |
| 3.3 | Empty rows in data | Some rows have empty item codes | Empty rows skipped, valid rows processed |
| 3.4 | Valid format | All headers present with data | Process continues |

---

## 4. Component Master Tests

### Test Flow - Prefix Rules

```mermaid
flowchart TB
    subgraph CMTests["Component Master Creation"]
        C1[Process Item from Excel] --> C2{CM already exists?}
        C2 -->|Yes| C3{Excel has Make/Buy?}
        C3 -->|Yes| C4[VERIFY: make_or_buy updated]
        C3 -->|No| C5[VERIFY: make_or_buy unchanged]
        C2 -->|No| C6[Create New CM]
    end

    subgraph PrefixRules["Item Code Prefix Rules"]
        P1[Prefix T, Y, E] --> P2[VERIFY:<br/>released_for_procurement = 'No']
        P3[Prefix M, G] --> P4[VERIFY:<br/>make_or_buy = 'Make']
        P5[Other prefixes] --> P6[VERIFY:<br/>make_or_buy = 'Buy'<br/>released_for_procurement = 'Yes']
    end

    C6 --> P1
    C6 --> P3
    C6 --> P5

    style C4 fill:#e6ffe6
    style C5 fill:#e6ffe6
    style P2 fill:#e6ffe6
    style P4 fill:#e6ffe6
    style P6 fill:#e6ffe6
```

### Test Flow - Assembly vs Leaf

```mermaid
flowchart TB
    subgraph AssemblyTests["Assembly Detection"]
        A1{Has children in Excel?}
        A1 -->|Yes - Assembly| A2[VERIFY:<br/>has_bom = 1<br/>active_bom = NULL initially]
        A1 -->|No - Leaf/RM| A3[VERIFY:<br/>has_bom = 0]
    end

    subgraph LevelRules["BOM Level Rules"]
        L1{Level = 1?}
        L1 -->|Yes - Root| L2[VERIFY:<br/>project_qty = Excel qty]
        L1 -->|No - Level 2+| L3[VERIFY:<br/>project_qty = 0]
    end

    A2 --> L1
    A3 --> L1

    style A2 fill:#e6ffe6
    style A3 fill:#e6ffe6
    style L2 fill:#e6ffe6
    style L3 fill:#e6ffe6
```

### Test Cases

| # | Test Case | Test Data | Expected Result |
|---|-----------|-----------|-----------------|
| 4.1 | T-prefix item | Item code: T12345 | released_for_procurement = 'No' |
| 4.2 | Y-prefix item | Item code: Y67890 | released_for_procurement = 'No' |
| 4.3 | E-prefix item | Item code: E11111 | released_for_procurement = 'No' |
| 4.4 | M-prefix item | Item code: M22222 | make_or_buy = 'Make' |
| 4.5 | G-prefix item | Item code: G33333 | make_or_buy = 'Make' |
| 4.6 | D-prefix item | Item code: D44444 | make_or_buy = 'Buy', released = 'Yes' |
| 4.7 | Level 1 assembly | Root item with children | project_qty = Excel qty value |
| 4.8 | Level 2 item | Child item | project_qty = 0 |
| 4.9 | Assembly node | Item with children | has_bom = 1 |
| 4.10 | Leaf node | Item without children | has_bom = 0 |

---

## 5. BOM Change Detection Tests

### Test Flow

```mermaid
flowchart TB
    subgraph ChangeTests["BOM Change Detection"]
        D1[Analyze Assembly] --> D2{CM exists?}
        D2 -->|No| D3[Status: NEW<br/>Can create BOM]
        D2 -->|Yes| D4{Active BOM linked?}
        D4 -->|No| D5[Check system for BOM]
        D4 -->|Yes| D6[Compare structure hash]
        D5 --> D7{BOM found?}
        D7 -->|No| D8[Status: NEW]
        D7 -->|Yes| D9[Compare hash]
        D6 --> D10{Hash matches?}
        D9 --> D10
        D10 -->|Yes| D11[Status: UNCHANGED<br/>BOM creation skipped]
        D10 -->|No| D12[Status: CHANGED<br/>Shows diff]
    end

    style D3 fill:#e6ffe6
    style D8 fill:#e6ffe6
    style D11 fill:#fff3cd
    style D12 fill:#ffe6e6
```

### Test Flow - Loose Item Blocking

```mermaid
flowchart TB
    subgraph LooseTests["Loose Item Tests"]
        L1{CM is_loose_item = Yes?}
        L1 -->|Yes| L2{can_be_converted = Yes?}
        L2 -->|No| L3[BLOCKED<br/>'Enable can be converted to BOM']
        L2 -->|Yes| L4[Proceeds normally]
        L1 -->|No| L5[Proceeds normally]
    end

    style L3 fill:#ffe6e6
    style L4 fill:#e6ffe6
    style L5 fill:#e6ffe6
```

### Test Cases

| # | Test Case | Setup | Expected Result |
|---|-----------|-------|-----------------|
| 5.1 | First upload | No existing CM or BOM | Status: NEW, BOM created |
| 5.2 | Re-upload same | Upload same Excel again | Status: UNCHANGED, no new BOM |
| 5.3 | Changed structure | Modify children in Excel | Status: CHANGED, shows diff |
| 5.4 | Loose item blocked | CM.is_loose_item=1, can_be_converted=0 | Upload blocked with message |
| 5.5 | Loose item enabled | CM.is_loose_item=1, can_be_converted=1 | Proceeds normally |

---

## 6. Procurement Blocking Tests

### Test Flow

```mermaid
flowchart TB
    subgraph BlockingTests["Procurement Blocking"]
        B1[Changed component detected] --> B2[Check child items]
        B2 --> B3{Child has MR?}
        B3 -->|Yes| B4[Level: CONFIRM<br/>User can proceed with remarks]
        B3 -->|No| B5{Child has RFQ?}
        B5 -->|Yes| B6[Level: CONFIRM<br/>User can proceed with remarks]
        B5 -->|No| B7{Child has PO?}
        B7 -->|Yes| B8{Has Manager role?}
        B8 -->|Yes| B9[Can proceed<br/>Manager override]
        B8 -->|No| B10[BLOCKED<br/>Manager role required]
        B7 -->|No| B11[Level: CONFIRM<br/>Needs confirmation only]
    end

    style B4 fill:#fff3cd
    style B6 fill:#fff3cd
    style B9 fill:#e6ffe6
    style B10 fill:#ffe6e6
    style B11 fill:#fff3cd
```

### Test Cases

| # | Test Case | Setup | User Role | Expected Result |
|---|-----------|-------|-----------|-----------------|
| 6.1 | No procurement | Child items have no MR/RFQ/PO | Any | Confirmation required |
| 6.2 | MR exists | Child item has Material Request | Any | Confirmation required |
| 6.3 | RFQ exists | Child item has RFQ | Any | Confirmation required |
| 6.4 | PO - no role | Child item has PO | Regular user | BLOCKED: Manager required |
| 6.5 | PO - with role | Child item has PO | CM Manager | Can proceed with confirmation |

---

## 7. User Confirmation Tests

### Test Flow

```mermaid
flowchart TB
    subgraph ConfirmTests["Confirmation Flow"]
        C1[Status: requires_confirmation] --> C2[Dialog shows changed items]
        C2 --> C3[User enters remarks]
        C3 --> C4[User clicks Confirm]
        C4 --> C5[VERIFY: Remarks saved]
        C5 --> C6[VERIFY: Old BOM deactivated]
        C6 --> C7[VERIFY: New BOM created]
        C7 --> C8[VERIFY: CM.active_bom updated]
    end

    style C5 fill:#e6ffe6
    style C6 fill:#e6ffe6
    style C7 fill:#e6ffe6
    style C8 fill:#e6ffe6
```

### Test Cases

| # | Test Case | Action | Expected Result |
|---|-----------|--------|-----------------|
| 7.1 | Confirm with remarks | Enter remarks, click Confirm | Remarks saved to CM |
| 7.2 | Old BOM deactivation | After confirmation | Old BOM: is_active=0, is_default=0 |
| 7.3 | New BOM creation | After confirmation | New BOM created & submitted |
| 7.4 | CM linking | After confirmation | CM.active_bom = new BOM name |

---

## 8. BOM Creation & Linking Tests

### Test Flow

```mermaid
flowchart TB
    subgraph BOMTests["BOM Creation"]
        B1[Approved for creation] --> B2{Assembly node?}
        B2 -->|No - Leaf| B3[No BOM created]
        B2 -->|Yes| B4{In approved list?}
        B4 -->|No| B5[BOM creation skipped]
        B4 -->|Yes| B6[BOM created with:<br/>- Correct parent item<br/>- All children<br/>- Correct quantities<br/>- Project linked]
        B6 --> B7[BOM submitted]
        B7 --> B8[BOM is_active=1, is_default=1]
    end

    style B3 fill:#fff3cd
    style B5 fill:#fff3cd
    style B6 fill:#e6ffe6
    style B7 fill:#e6ffe6
    style B8 fill:#e6ffe6
```

### Test Flow - Hierarchy Codes

```mermaid
flowchart TB
    subgraph HierarchyTests["Hierarchy Code Population"]
        H1[After BOM linked] --> H2{Item is M-code?}
        H2 -->|Yes| H3[VERIFY:<br/>m_code = item_code<br/>g_code = NULL]
        H2 -->|No| H4{Item is G-code?}
        H4 -->|Yes| H5[VERIFY:<br/>g_code = item_code<br/>m_code from parent]
        H4 -->|No| H6[VERIFY:<br/>Inherits from parent]
        H3 --> H7[VERIFY: parent_component linked]
        H5 --> H7
        H6 --> H7
    end

    style H3 fill:#e6ffe6
    style H5 fill:#e6ffe6
    style H6 fill:#e6ffe6
    style H7 fill:#e6ffe6
```

### Test Cases

| # | Test Case | Setup | Expected Result |
|---|-----------|-------|-----------------|
| 8.1 | Leaf item | Item with no children | No BOM created |
| 8.2 | Assembly item | Item with children | BOM created with all children |
| 8.3 | BOM submission | After creation | docstatus=1, is_active=1, is_default=1 |
| 8.4 | CM linking | After BOM submitted | CM.active_bom = BOM name |
| 8.5 | M-code hierarchy | Item starting with M | m_code = item_code |
| 8.6 | G-code hierarchy | Item starting with G | g_code = item_code, m_code from parent |
| 8.7 | BOM Usage | After linking | Component BOM Usage records created |

---

## 9. Output Verification Tests

### Test Flow

```mermaid
flowchart TB
    subgraph OutputTests["Output Verification"]
        O1[Process Complete] --> O2[Summary Dialog]
        O2 --> O3[Items: created / existing / updated / failed]
        O2 --> O4[BOMs: created / existing / failed]
        O2 --> O5[CMs: created / existing / updated / failed]
        O3 --> O6[VERIFY: Totals correct]
        O4 --> O6
        O5 --> O6
        O6 --> O7{Any failures?}
        O7 -->|Yes| O8[VERIFY: Error Log entries]
        O7 -->|No| O9[Clean completion]
    end

    style O6 fill:#e6ffe6
    style O8 fill:#fff3cd
    style O9 fill:#e6ffe6
```

### Test Cases

| # | Test Case | Setup | Expected Result |
|---|-----------|-------|-----------------|
| 9.1 | Summary counts | Complete upload | All counts match actual operations |
| 9.2 | Error logging | Simulate item creation failure | Error logged to Error Log doctype |
| 9.3 | Partial success | Some items fail, others succeed | Failures counted, successes processed |

---

## 10. Complete Test Data Checklist

| # | Test Scenario | Required Test Data | Expected Result |
|---|---------------|-------------------|-----------------|
| 1 | Valid upload - new items | Excel with new item codes, Project, Machine Code | All items, CMs, BOMs created |
| 2 | Re-upload same data | Same Excel uploaded again | Status: UNCHANGED, no new BOMs |
| 3 | Changed BOM structure | Excel with modified children | Status: CHANGED, requires confirmation |
| 4 | Missing Excel column | Excel without 'LivelloBom' header | Validation error with missing column |
| 5 | Loose item blocking | CM with is_loose_item=1, can_be_converted=0 | Upload blocked with message |
| 6 | MR blocking | Child item has Material Request | Confirmation required |
| 7 | PO blocking - no role | Child item has PO, user lacks Manager role | Hard blocked |
| 8 | PO blocking - with role | Child item has PO, user has Manager role | Can proceed with confirmation |
| 9 | T-prefix item | Item code starting with 'T' | released_for_procurement = 'No' |
| 10 | M-prefix item | Item code starting with 'M' | make_or_buy = 'Make' |
| 11 | Level 1 assembly | Root assembly in Excel | project_qty = Excel qty |
| 12 | Level 2+ item | Child item in Excel | project_qty = 0 |

---

## 11. Return Status Quick Reference

| Status | Reason | User Action |
|--------|--------|-------------|
| `success` | - | None - upload complete |
| `blocked` | `loose_items_not_enabled` | Enable 'Can be converted to BOM' on loose items |
| `manager_required` | `active_po_no_role` | Contact Component Master Manager |
| `requires_confirmation` | - | Confirm changes with remarks |

---

## 12. Database Tables to Verify

| Table | Check After |
|-------|-------------|
| Item | Step 2 - Verify items created/updated |
| Project Component Master | Step 3 - Verify CMs with correct prefix rules |
| BOM | Step 6 - Verify BOMs created & submitted |
| BOM Item | Step 6 - Verify children added correctly |
| Component BOM Usage | Step 7 - Verify usage records populated |
