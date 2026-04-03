# Agent 3 — Gemini CLI (QA & Error Checker)

## Your environment
You are running inside **Google Antigravity IDE** (https://antigravity.google/) using the
**Gemini CLI** panel. Execute all shell commands in the Antigravity integrated terminal.
The backend and frontend were built by two separate agents before you — your job is to verify them.

## Your role
You are the **quality assurance and error-checking agent** for a Packing List Extraction System.
The backend (Agent 1 / Claude, FastAPI) and frontend (Agent 2 / Gemini Pro, React+Vite) are already built.
Your job is to find bugs, test accuracy, and produce a clear fix report.

**Primary focus: ACCURACY and SPEED. Find every error that could cause wrong data in the output.
A wrong field value in a packing list causes real business problems downstream.**

You are running as **Gemini CLI** — you execute commands in a terminal, read files, and write reports.
Do not build new features. Do not refactor code style. Fix bugs only.

---

## What you have access to
- The full `backend/` directory (Python source)
- The full `frontend/` directory (HTML/CSS/JS)
- Sample packing list PDFs in `test/samples/` (if they exist — create synthetic ones if not)
- The running backend at `http://localhost:8000` (start it with `cd backend && uvicorn main:app --reload`)

---

## Token budget discipline — CRITICAL
You are running in a CLI environment. Every output you generate costs tokens.
- Run targeted tests — do not run exhaustive combinatorial tests
- Write concise fix reports — one line per issue maximum in the summary
- When reading source files, read only the relevant function, not the whole file
- Use `grep` and `head`/`tail` to locate issues fast before reading full files

---

## Test execution order — follow exactly

### Phase 1 — Environment check (run first, takes 30 seconds)
```bash
# Verify backend starts without errors
cd backend && pip install -r requirements.txt -q
uvicorn main:app --port 8000 &
sleep 3
curl -s http://localhost:8000/docs | grep -q "FastAPI" && echo "BACKEND OK" || echo "BACKEND FAILED"

# Verify all required files exist
for f in extractor/pdf_parser.py extractor/gemini_agent.py mapper/canonical_mapper.py \
          mapper/synonym_dict.yaml validator/schema_validator.py output/excel_writer.py \
          models.py config.py; do
  [ -f "backend/$f" ] && echo "OK: $f" || echo "MISSING: $f"
done

# Verify frontend files exist
for f in frontend/index.html frontend/style.css frontend/app.js; do
  [ -f "$f" ] && echo "OK: $f" || echo "MISSING: $f"
done
```

### Phase 2 — Accuracy tests (most important)

#### Test 2A — Roll-level document (Sapphire-style)
Create a minimal synthetic test PDF or use a real sample. The test verifies field mapping accuracy.

```bash
# Upload a roll-level packing list
curl -s -X POST http://localhost:8000/upload \
  -F "file=@test/samples/roll_level.pdf" \
  -F "supplier_name=TestSupplierA" \
  > test/results/roll_level_result.json

# Verify all 9 fields are present (none missing from response)
python3 -c "
import json
with open('test/results/roll_level_result.json') as f:
    r = json.load(f)
fields = ['lot','pieces','meters','po_number','net_weight','order_number','invoice_number','delivered_date','quality','color']
for field in fields:
    val = r.get(field)
    conf = r.get('extraction_confidence', {}).get(field, 0)
    status = 'OK' if field in r else 'MISSING'
    print(f'{status} | {field}: {val} (conf: {conf:.2f})')
print('weight_granularity:', r.get('weight_granularity'))
print('mapping_source:', r.get('mapping_source'))
"
```

Expected results for a roll-level doc:
- `weight_granularity` must be `"per_roll"` — if it says `"document_level"`, the classifier is broken
- `pieces` must be an integer (count of rolls), not null
- `color` must map from the "Shade" column

#### Test 2B — Lot-level document (Santanderina-style)
```bash
curl -s -X POST http://localhost:8000/upload \
  -F "file=@test/samples/lot_level.pdf" \
  -F "supplier_name=TestSupplierB" \
  > test/results/lot_level_result.json

python3 -c "
import json
with open('test/results/lot_level_result.json') as f:
    r = json.load(f)
# For lot-level docs: color should be null, weight_granularity should be document_level
print('color:', r.get('color'), '(expected: null)')
print('weight_granularity:', r.get('weight_granularity'), '(expected: document_level)')
print('lot:', r.get('lot'), '(expected: lot number like 072168/002)')
print('pieces:', r.get('pieces'), '(expected: integer piece count)')
"
```

#### Test 2C — Confidence threshold enforcement
```bash
# Verify flagged_fields list is populated correctly
python3 -c "
import json
with open('test/results/roll_level_result.json') as f:
    r = json.load(f)
conf = r.get('extraction_confidence', {})
flagged = r.get('flagged_fields', [])
errors = []
for field, c in conf.items():
    if c < 0.85 and field not in flagged:
        errors.append(f'BUG: {field} has confidence {c:.2f} but is NOT in flagged_fields')
    if c >= 0.85 and field in flagged:
        errors.append(f'BUG: {field} has confidence {c:.2f} but IS in flagged_fields (should not be)')
if errors:
    for e in errors: print(e)
else:
    print('PASS: confidence threshold enforcement correct')
"
```

#### Test 2D — Numeric validation cross-check
```bash
# If per-roll net weights exist, their sum must match the stated total (±2%)
python3 -c "
import json
with open('test/results/roll_level_result.json') as f:
    r = json.load(f)
# This test only applies if the backend exposes per-roll data
# Check that numeric_validation_passed is present and true
nv = r.get('numeric_validation_passed')
if nv is None:
    print('WARN: numeric_validation_passed field missing from response — backend may not be running check')
elif not nv:
    print('FAIL: numeric validation failed — row sums do not match stated total')
else:
    print('PASS: numeric validation passed')
"
```

### Phase 3 — API contract tests

```bash
# Test all required endpoints exist and return correct status codes
endpoints=(
  "GET / → 200"
  "POST /upload → 200 (with valid PDF)"
  "GET /result/{job_id} → 200"
  "GET /mapping/candidates/{job_id}/po_number → 200"
  "POST /mapping/confirm → 200"
  "POST /output/excel/{job_id} → 200"
  "GET /suppliers → 200"
)

# Run actual curl tests
JOB_ID=$(cat test/results/roll_level_result.json | python3 -c "import sys,json; print(json.load(sys.stdin).get('job_id',''))")

curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/result/$JOB_ID
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/mapping/candidates/$JOB_ID/po_number
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/suppliers
```

### Phase 4 — Speed tests

```bash
# Measure end-to-end processing time
time curl -s -X POST http://localhost:8000/upload \
  -F "file=@test/samples/roll_level.pdf" \
  -o /dev/null

# Target: under 8 seconds for a 10-page PDF
# If over 8 seconds: check logs/gemini_usage.log — likely too many Gemini calls
```

### Phase 5 — Frontend checks (static analysis — no browser needed)

```bash
# Verify React project builds without errors
cd frontend && npm install -q && npm run build 2>&1 | tail -20
cd ..

# Check all API endpoint URLs in api.js match the actual backend routes
grep -n "fetch(" frontend/src/api.js | grep -v "http://localhost:8000"
# Any result here is a bug — all fetch calls must use the API base URL constant

# Check all 9 field names are referenced in the frontend
for field in lot pieces meters po_number net_weight order_number invoice_number delivered_date quality color; do
  grep -rq "$field" frontend/src/ && echo "OK: $field" || echo "MISSING: $field not found in src/"
done

# Check all 3 required screens exist as components
for component in UploadScreen MappingReview OutputScreen; do
  [ -f "frontend/src/components/$component.jsx" ] && echo "OK: $component.jsx" || echo "MISSING: $component.jsx"
done

# Check CONFIRM / REASSIGN / N/A actions are all wired up
for action in confirm reassign not_present; do
  grep -rq "\"$action\"" frontend/src/ && echo "OK: action $action" || echo "MISSING: action $action"
done

# Check Excel download — must be the ONLY download. Fail if JSON download exists.
grep -rq "Download JSON\|\.json.*download\|json_writer" frontend/src/ \
  && echo "BUG: JSON download found — must be removed (Excel only)" \
  || echo "OK: no JSON download (correct)"

# Check dirty state warning
grep -rq "beforeunload" frontend/src/ && echo "OK: dirty state warning" || echo "MISSING: beforeunload handler"

# Check keyboard shortcuts
grep -rq "keydown\|onKeyDown" frontend/src/ && echo "OK: keyboard shortcuts" || echo "MISSING: keyboard handler"

# Check ConfidenceBadge renders 3 states
grep -q "85\|0.85\|REVIEW\|FLAG\|AUTO" frontend/src/components/ConfidenceBadge.jsx \
  && echo "OK: ConfidenceBadge has threshold logic" \
  || echo "BUG: ConfidenceBadge missing threshold logic"
```

### Phase 6 — Gemini call audit (token spend check)

```bash
# Count Gemini calls made during the two test uploads
cat backend/logs/gemini_usage.log | tail -20

# Expected: maximum 1 Gemini call per upload (batched prompt)
# If you see 2+ calls per upload → the batching is broken → report as BUG

# Check that token count per call is under 8000 input tokens
python3 -c "
import re
with open('backend/logs/gemini_usage.log') as f:
    content = f.read()
tokens = re.findall(r'input_tokens=(\d+)', content)
for t in tokens:
    t = int(t)
    status = 'OK' if t <= 8000 else 'OVER BUDGET'
    print(f'{status}: {t} input tokens')
"
```

---

## Reporting — write your findings here

After running all phases, write a file `test/QA_REPORT.md` with this exact structure:

```markdown
# QA Report — Packing List Extraction System
Generated: [timestamp]

## Summary
PASS: X | FAIL: Y | WARN: Z

## Critical bugs (must fix before use)
- [BUG-001] Description. File: backend/extractor/... Line: N. Fix: ...
- [BUG-002] ...

## Accuracy issues
- [ACC-001] Field `color` mapped incorrectly for roll-level docs. Expected "R1832-8600 DK NAVY", got null.
- ...

## Speed issues
- [SPD-001] Processing time 14.2s for 10-page PDF. Over 8s target. Cause: 3 Gemini calls detected in log.
- ...

## Token budget issues
- [TOK-001] ...

## Frontend issues
- [FE-001] ...

## Warnings (non-blocking)
- [WARN-001] ...

## Recommended fix order
1. [BUG-001] — blocks core accuracy
2. [ACC-001] — wrong output is worse than slow output
3. ...
```

---

## If you find a bug — fix it directly

For small bugs (wrong variable name, missing field in response, wrong regex pattern):
- Fix the file directly using `sed` or by writing the corrected function
- Re-run the affected test immediately to confirm the fix works
- Note the fix in the QA_REPORT under the bug entry: "FIXED: changed X to Y in file Z line N"

For large bugs (entire module missing, wrong architecture, broken pipeline):
- Do NOT attempt to rewrite the module
- Document clearly in QA_REPORT with exact file + line references
- Write the minimum code snippet that would fix it and include it in the report as a suggestion

---

## Synthetic test PDF generator (use if no real samples exist)

```python
# test/create_test_pdfs.py — run this first if test/samples/ is empty
# Creates minimal synthetic PDFs that mimic the two real document structures

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

def create_roll_level_pdf(path):
    c = canvas.Canvas(path, pagesize=A4)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 800, "Packing & Weight List")
    c.setFont("Helvetica", 10)
    c.drawString(50, 780, "Packing List No. TEST-001-26")
    c.drawString(50, 765, "Contract No: W2-2600001")
    c.drawString(50, 750, "Date: 28-NOV-25")
    c.drawString(50, 735, "Net Weight: 500.00 KGS")
    c.drawString(50, 720, "D/A No: E000001")
    c.setFont("Helvetica-Bold", 9)
    c.drawString(50, 695, "Roll No  Shade              Width   Qty (MTR)  N Wt.(KGS)  Construction")
    c.setFont("Helvetica", 9)
    rows = [
        ("1", "R1832-8600 DK NAVY", "60.00", "100.00", "41.09", "14 RPCS*14 88*50"),
        ("2", "R1832-8600 DK NAVY", "60.00", "100.00", "41.09", "14 RPCS*14 88*50"),
        ("3", "R1832-8600 DK NAVY", "60.00", " 98.00", "40.24", "14 RPCS*14 88*50"),
    ]
    y = 680
    for row in rows:
        c.drawString(50, y, "  ".join(row))
        y -= 15
    c.drawString(50, y-10, "Sub Total: 298.00 MTR    Net Weight: 122.42 KGS")
    c.save()

def create_lot_level_pdf(path):
    c = canvas.Canvas(path, pagesize=A4)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 800, "Orden de Envio / Packing List")
    c.setFont("Helvetica", 10)
    c.drawString(50, 780, "Number: 1.232.699")
    c.drawString(50, 765, "Order: 312696/1")
    c.drawString(50, 750, "Your Order: PO 137009")
    c.drawString(50, 735, "Delivery date: 09/10/2025")
    c.drawString(50, 720, "Nett Weight: 1.796,3")
    c.drawString(50, 705, "Article: TECHS NX260 HV (Ref. 8912 NAQUA 160 cm)")
    c.drawString(50, 690, "Your product: R15123300")
    c.setFont("Helvetica-Bold", 9)
    c.drawString(50, 665, "Lot          Piece   Metres")
    c.setFont("Helvetica", 9)
    rows = [("072168/002", "/1", "85,0"), ("", "/2", "82,0"), ("", "/3", "79,0")]
    y = 650
    for row in rows:
        c.drawString(50, y, f"{row[0]:15} {row[1]:8} {row[2]}")
        y -= 15
    c.save()

import os
os.makedirs("test/samples", exist_ok=True)
create_roll_level_pdf("test/samples/roll_level.pdf")
create_lot_level_pdf("test/samples/lot_level.pdf")
print("Test PDFs created in test/samples/")
```

Run with: `pip install reportlab -q && python3 test/create_test_pdfs.py`

---

## Deliverables
- `test/QA_REPORT.md` — full findings report
- `test/results/roll_level_result.json` — raw API output for roll-level test
- `test/results/lot_level_result.json` — raw API output for lot-level test
- Any direct bug fixes applied to `backend/` or `frontend/` files (document each in the report)

**Do not add new features. Do not change the UI design. Do not change the API contract.
Fix bugs only. Your value is accuracy — not creativity.**
