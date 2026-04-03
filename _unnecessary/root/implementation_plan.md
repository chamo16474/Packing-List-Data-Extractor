# Packing List Frontend Implementation

This implementation plan outlines the development of the frontend React application for the Packing List Extraction & Summarization System, strictly following the `AGENT_2_GEMINI_FRONTEND.md` instructions while marrying them with the `@frontend-design` and `@typescript-expert` principles.

## Proposed Design Direction (DFII Strategy)
Following the `@frontend-design` directives, we will implement an **Industrial / Utilitarian** aesthetic. This makes perfect sense for a high-accuracy, data-dense Review Portal where human reviewers cannot afford mistakes.

*   **Aesthetic Name:** Industrial Utilitarian Data-Entry
*   **Design Anchor:** A rigid, dense, grid-based layout with mono-spaced numbers and high-contrast status pills (Red/Amber/Green) starkly separating data from controls. Missing decorative fluff.
*   **Color System:**
    *   Background: `#ffffff` (White, absolute blank canvas)
    *   Primary Action: `#2563eb` (Utility Blue)
    *   Status Tokens: `#16a34a` (Auto), `#d97706` (Review), `#dc2626` (Flag)
    *   Structure: `#e5e7eb` (Sharp 1px borders everywhere)
*   **Typography:** Strict separation of context (system-ui, sans-serif) and data values (monospaced for numbers to easily verify POs, pieces, quantities).

## User Review Required

> [!WARNING]
> **Conflict in Instructions regarding TypeScript**
> The design spec `AGENT_2_GEMINI_FRONTEND.md` explicitly states: **"No TypeScript — plain JavaScript only"** and **"Do not add TypeScript"**.
> However, your prompt asks me to use the `@typescript-expert` skill, which mandates a TypeScript-first approach. 
> 
> My recommendation: Given the request for `@typescript-expert` and the focus on "ACCURACY", TypeScript is highly recommended for building resilient API integrations and forms. **Please confirm if you want me to ignore the 'No TypeScript' rule and use TypeScript (React-TS), or stick to plain JavaScript.**

> [!IMPORTANT]
> **Aesthetic Commitment**
> By utilizing `@frontend-design`, the app will NOT look like a default template. It will feel more like a Bloomberg Terminal or serious factory management software: high-density, no gradients, sharp borders, focused entirely on the data and the task at hand. Please confirm this aligns with your expectations.

## Proposed Changes

### Frontend Infrastructure

#### [NEW] `frontend/` (Project Root)
- Initialize using `npx -y create-vite@latest frontend --template react-ts` (assuming TypeScript is approved based on the skill, or `react` if plain JS).
- Clean up all default assets and styles.

---
### Frontend Components (React)

#### [NEW] `frontend/src/App.tsx`
- Implement basic state-driven router between the three steps: `UploadScreen`, `MappingReview`, `OutputScreen`.

#### [NEW] `frontend/src/api.ts`
- Centralized fetch calls mapping strictly to the backend FastAPI endpoints (`/upload`, `/result/{jobId}`, `/mapping/candidates/{jobId}/{fieldName}`, `/mapping/confirm`, `/output/excel/{jobId}`).

#### [NEW] `frontend/src/components/UploadScreen.tsx`
- Drag-and-drop zone using standard HTML5 Drag/Drop APIs.
- Optional Supplier Name field.
- Loading spinner indicating synchronous backend processing.

#### [NEW] `frontend/src/components/MappingReview.tsx`
- The core data grid displaying the 9 canonical fields.
- Tracks completeness state: disables submit until all flags (Red) are resolved.
- Integrates keyboard navigation (Enter, R, N).
- Connects tightly to the `DocumentPreview` panel to synchronize highlights on row focus.

#### [NEW] `frontend/src/components/FieldRow.tsx`
- Individual row for a canonical field.
- Handles inline editing and focus states.
- Status UI and `ReassignDropdown` action hook.

#### [NEW] `frontend/src/components/DocumentPreview.tsx`
- Scrolly-telling style text viewer.
- Receives focus coordinates/text-ranges from the active `FieldRow` to highlight source text.

#### [NEW] `frontend/src/components/OutputScreen.tsx`
- Summary data table.
- Single CTA for downloading the `.xlsx` Excel file.

---
### Styles (CSS Modules)

#### [NEW] `frontend/src/styles/App.module.css` (and related module files)
- Implementation of the Industrial Utilitarian design rules.
- Only standard CSS, strictly adhering to the "No Tailwind, no UI library" constraint.

## Open Questions

1.  **TypeScript vs JavaScript**: As highlighted above, shall I use TypeScript (per the `@typescript-expert` skill) or plain JS (per `AGENT_2_GEMINI_FRONTEND.md`)?
2.  **API Port**: The document states the backend runs at `http://localhost:8000`. Are there any CORS headers that need to be accounted for, or is `fetch` straight to `8000` sufficient as is from your backend setup?

## Verification Plan

### Manual Verification
- Execute `npm install` and `npm run dev` to serve the frontend.
- Launch the provided backend (`uvicorn main:app --port 8000`).
- Test the full end-to-end flow:
  1. Uploading a dummy PDF (with intentional missing fields to trigger Amber/Red confidence flags).
  2. Test keyboard shortcuts (Enter to confirm, 'N' for N/A, 'R' to reassign) in the Review Portal.
  3. Verify that the Submit button blocks action until all Red flags are resolved.
  4. Verify Excel download fires accurately at the end.
