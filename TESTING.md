# Clevertech Automated Testing Framework

## Overview

This document describes the automated testing strategy for the Clevertech BOM management system, aligned with your framework design principle:

> **Ensure business-critical functionality, module integrations, and APIs are continuously validated through automated tests — across development, UAT, and production readiness cycles.**

## Test Architecture

### 1. Test Structure

```
apps/clevertech/
└── clevertech/
    └── tests/
        ├── __init__.py
        ├── test_g_code_validation.py         # G-code procurement validation
        ├── test_bom_upload.py                 # BOM upload and validation
        ├── test_component_master.py           # CM calculations and cascades
        ├── test_make_buy_cascade.py           # Make/Buy logic
        └── test_integration_procurement.py    # End-to-end procurement flow
```

### 2. Test Types

#### Unit Tests
- Test individual functions in isolation
- Fast execution (< 1s per test)
- Example: `test_calculate_bom_qty_required()`

#### Integration Tests
- Test module interactions
- Medium execution (1-5s per test)
- Example: `test_mr_validation_with_component_master()`

#### End-to-End Tests
- Test complete business workflows
- Slower execution (5-30s per test)
- Example: `test_bom_upload_to_po_creation_flow()`

## Running Tests

### Local Development

**Run all tests:**
```bash
cd /home/bharatbodh/bharatbodh-bench
bench --site clevertech-uat.bharatbodh.com run-tests --app clevertech
```

**Run specific module:**
```bash
bench --site clevertech-uat.bharatbodh.com run-tests --app clevertech --module test_g_code_validation
```

**Run specific test case:**
```bash
bench --site clevertech-uat.bharatbodh.com run-tests \
  --app clevertech \
  --module test_g_code_validation \
  --test test_g_code_validation.TestGCodeValidation.test_mr_with_bom_no_validates_against_g_code_limit
```

**Run with verbose output:**
```bash
bench --site clevertech-uat.bharatbodh.com run-tests --app clevertech --verbose
```

### CI/CD Integration

## GitHub Actions Workflow

Create `.github/workflows/tests.yml`:

```yaml
name: Clevertech Tests

on:
  push:
    branches: [main, develop, feature/*]
  pull_request:
    branches: [main, develop]
  schedule:
    # Daily sanity run at 2 AM IST
    - cron: '30 20 * * *'  # 2:30 AM IST = 20:30 UTC

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      mariadb:
        image: mariadb:10.6
        env:
          MYSQL_ROOT_PASSWORD: root
        ports:
          - 3306:3306
        options: --health-cmd="mysqladmin ping" --health-interval=10s --health-timeout=5s --health-retries=3

      redis:
        image: redis:alpine
        ports:
          - 6379:6379

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install Frappe Bench
        run: |
          pip install frappe-bench
          bench init --skip-redis-config-generation --frappe-branch version-15 frappe-bench
          cd frappe-bench
          bench set-config -g db_host 127.0.0.1
          bench set-config -g redis_cache redis://127.0.0.1:6379
          bench set-config -g redis_queue redis://127.0.0.1:6379

      - name: Install ERPNext
        run: |
          cd frappe-bench
          bench get-app --branch version-15 erpnext

      - name: Install Clevertech
        run: |
          cd frappe-bench
          bench get-app $GITHUB_WORKSPACE

      - name: Create test site
        run: |
          cd frappe-bench
          bench new-site test-site --mariadb-root-password root --admin-password admin
          bench --site test-site install-app erpnext
          bench --site test-site install-app clevertech

      - name: Run tests
        run: |
          cd frappe-bench
          bench --site test-site run-tests --app clevertech --coverage

      - name: Upload coverage report
        uses: codecov/codecov-action@v3
        with:
          file: ./frappe-bench/sites/coverage.xml
          fail_ci_if_error: true

      - name: Generate test report
        if: always()
        run: |
          cd frappe-bench
          bench --site test-site run-tests --app clevertech --junit-xml-output test-results.xml

      - name: Publish test results
        uses: EnricoMi/publish-unit-test-result-action@v2
        if: always()
        with:
          files: frappe-bench/test-results.xml
```

## Test Execution Schedule

### When Tests Run

1. **On Every Commit** (CI)
   - Runs automatically via GitHub Actions
   - Blocks merge if tests fail
   - ~10-15 minutes

2. **Before Deployment**
   - Manual trigger: `bench --site <site> run-tests --app clevertech`
   - Run before `git push` to staging/production
   - Validates deployment readiness

3. **Daily Scheduled Runs**
   - Runs at 2:30 AM IST (configured in GitHub Actions)
   - Catches regressions from external dependencies
   - Sends alert if failures detected

4. **Pre-Release Validation**
   - Run full test suite before version release
   - Includes performance benchmarks
   - Generate test report for release notes

## Test Data Management

### Test Fixtures

Create reusable test data in `tests/fixtures/`:

```python
# tests/fixtures/test_project.py
def create_test_project():
    """Create a test project with standard setup"""
    return frappe.get_doc({
        "doctype": "Project",
        "project_name": "TEST-PROJECT-001",
        "status": "Open"
    }).insert(ignore_permissions=True)

def create_test_bom_structure():
    """Create M → G → D → Raw material hierarchy"""
    # ... BOM creation logic
    pass
```

