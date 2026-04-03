# Packing List Extraction Backend

A FastAPI backend that receives packing list PDFs from any supplier and extracts them into a fixed **9-field canonical schema**, outputting an Excel `.xlsx` file.

---

## Architecture Overview

```
PDF Upload
    │
    ▼
pdf_parser.py        ← pdfplumber, parallel page processing (4 workers)
    │
    ▼ (scanned pages)
ocr_fallback.py      ← pytesseract fallback
    │
    ▼
chunker.py           ← classify doc type + select key pages for Gemini
    │
    ▼
regex_rules.py       ← fast regex for dates, PO#, invoice# (always first)
    │
    ├──▶ template_store.py  ← ChromaDB cache: skip Gemini if known supplier
    │
    ▼ (only if regex misses fields or doc_type unknown)
gemini_agent.py      ← single batched Gemini call (1 call per document)
    │
    ▼
canonical_mapper.py  ← merge all sources, resolve conflicts, coerce types
    │
    ▼
schema_validator.py  ← Pydantic + business rules (parallel, 4 checks)
numeric_checker.py   ← cross-check row weight sums vs stated total
    │
    ▼
session_store.py     ← in-memory Python dict, no DB
    │
    ▼
excel_writer.py      ← openpyxl .xlsx output (ONLY format)
```

---

## Setup (inside Antigravity IDE)

### 1. Create and activate a virtual environment

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell
# source .venv/bin/activate     # macOS / Linux
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

> **Note on OCR fallback:**  
> `pytesseract` requires [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) installed on the system.  
> `pdf2image` requires [Poppler](https://github.com/oschwartz10612/poppler-windows/releases) on Windows.  
> If neither is installed, scanned-page OCR is silently skipped — digital PDFs work without them.

### 3. Configure environment

```bash
copy .env.example .env      # Windows
# cp .env.example .env      # macOS / Linux
```

Open `.env` and set your Gemini API key:

```
GEMINI_API_KEY=your_actual_key_here
```

Get a free key from: https://aistudio.google.com/app/apikey

---

## Running the Server

```bash
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

The API is available at: `http://localhost:8080`  
Interactive docs (Swagger UI): `http://localhost:8080/docs`  
Alternative docs (ReDoc): `http://localhost:8080/redoc`

---

## API Endpoints

### `POST /upload` — Upload a packing list PDF

```bash
curl -X POST http://localhost:8080/upload \
  -F "file=@/path/to/packing_list.pdf" \
  -F "supplier_name=ACME Textiles"
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "done",
  "result": {
    "lot": "LOT-001",
    "pieces": 42,
    "meters": 2150.5,
    "po_number": "PO-2024-001",
    "net_weight": 850.3,
    "order_number": "ORD-9988",
    "invoice_number": "INV-20240115",
    "delivered_date": "2024-01-15",
    "quality": "100% Cotton 40/40",
    "color": "Navy Blue",
    "supplier_name": "ACME Textiles",
    "source_file": "packing_list.pdf",
    "extraction_confidence": { "lot": 0.9, "pieces": 0.88, ... },
    "flagged_fields": [],
    "mapping_source": "ai"
  }
}
```

---

### `GET /result/{job_id}` — Retrieve a result

```bash
curl http://localhost:8080/result/550e8400-e29b-41d4-a716-446655440000
```

---

### `POST /mapping/confirm` — Confirm or reassign a field

```bash
# Confirm a value as-is
curl -X POST http://localhost:8080/mapping/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "field_name": "po_number",
    "confirmed_value": "PO-2024-001",
    "action": "confirm"
  }'

# Reassign to a different value
curl -X POST http://localhost:8080/mapping/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "field_name": "color",
    "confirmed_value": "Royal Blue",
    "action": "reassign"
  }'

# Mark field as not present in this document
curl -X POST http://localhost:8080/mapping/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "field_name": "lot",
    "confirmed_value": null,
    "action": "not_present"
  }'
```

---

### `GET /mapping/candidates/{job_id}/{field_name}` — Get reassign options

```bash
curl "http://localhost:8080/mapping/candidates/550e8400-e29b-41d4-a716-446655440000/color"
```

**Response:**
```json
{
  "job_id": "...",
  "field_name": "color",
  "candidates": ["Navy Blue", "NB", "Blue Navy", "Royal Blue"]
}
```

---

### `POST /output/excel/{job_id}` — Download the Excel file

```bash
curl -X POST "http://localhost:8080/output/excel/550e8400-e29b-41d4-a716-446655440000" \
  --output packing_list.xlsx
```

> ⚠️ This is the **only** supported output format.

---

### `GET /suppliers` — List known supplier templates

```bash
curl http://localhost:8080/suppliers
```

---

### `DELETE /suppliers/{supplier_name}` — Delete a supplier template

```bash
curl -X DELETE "http://localhost:8080/suppliers/ACME%20Textiles"
```

---

## Canonical Schema (9 Fields — Never Changes)

| Field            | Type    | Description                         |
|-----------------|---------|-------------------------------------|
| `lot`           | str     | Lot / batch number                  |
| `pieces`        | int     | Number of rolls / pieces            |
| `meters`        | float   | Total quantity in metres            |
| `po_number`     | str     | Purchase order number               |
| `net_weight`    | float   | Net weight in KG                    |
| `order_number`  | str     | Internal order / delivery note no.  |
| `invoice_number`| str     | Invoice or D/A number               |
| `delivered_date`| str     | Delivery date ISO format YYYY-MM-DD |
| `quality`       | str     | Fabric quality / article description|
| `color`         | str     | Shade / colour name or code         |

All fields may be `null` if not found. `flagged_fields` lists fields with confidence < 0.85.

---

## Performance Targets

| Scenario                         | Target     |
|----------------------------------|------------|
| 10-page digital PDF (full AI)    | < 8 sec    |
| Known supplier (template cache)  | < 2 sec    |
| Gemini call timeout              | 10 sec     |

---

## Project Structure

```
backend/
├── main.py                  FastAPI app, all routes
├── models.py                Pydantic models
├── config.py                Config, env vars, logging setup
├── session_store.py         In-memory session dict
├── extractor/
│   ├── pdf_parser.py        pdfplumber + parallel page processing
│   ├── ocr_fallback.py      Tesseract OCR for scanned pages
│   ├── regex_rules.py       Fast regex (runs before Gemini)
│   ├── chunker.py           Large-doc chunker + doc_type classifier
│   └── gemini_agent.py      Single batched Gemini call
├── mapper/
│   ├── canonical_mapper.py  Merge all sources → 9-field record
│   ├── confidence_scorer.py Per-field confidence scoring
│   ├── conflict_resolver.py Highest-confidence-wins deduplication
│   └── synonym_dict.yaml    Column alias → canonical field mapping
├── memory/
│   └── template_store.py    ChromaDB supplier template CRUD
├── validator/
│   ├── schema_validator.py  Pydantic + business rule checks
│   └── numeric_checker.py   Weight row-sum cross-check
├── output/
│   └── excel_writer.py      openpyxl .xlsx generation
├── logs/
│   ├── errors.log           All ERROR-level events
│   └── gemini_usage.log     Gemini call log with token counts
├── db/chroma/               ChromaDB persistent store (auto-created)
├── output/excel/            Generated .xlsx files (auto-created)
├── requirements.txt
└── .env.example
```

---

## Logs

| File                    | Contents                                       |
|------------------------|------------------------------------------------|
| `logs/errors.log`      | All exceptions with filename + stack trace     |
| `logs/gemini_usage.log`| Every Gemini call: supplier, elapsed, tokens   |
