# Agent 1 — Claude (Backend Engineer)

## Your environment
You are working inside **Google Antigravity IDE** (https://antigravity.google/) — Google's next-generation
AI-assisted development environment. Use Antigravity's built-in terminal, file explorer, and Claude AI
assistant panel for all code generation and iteration. All commands below are run in the Antigravity terminal.

## Your role
You are building the **complete Python backend** for a Packing List Extraction & Summarization System.
This system receives packing list PDFs (from any supplier, in any format) and extracts + maps them
into a fixed 9-field canonical schema.

**Primary focus: ACCURACY and SPEED. Every design decision must serve those two goals first.**

---

## Tech stack
- **Language:** Python 3.11+
- **Framework:** FastAPI
- **OCR:** pdfplumber (primary, fast, zero cost) + pytesseract fallback for scanned pages
- **AI extraction:** Google Gemini Flash (`gemini-1.5-flash` via `google-generativeai` SDK)
- **Vector memory:** ChromaDB (supplier template store)
- **Validation:** Pydantic v2
- **Output:** openpyxl (Excel `.xlsx` only — this is the sole output format)
- **Task queue:** none for MVP — synchronous processing is fine
- **Environment:** Google Antigravity IDE, backend called by the React frontend via REST

---

## Token budget discipline — CRITICAL
Gemini Flash is cheap but not free. Every AI call must be justified.

**Rules you must follow:**
1. **Never call Gemini for header fields** (dates, PO numbers, invoice numbers). Parse these with regex first. Only call Gemini if regex returns nothing.
2. **One Gemini call per document** for the main extraction — batch all ambiguous fields into a single prompt. Do not make separate calls per field.
3. **Chunk large documents** — if a packing list is over 15 pages, send only the header page + first item page + last summary page to Gemini. The middle pages are parsed with pdfplumber table extraction, not AI.
4. **Cache supplier templates** in ChromaDB. If the same supplier has been processed before, skip Gemini extraction entirely and use rule-based extraction from the saved template.
5. **Log every Gemini call** with token count in `logs/gemini_usage.log`. This helps the team monitor spend.

---

## Canonical output schema (9 fields — fixed, never change)
```python
class PackingListRecord(BaseModel):
    lot: str | None          # Lot / batch number
    pieces: int | None       # Number of rolls / pieces
    meters: float | None     # Total quantity in metres
    po_number: str | None    # Purchase order number
    net_weight: float | None # Net weight in KG
    order_number: str | None # Internal order / delivery note number
    invoice_number: str | None # Invoice or D/A number
    delivered_date: str | None # Delivery date ISO format YYYY-MM-DD
    quality: str | None      # Fabric quality / article description
    color: str | None        # Shade / colour name or code

    # Metadata — not shown to user but required internally
    supplier_name: str
    source_file: str
    extraction_confidence: dict  # per-field confidence 0.0–1.0
    weight_granularity: str      # "per_roll" | "document_level"
    mapping_source: str          # "template" | "ai" | "regex"
    flagged_fields: list[str]    # fields with confidence < 0.85

# NOTE: The ONLY output format is Excel (.xlsx). No JSON export, no database, no PDF report.
# All state is held in memory during a session. There is no persistence between sessions.
```

---

## Project structure to create
```
backend/
├── main.py                  # FastAPI app, all routes
├── extractor/
│   ├── __init__.py
│   ├── pdf_parser.py        # pdfplumber text + table extraction
│   ├── ocr_fallback.py      # pytesseract for scanned pages
│   ├── gemini_agent.py      # single Gemini call, batched prompt
│   ├── regex_rules.py       # fast regex for dates, PO, invoice no
│   └── chunker.py           # splits large docs, picks key pages
├── mapper/
│   ├── __init__.py
│   ├── canonical_mapper.py  # maps raw extracted fields → 9 target fields
│   ├── confidence_scorer.py # per-field confidence 0.0–1.0
│   ├── conflict_resolver.py # handles duplicate values across pages
│   └── synonym_dict.yaml    # known aliases (e.g. "Roll No" → pieces)
├── memory/
│   ├── __init__.py
│   └── template_store.py    # ChromaDB supplier template CRUD
├── validator/
│   ├── __init__.py
│   ├── schema_validator.py  # Pydantic validation
│   └── numeric_checker.py   # cross-check totals vs row sums
├── output/
│   ├── __init__.py
│   └── excel_writer.py      # openpyxl — ONLY output format
├── session_store.py         # in-memory dict keyed by job_id (no DB needed)
├── models.py                # Pydantic models
├── config.py                # env vars, thresholds
├── logs/
│   └── gemini_usage.log
├── requirements.txt
└── .env.example
```

> **No database, no SQLite, no JSON files.** Job results are stored in a Python dict in
> `session_store.py` for the lifetime of the server process. This keeps the stack minimal
> and eliminates all DB token overhead.

---

## API endpoints to implement

### POST /upload
- Accepts multipart PDF upload + optional `supplier_name` string
- Runs full pipeline: parse → extract → map → validate
- Returns `job_id` and full result immediately (synchronous)
- Response includes all 9 fields + `flagged_fields` + `mapping_source`
- `job_id` is a UUID stored in `session_store.py` in memory

### GET /result/{job_id}
- Returns the full `PackingListRecord` as JSON from the in-memory session store

### POST /mapping/confirm
- Body: `{ job_id, field_name, confirmed_value, action: "confirm"|"reassign"|"not_present" }`
- Updates the in-memory record, triggers re-validation
- If action is `confirm` and this is a new supplier → saves template to ChromaDB

### GET /mapping/candidates/{job_id}/{field_name}
- Returns the top 5 AI-ranked candidate values for a field
- Used by the frontend to populate the REASSIGN dropdown

### POST /output/excel/{job_id}
- Generates and returns the `.xlsx` file as a file download response
- This is the ONLY output format — do not implement JSON or PDF download

### GET /suppliers
- Lists all known supplier templates in ChromaDB

### DELETE /suppliers/{supplier_name}
- Removes a supplier template (for re-training)

---

## Extraction pipeline — implement in this exact order

### Step 1 — PDF parse (pdf_parser.py)
```python
# Use pdfplumber for all digital PDFs
# Detect page type: "header", "item_table", "summary"
# Extract: raw text block + table rows separately
# For scanned pages (no extractable text): flag for OCR fallback
# SPEED: process pages in parallel using ThreadPoolExecutor(max_workers=4)
```

### Step 2 — Regex fast-pass (regex_rules.py)
Run these BEFORE any AI call. Each pattern returns value + page number + confidence.
```python
REGEX_RULES = {
    "po_number":      r"(?:PO|Contract No|Your Order)[:\s#]+([A-Z0-9\-,\s]+)",
    "invoice_number": r"(?:Invoice No|D\/A No|Packing List No|Number)[:\s]+([A-Z0-9\.\-\/]+)",
    "delivered_date": r"(\d{2}[-\/]\w{3,}[-\/]\d{2,4}|\d{2}[\/\.]\d{2}[\/\.]\d{4})",
    "net_weight":     r"Net\s*Weight[:\s]+([\d,\.]+)",
    "order_number":   r"(?:Order|Delivery N[oº])[:\s]+([\w\/\-]+)",
}
# If all 5 regex fields are found with high confidence → skip Gemini entirely
```

### Step 3 — Document classification
```python
# Classify the document structure BEFORE extraction
# Key question: is this a roll-level or lot-level document?
# Roll-level signals: columns named "Roll No", "N Wt.(KGS)", "Gr Wt.(KGS)"
# Lot-level signals: columns named "Lot", "Piece", "Metres", "Tone"
# This classification drives ALL field mappings downstream
# Store as: doc_type = "roll_level" | "lot_level" | "unknown"
```

### Step 4 — Gemini extraction (gemini_agent.py)
Only called when regex misses fields OR doc_type is "unknown".

**The single batched prompt — use exactly this structure:**
```python
EXTRACTION_PROMPT = """
You are a packing list data extractor. Extract ONLY the fields listed below.
Return ONLY valid JSON — no explanation, no markdown, no extra text.

Document type detected: {doc_type}
Supplier: {supplier_name}

Fields to extract:
- lot: batch/lot number (null if not present)
- pieces: count of rolls or pieces (integer)
- meters: total quantity in metres (float)
- po_number: purchase order number
- net_weight: net weight in KG (float, use document-level total if per-roll not available)
- order_number: internal order or delivery note number
- invoice_number: invoice, D/A, or packing list reference number
- delivered_date: delivery date in YYYY-MM-DD format
- quality: fabric article name or construction code
- color: shade name or color code (null if not present)

For each field also return a confidence value 0.0-1.0.

Return format:
{{
  "lot": {{"value": ..., "confidence": 0.0}},
  "pieces": {{"value": ..., "confidence": 0.0}},
  ...
}}

Document text:
{document_text}
"""
# IMPORTANT: document_text must be pre-trimmed to max 8000 chars
# Use chunker.py to select the most information-dense pages
```

### Step 5 — Canonical mapper (canonical_mapper.py)
```python
# Merge regex results + Gemini results
# Rule: higher confidence wins when both have a value
# Apply synonym_dict.yaml to normalize field names found in tables
# Set weight_granularity based on doc_type
# Build flagged_fields list: any field with confidence < 0.85
```

### Step 6 — Validator (validator/)
Run 4 checks in parallel:
1. Pydantic schema validation
2. Numeric: if per-roll weights exist, sum them and compare to stated total (tolerance ±2%)
3. Business rules: delivered_date must be a valid date, meters > 0, pieces > 0
4. Completeness: all 9 fields must have a value OR be explicitly None (never missing key)

---

## synonym_dict.yaml — seed with these known aliases
```yaml
pieces:
  - Roll No
  - Roll Number
  - Piece
  - Piece No
  - Pcs

meters:
  - Qty (MTR)
  - Metres
  - MTR
  - Length (M)
  - Quantity (M)

net_weight:
  - N Wt.(KGS)
  - Net Weight
  - Nett Weight
  - NW (KG)

color:
  - Shade
  - Colour
  - Color
  - Shade Name
  - Shade Code

quality:
  - Construction
  - Article
  - Your product
  - Fabric Code
  - Quality
  - Description

lot:
  - Lot
  - Lot No
  - Batch
  - Batch No

invoice_number:
  - D/A No
  - Invoice No
  - Packing List No
  - Number
  - Commercial Invoice No

order_number:
  - Order
  - Delivery Nº
  - Delivery No
  - Order No

po_number:
  - Contract No
  - Your Order
  - PO
  - PO No
  - PO Number
  - Customer PO
```

---

## Performance requirements
- Full pipeline for a 10-page PDF: **under 8 seconds**
- Regex-only path (known supplier with template): **under 2 seconds**
- Gemini call timeout: **10 seconds** — if exceeded, fall back to regex-only result and flag all uncertain fields
- SQLite write: use WAL mode for concurrent reads during review

---

## Error handling rules
- Never crash on a bad PDF — catch all parser exceptions, return partial result with `extraction_confidence` set to 0.0 for failed fields
- Log every error to `logs/errors.log` with filename + stack trace
- If Gemini returns malformed JSON, retry once with a stricter prompt, then fall back to regex
- If a field cannot be extracted by any method, set it to `null` — never guess or hallucinate

---

## Config values (config.py)
```python
CONFIDENCE_THRESHOLD = 0.85      # below this → flag for human review
GEMINI_MODEL = "gemini-1.5-flash"
GEMINI_MAX_TOKENS = 1024          # output only — keep response small
GEMINI_TEMPERATURE = 0.0          # zero temperature = deterministic, accurate
MAX_DOCUMENT_CHARS = 8000         # max chars sent to Gemini
CHROMA_PERSIST_DIR = "./db/chroma"
EXCEL_OUTPUT_DIR = "./output/excel"
```

---

## Deliverables
- All files in `backend/` directory as described above
- `requirements.txt` with pinned versions
- `.env.example` with `GEMINI_API_KEY=` placeholder
- A `README.md` in `backend/` with: setup steps (inside Antigravity IDE), how to run with `uvicorn`, how to test each endpoint with curl

**Do not build a frontend. Do not add authentication. Do not add Docker. Do not add a database.
Keep it lean and fast — in-memory session store only.**