### Cleanup Strategy

```python
@classmethod
def tearDownClass(cls):
    """Clean up test data after all tests"""
    # Delete in reverse order of dependencies
    frappe.delete_doc("Material Request", cls.mr.name, force=True)
    frappe.delete_doc("Component Master", cls.cm.name, force=True)
    frappe.delete_doc("BOM", cls.bom.name, force=True)
    frappe.delete_doc("Item", cls.item.item_code, force=True)
    frappe.delete_doc("Project", cls.project.name, force=True)
    frappe.db.commit()
```

## Coverage Requirements

### Target Coverage Levels

| Module | Target | Current |
|--------|--------|---------|
| `material_request_validation.py` | 90% | TBD |
| `purchase_order_validation.py` | 90% | TBD |
| `bom_upload_enhanced.py` | 80% | TBD |
| `project_component_master.py` | 85% | TBD |
| Overall | 80% | TBD |

### Measuring Coverage

```bash
# Run tests with coverage
bench --site test-site run-tests --app clevertech --coverage

# Generate HTML report
coverage html
# Open htmlcov/index.html in browser

# Check coverage report
coverage report
```

## Test Naming Conventions

```python
# Format: test_<what>_<scenario>_<expected_result>
def test_mr_with_bom_no_validates_against_g_code_limit():
    """When MR has bom_no, should validate against G-code limit"""
    pass

def test_mr_without_bom_no_validates_against_overall_limit():
    """When MR has no bom_no, should validate against CM limit"""
    pass

def test_multiple_g_codes_have_independent_limits():
    """Each G-code should have its own independent limit"""
    pass
```

## Debugging Failed Tests

### Local Debugging

```bash
# Run with pdb debugger
bench --site test-site run-tests --app clevertech --pdb-on-exception

# Run specific failing test
bench --site test-site run-tests \
  --app clevertech \
  --module test_g_code_validation \
  --test TestGCodeValidation.test_mr_with_bom_no_validates_against_g_code_limit \
  --verbose
```

### Check Test Logs

```bash
# View bench logs
tail -f /home/bharatbodh/bharatbodh-bench/logs/bench.log

# View site logs
tail -f /home/bharatbodh/bharatbodh-bench/sites/clevertech-uat.bharatbodh.com/logs/web.log
```

## Best Practices

### 1. Test Independence
- Each test should be independent
- Use `setUp()` and `tearDown()` for test data
- Don't rely on test execution order

### 2. Test Data Isolation
- Use unique identifiers for test data (e.g., `TEST-PROJECT-001`)
- Clean up all test data in `tearDown()`
- Don't affect production data

### 3. Assertion Quality
```python
# Bad - vague error message
self.assertTrue(result)

# Good - clear error message
self.assertEqual(
    result["status"],
    "success",
    f"Expected success but got {result['status']}: {result.get('message')}"
)
```

### 4. Test Documentation
```python
def test_mr_with_bom_no_validates_against_g_code_limit(self):
    """
    Test that MR validation uses G-code aggregate limit when bom_no is present.

    Setup:
    - Component has total_qty_limit = 100
    - G-code 1 has aggregate limit = 60 (from bom_usage)
    - G-code 2 has aggregate limit = 40

    Test:
    - Create MR with bom_no pointing to G-code 1
    - Try to add 70 units (exceeds G-code limit but within overall)

    Expected:
    - Should fail with "G-code G11111111" in error message
    - Should show limit of 60, not 100
    """
    # Test implementation
```

## Performance Benchmarks

Track test performance over time:

```python
import time

def test_bom_upload_performance(self):
    """BOM upload should complete within 5 seconds for 100 items"""
    start = time.time()

    # Upload BOM with 100 items
    result = upload_bom(excel_file)

    duration = time.time() - start
    self.assertLess(duration, 5.0, f"Upload took {duration}s, expected < 5s")
```

## Continuous Improvement

### Monthly Test Review
1. Review test coverage reports
2. Identify untested code paths
3. Add tests for recently fixed bugs
4. Remove obsolete tests

### Test Metrics Dashboard
Track over time:
- Test count by module
- Code coverage %
- Average test execution time
- Test failure rate
- Time to fix failing tests

## Getting Started

### Step 1: Create your first test

```bash
# Copy template
cp tests/test_g_code_validation.py tests/test_my_feature.py

# Edit test file
# Add your test cases

# Run your test
bench --site test-site run-tests --app clevertech --module test_my_feature
```

### Step 2: Add to CI/CD

```bash
# Commit test file
git add tests/test_my_feature.py
git commit -m "Add tests for my feature"
git push

# Tests will run automatically on GitHub Actions
```

### Step 3: Monitor results

- Check GitHub Actions tab for test results
- View coverage report in PR
- Fix any failing tests before merge

---

## Support

**Questions?**
- Check existing tests for examples
- Read Frappe testing docs: https://frappeframework.com/docs/user/en/testing
- Ask team for help

**Found a bug in tests?**
- Create issue in GitHub
- Tag with `testing` label
- Provide test output and logs
