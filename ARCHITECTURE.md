# Software Architecture: Packing List Extraction & Summarization

This document describes the current software architecture, end-to-end processes, and the libraries, software, and AI elements involved in the Packing List Extraction system.

---

## 1. System Overview
The system is designed to automate the extraction of data from textile/apparel packing lists (PDF format) and summarize them into a canonical 10-field schema. It supports both digital PDFs and scanned documents through a multi-stage extraction pipeline combining regex, table column scanning, and Large Language Models (LLMs) via OpenRouter.

---

## 2. Technology Stack

### Frontend
- **Framework**: React.js (via Vite)
- **Language**: TypeScript
- **Styling**: Vanilla CSS / Tailwind CSS (Optional)
- **Build Tool**: Vite

### Backend
- **Framework**: FastAPI (Python 3.12+)
- **Server**: Uvicorn
- **Validation**: Pydantic v2
- **Concurrency**: Python Asyncio & Threading

### AI & Data Extraction
- **AI Gateway**: OpenRouter API
- **AI Models**: 
    - **Primary**: `google/gemini-2.0-flash-001` (Full Flash)
    - **Fallback**: `meta-llama/llama-3.3-70b-instruct`
- **OCR Engine**: Tesseract OCR (via `ocr_fallback.py`)
- **PDF Processing**: `pdfplumber`, `pdf2image` (Poppler)

### Storage & Persistence
- **Vector Database**: ChromaDB (Supplier pattern & template caching)
- **Session Store**: In-memory (Python dictionary-based)
- **Output**: Multi-sheet Excel (.xlsx) via `openpyxl`

---

## 3. Extraction Pipeline (Process Flow)

The extraction process follows a robust pipeline designed for high accuracy and scalability:

1.  **PDF Ingestion**: PDF is uploaded; `pdfplumber` attempts to extract raw text and structural metadata.
2.  **OCR Fallback**: If no selectable text is found, `ocr_fallback.py` uses `pdf2image` and `Tesseract` to generate text.
3.  **Classification**: `chunker.py` determines document layout (Roll-level vs. Lot-level) to adjust extraction prompts.
4.  **Regex Fast-Pass**: Static fields (PO, Invoice, Date) are extracted using `regex_rules.py`.
5.  **Chunking & Context Injection**: Large documents are split into ~3000 character chunks. The first 1000 characters (header context) are prepended to continuation chunks to ensure the AI maintains column alignment and semantic understanding.
6.  **Dynamic Skill Loading**: The system loads `PACKING_LIST_SKILL.md` as the authoritative AI system prompt, ensuring the AI strictly follows the defined extraction schema.
7.  **AI Extraction (OpenRouter)**: Chunks are processed by Gemini 2.0 Flash (with Llama-3.3 fallback). Results are merged, ensuring every single roll row is captured.
8.  **Canonical Mapping**: `canonical_mapper.py` merges results from Regex, AI, and Table Scanning. It uses a `synonym_dict.yaml` to handle multi-lingual or varied column headers.
9.  **Numeric Validation**: `numeric_checker.py` cross-references extracted totals against the sum of individual line items.
10. **Excel Generation**: Validated data is exported to a professionally formatted Excel file with granular line-item sheets.

---

## 4. Library & Software Inventory

| Component | Library / Software | Role in Process |
| :--- | :--- | :--- |
| **API Layer** | `FastAPI` | Handles HTTP requests, file uploads, and job status polling. |
| **PDF Extraction** | `pdfplumber` | Primary tool for extracting text and tables from digital PDFs. |
| **OCR Image Prep** | `pdf2image` | Converts PDF pages to PIL images for OCR processing. |
| **OCR Engine** | `Tesseract OCR` | Performs optical character recognition on scanned images. |
| **AI Client** | `requests` | Communicates with the OpenRouter/Gemini API. |
| **Vector Store** | `ChromaDB` | Persists supplier templates to reduce AI latency and costs. |
| **Data Models** | `Pydantic` | Defines and validates the 10-field canonical schema. |
| **Excel Output** | `openpyxl` | Generates highly formatted Excel reports. |

---

## 5. AI Elements & Intelligence

### OpenRouter (AI Gateway)
- **Role**: Provides a unified interface to multiple LLMs.
- **Handling**: Manages rate limits (RPM/RPD), timeouts, and automatic failover between models.

### Google Gemini 2.0 Flash (Primary Model)
- **Role**: The "Decision Engine."
- **Capabilities**: 
    - **Large Context**: Processes long lists effectively using the chunking strategy.
    - **JSON Enforcement**: Strictly returns structured data according to the skill specification.
    - **Table Parsing**: Understands complex grid structures without explicit training.

### Fallback Mechanism
- If Gemini fails to return valid JSON, the system automatically retries with **Llama 3.3 70B**, ensuring zero-downtime extraction.

---

## 6. Data Schema (Canonical Record)

The system maps all extracted data to a standard 10-field header schema + granular line items:

### Header Fields
1. **Lot / Batch**
2. **Pieces / Rolls** (Total)
3. **Meters** (Total)
4. **PO Number**
5. **Net Weight**
6. **Order Number**
7. **Invoice Number**
8. **Delivered Date**
9. **Quality / Fabric**
10. **Color / Shade**

### Granular Line Items (Roll Level)
- `lot_no`, `po_number`, `piece_number`, `meters`, `length_yds`, `net_weight`, `color`, `quality`, `points_per_roll`, `points_per_100m2`, `weight_gross_kgs`.

