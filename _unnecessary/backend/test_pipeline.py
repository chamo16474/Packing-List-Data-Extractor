import logging
logging.disable(logging.CRITICAL)

from main import run_pipeline

with open(r'../sample packing list/PACKING LIST.pdf', 'rb') as f:
    pdf_bytes = f.read()

record = run_pipeline(pdf_bytes, 'PACKING LIST.pdf', 'unknown')
print('=== EXTRACTION RESULT ===')
print(f'lot: {record.lot}')
print(f'pieces: {record.pieces}')
print(f'meters: {record.meters}')
print(f'po_number: {record.po_number}')
print(f'net_weight: {record.net_weight}')
print("=== EXTRACTION RESULT ===")
for k, v in record.model_dump().items():
    if k not in ['extraction_confidence', 'raw_candidates', 'raw_text', 'line_items']:
        print(f"{k}: {v}")

print("\n=== LINE ITEMS ===")
if record.line_items:
    for i, item in enumerate(record.line_items):
        print(f"[{i+1}] {item.model_dump()}")
else:
    print("No line items found.")

print("\n=== CONFIDENCE ===")
for k, v in record.extraction_confidence.items():
    print(f"  {k}: {v:.2f}")

from output.excel_writer import generate_excel
import uuid
test_id = str(uuid.uuid4())
generate_excel(record, test_id)
print(f"\nExcel generated with ID: {test_id}")
