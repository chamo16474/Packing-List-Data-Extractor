# Agent 2 — Gemini Pro (Frontend Engineer)

## Your environment
You are working inside **Google Antigravity IDE** (https://antigravity.google/) — Google's next-generation
AI-assisted development environment. Use Antigravity's built-in terminal and the Gemini Pro assistant
panel for all code generation and iteration. Run all `npm` commands in the Antigravity terminal.

## Your role
You are building the **complete React frontend** for a Packing List Extraction & Summarization System.
The backend (FastAPI, running at `http://localhost:8000`) is already built by a separate agent.
Your job is to build a fast, accurate, and easy-to-use review interface.

**Primary focus: ACCURACY and SPEED. The UI must make it impossible for a human reviewer to make
mistakes, and every interaction must feel instant.**

---

## Tech stack
- **Framework:** React 18 via Vite — bootstrap with `npm create vite@latest frontend -- --template react`
- **Styling:** plain CSS modules (one `.module.css` per component) — no Tailwind, no UI library
- **HTTP:** native `fetch` API only — no axios, no jQuery
- **State:** React `useState` + `useReducer` — no Redux, no external state library
- **No TypeScript** — plain JavaScript only, faster to write and costs fewer tokens
- Run locally with `npm run dev` inside Antigravity

**Why plain CSS + no UI library:** Minimum token usage, zero dependency conflicts, fastest iteration.

---

## Token budget discipline — CRITICAL
You are Gemini Pro. You are not generating AI completions at runtime — you are writing static frontend code.
- Write clean, minimal HTML/CSS/JS
- No inline comments longer than one line
- No placeholder lorem ipsum text
- No unused CSS classes
- No animations unless they serve a functional purpose (e.g. loading spinner)

---

## The 9 canonical fields (fixed — never change)
The backend always returns these 9 fields. Build your UI around exactly these:

| Field | Display label | Type |
|---|---|---|
| `lot` | LOT | text |
| `pieces` | Pieces | number |
| `meters` | Meters (m) | number |
| `po_number` | PO Number | text |
| `net_weight` | Net Weight (kg) | number |
| `order_number` | Order Number | text |
| `invoice_number` | Invoice Number | text |
| `delivered_date` | Delivered Date | date |
| `quality` | Quality / Article | text |
| `color` | Color / Shade | text |

---

## Application flow — implement exactly in this order

### Screen 1 — Upload
- Large drag-and-drop zone accepting PDF files
- Optional text input: "Supplier name (optional — helps accuracy)"
- Upload button → POST to `http://localhost:8000/upload`
- Show a progress spinner while processing (the backend is synchronous, response comes when done)
- On success → navigate to Screen 2 with the `job_id`
- On error → show inline error message in red, allow retry

### Screen 2 — Mapping Review Portal
This is the core screen. It must be designed for accuracy.

**Layout:**
```
┌─────────────────────────────────────────────────────────┐
│  [Supplier name]        [Source file]    [job_id badge] │
├────────────────┬────────────────────────────────────────┤
│                │  FIELD REVIEW TABLE                    │
│  DOCUMENT      │                                        │
│  PREVIEW       │  Field │ Extracted value │ Status      │
│  (raw text     │  ──────┼─────────────────┼──────────── │
│   from backend)│  LOT   │ 072168/002     │ [CONFIRM]   │
│                │  Pieces│ 59             │ [CONFIRM]   │
│                │  ...   │ ...            │ ...         │
│                │                                        │
│                │  [Submit all confirmed →]              │
└────────────────┴────────────────────────────────────────┘
```

**Field review table — each row has:**
1. Field label (from the canonical list above)
2. Extracted value (editable inline text input — pre-filled with what the AI found)
3. Confidence badge — color coded:
   - Green (≥ 85%): "AUTO" badge
   - Amber (60–84%): "REVIEW" badge  
   - Red (< 60%): "FLAG" badge
4. Three action buttons:
   - **CONFIRM** — accepts the current value as-is
   - **REASSIGN** — opens a small dropdown of top 5 candidate values fetched from `GET /mapping/candidates/{job_id}/{field_name}`. Selecting one sets the value and auto-confirms.
   - **N/A** — marks the field as not present in this document

**Important UX rules for accuracy:**
- Fields flagged red must be actioned before Submit is enabled
- Fields flagged amber are highlighted but Submit is not blocked
- Green fields are pre-confirmed — reviewer can still change them
- The inline value input is always editable regardless of confidence — human can type a correction
- When a field is confirmed, its row turns light green
- When N/A is selected, the row turns gray and the value input is disabled
- "Submit all confirmed" button is disabled until every red-flagged field has been actioned

**Document preview panel:**
- Shows the raw extracted text from the backend (returned in the `/result/{job_id}` response)
- When a reviewer clicks a field row → the preview panel scrolls to and highlights the relevant text passage (use the `page` and `source_text` metadata from the backend response)
- This is essential for accuracy — the reviewer can verify the value against the source

### Screen 3 — Output
After submitting the confirmed mapping:
- Show a clean summary table of all 9 fields with their final confirmed values
- **One download button only:**
  - **Download Excel (.xlsx)** → calls `POST /output/excel/{job_id}` → triggers file download
  - This is the ONLY output format. Do not add JSON or PDF download buttons.
- A "Process another file" button → resets to Screen 1
- A small "Supplier template saved" notice if this was a new supplier

---

## File structure to create (React + Vite)
```
frontend/
├── index.html              # Vite entry point (do not modify)
├── src/
│   ├── main.jsx            # React root mount
│   ├── App.jsx             # Router between the 3 screens
│   ├── api.js              # All fetch calls to backend (single file)
│   ├── components/
│   │   ├── UploadScreen.jsx         # Screen 1
│   │   ├── MappingReview.jsx        # Screen 2 — core review table
│   │   ├── FieldRow.jsx             # Single row in the review table
│   │   ├── DocumentPreview.jsx      # Left panel — raw text + highlight
│   │   ├── ConfidenceBadge.jsx      # GREEN/AMBER/RED pill
│   │   ├── ReassignDropdown.jsx     # Candidate list popup
│   │   └── OutputScreen.jsx         # Screen 3 — summary + download
│   └── styles/
│       ├── App.module.css
│       ├── UploadScreen.module.css
│       ├── MappingReview.module.css
│       └── OutputScreen.module.css
├── package.json
└── README.md               # how to run in Antigravity
```

---

## API calls to implement in src/api.js

```javascript
const API = "http://localhost:8000";

// Upload a PDF
async function uploadFile(file, supplierName) {
  const form = new FormData();
  form.append("file", file);
  if (supplierName) form.append("supplier_name", supplierName);
  const res = await fetch(`${API}/upload`, { method: "POST", body: form });
  return res.json(); // returns { job_id, ...fields, flagged_fields, mapping_source }
}

// Get full result
async function getResult(jobId) {
  const res = await fetch(`${API}/result/${jobId}`);
  return res.json();
}

// Get reassign candidates for a field
async function getCandidates(jobId, fieldName) {
  const res = await fetch(`${API}/mapping/candidates/${jobId}/${fieldName}`);
  return res.json(); // returns array of { value, confidence }
}

// Confirm / reassign / mark N/A
async function submitAction(jobId, fieldName, value, action) {
  const res = await fetch(`${API}/mapping/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId, field_name: fieldName, confirmed_value: value, action })
  });
  return res.json();
}

