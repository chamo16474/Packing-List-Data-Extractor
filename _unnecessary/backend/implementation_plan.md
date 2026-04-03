# Feature Implementation Plan: Line-Item Detailed Excel Export

Currently, the backend extracts document-level summary values (total pieces, total weight) into a single canonical `PackingListRecord` and exports exactly one row per packing list into the generated Excel file. 

You have requested to change the output layout so that the Excel report contains a row for **each individual piece/roll**, including its specific lot, piece number, length, weight, and color, along with the document-level attributes (PO, Invoice, etc).

## User Review Required
> [!IMPORTANT]
> Because the React UI is strictly built to review exactly 10 canonical summary fields rather than a grid of 500 individual line items, **performing a full-stack rewrite to support editing hundreds of line items in the web UI would be massive overhead**. 
> 
> My proposed plan below achieves your exact goal in the **Excel Output** entirely through backend enhancements, without breaking the existing Frontend UI. Please review.

## Proposed Changes

We will use a "Hidden Detail Extraction" approach. The AI will extract the 10 summary fields for the UI to display, but will *also* extract the granular line items which remain invisible to the UI but are directly written to the resulting Excel document. 

### 1. `backend/models.py`
We will extend the core model to hold the line-item data without disrupting the existing canonical schema expected by the frontend.
#### [MODIFY] models.py
- Define a new `PackingLineItem` structure mapping: `lot`, `piece_number`, `meters`, `weight`, `color`, `quality`.
- Add `line_items: list[PackingLineItem] = []` to the main `PackingListRecord`.

### 2. `backend/extractor/gemini_agent.py`
We must update the AI instruction prompt to instruct Gemini to extract a full list of rolls/pieces. 
#### [MODIFY] gemini_agent.py
- Update `EXTRACTION_PROMPT` to add a new top-level `line_items` array in the JSON schema.
- Specifically instruct the model to gather the detailed roll properties (length, weight, color) for *every* piece identified in the document, while still providing the 10 grouped summary values.
- Re-run token budget testing to ensure huge packing lists aren't truncated by output limits. 

### 3. `backend/mapper/canonical_mapper.py`
Ensure the newly extracted line items are safely attached to the memory session.
#### [MODIFY] canonical_mapper.py
- Pass the `line_items` array from the `gemini_results` directly into the mapped `PackingListRecord`.

### 4. `backend/output/excel_writer.py`
Completely overhaul the Excel generation logic to support multi-line outputs per document rather than the flat single-line format.
#### [MODIFY] excel_writer.py
- Re-map the structural headers to definitively support: `PO Number`, `Invoice Number`, `Delivered Date`, `Order Number`, `Lot / Batch`, `Piece / Roll No`, `Meters`, `Net Weight (KG)`, `Quality`, `Color`.
- If a document has populated `line_items`, use a loop to insert a new row for *every piece in the array*. 
- **Inheritance Logic:** Inject the document-level constants (like PO Number, Invoice number) automatically into each row, combined with the piece-specific variables (like Meters, Weight).
- If `line_items` is empty (e.g. missing text or regex fallback), it will gracefully fall back to simply recording the 10 original canonical summary fields as a single row.

---

## Open Questions

> [!WARNING]
> **What happens if you manually correct a summary field in the UI?**
> E.g., The AI says Color is "NAVY, RED", but you manually edit the Color text-box to say "RED" before hitting Confirm. Should the final Excel file OVERRIDE the individual line-item colors and force them all to be "RED"? Or should it preserve the line-item colors originally found by the AI and ignore your UI edit for that field? 
> *My default assumption is: Edited UI fields will OVERRIDE line items.*

## Verification Plan

### Automated Tests
- I will run the `test_pipeline.py` script and examine the extracted JSON object to ensure `line_items` are accurately extracted. 
- Ensure no TypeErrors on missing weights.

### Manual Verification
- I will ask you to upload the `PACKING LIST.pdf` through your browser, proceed through the Review screen, and hit "Download Excel". 
- You should verify that the Excel document perfectly matches the new row-by-row itemized structure.