// Download Excel
async function downloadExcel(jobId) {
  const res = await fetch(`${API}/output/excel/${jobId}`, { method: "POST" });
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `packing_list_${jobId}.xlsx`;
  a.click();
}
```

---

## Visual design rules
- Background: white (`#ffffff`)
- Primary action color: `#2563eb` (blue)
- Confirm green: `#16a34a`
- Flag red: `#dc2626`
- Review amber: `#d97706`
- N/A gray: `#6b7280`
- Font: system-ui, -apple-system, sans-serif
- Table borders: 1px solid `#e5e7eb`
- Confidence badge: small pill, 11px font, rounded corners
- No gradients, no shadows, no animations except spinner
- Mobile-responsive is NOT required — desktop only, minimum 1280px wide

---

## Accuracy-critical UI rules — do not skip these
1. **Never auto-submit** — human must click CONFIRM or an action for every flagged field
2. **Show confidence number** alongside the badge (e.g. "AUTO 92%") — transparency builds trust
3. **Show `mapping_source`** per field as a tooltip: "Extracted by: AI / Regex / Template"
4. **Editable values:** clicking directly on a value cell enables inline editing — Tab moves to next field
5. **Keyboard shortcuts:** Enter = CONFIRM current field, N = mark N/A, R = open REASSIGN dropdown
6. **Dirty state warning:** if user tries to close the tab with unsubmitted changes, show browser confirm dialog

---

## Performance requirements
- Page load: under 1 second (no external dependencies to fetch)
- Upload → result display: determined by backend; show spinner, no timeout on frontend
- REASSIGN dropdown: must open in under 200ms (fetch candidates as soon as row is clicked, cache result)
- All screen transitions: instant — just toggle `display: none / block`, no CSS transitions

---

## Error states to handle
- Backend not reachable → show "Backend offline — make sure `uvicorn main:app` is running at port 8000"
- Upload fails → show filename + error message from backend JSON response
- Candidates fetch fails → show a manual text input in the REASSIGN dropdown instead
- Excel download fails → show "Download failed — try again" inline

---

## Deliverables
- Full `frontend/` directory with React + Vite project as described above
- `frontend/README.md` with: how to run (`npm install && npm run dev`) inside Antigravity,
  how to connect to backend, known limitations

**Do not add a login screen. Do not add dark mode. Do not add TypeScript.
Do not install any UI component library (no MUI, no shadcn, no Ant Design).**
