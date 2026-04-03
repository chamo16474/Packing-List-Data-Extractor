"""
tests/test_endpoints.py
Run with:  python tests/test_endpoints.py
Requires:  server running on localhost:8000  AND  reportlab installed
"""
import io
import sys
import httpx

BASE = "http://localhost:8080"


def make_test_pdf() -> bytes:
    """Create a minimal digital PDF with recognisable packing list fields."""
    try:
        from reportlab.pdfgen import canvas as PdfCanvas  # type: ignore
        buf = io.BytesIO()
        c = PdfCanvas.Canvas(buf)
        c.setFont("Helvetica", 10)
        lines = [
            "Packing List",
            "PO No: PO-2024-TEST-001",
            "Invoice No: INV-20240115",
            "Net Weight: 850.5",
            "Order No: ORD-9988",
            "Date: 15/01/2024",
            "Quality: 100pct Cotton Combed 40/40",
            "Shade: Navy Blue",
        ]
        y = 750
        for line in lines:
            c.drawString(50, y, line)
            y -= 20
        c.save()
        return buf.getvalue()
    except ImportError:
        # reportlab not installed — use a pre-made minimal PDF (1-page blank)
        # This minimal PDF was hand-crafted; pdfplumber will extract no text
        # so the regex path produces null results — still tests the pipeline flow.
        return (
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
            b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
            b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 50 750 Td"
            b" (Packing List PO-2024-TST) Tj ET\nendstream\nendobj\n"
            b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
            b"xref\n0 6\n"
            b"0000000000 65535 f \n"
            b"0000000009 00000 n \n"
            b"0000000058 00000 n \n"
            b"0000000115 00000 n \n"
            b"0000000274 00000 n \n"
            b"0000000370 00000 n \n"
            b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n450\n%%EOF"
        )


PASS = 0
FAIL = 0


def check(label: str, cond: bool, extra: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {label}" + (f"  {extra}" if extra else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {label}" + (f"  {extra}" if extra else ""))


def main():
    global PASS, FAIL
    print("=" * 56)
    print("  Packing List Backend — Endpoint Integration Tests")
    print("=" * 56)

    # ── 1. Health ────────────────────────────────────────────────────
    print("\n[1] GET /health")
    r = httpx.get(f"{BASE}/health", timeout=5)
    check("Status 200", r.status_code == 200, str(r.json()))

    # ── 2. Suppliers (empty) ─────────────────────────────────────────
    print("\n[2] GET /suppliers")
    r = httpx.get(f"{BASE}/suppliers", timeout=5)
    check("Status 200", r.status_code == 200)
    check("Returns list", isinstance(r.json().get("suppliers"), list))

    # ── 3. Upload PDF ─────────────────────────────────────────────────
    print("\n[3] POST /upload")
    pdf_bytes = make_test_pdf()
    r = httpx.post(
        f"{BASE}/upload",
        files={"file": ("test_packing_list.pdf", pdf_bytes, "application/pdf")},
        data={"supplier_name": "Test Supplier"},
        timeout=30,
    )
    check("Status 200", r.status_code == 200, f"({r.status_code})")
    if r.status_code != 200:
        print("    Response:", r.text[:400])
        print("\nAborting remaining tests — upload failed.")
        _summary()
        return

    data = r.json()
    job_id = data.get("job_id", "")
    result = data.get("result", {})

    check("job_id returned", bool(job_id), job_id[:8] if job_id else "MISSING")
    check("status == done", data.get("status") == "done")
    check("9 canonical fields present", all(
        k in result for k in [
            "lot", "pieces", "meters", "po_number", "net_weight",
            "order_number", "invoice_number", "delivered_date", "quality", "color",
        ]
    ))
    check("extraction_confidence is dict", isinstance(result.get("extraction_confidence"), dict))
    check("flagged_fields is list", isinstance(result.get("flagged_fields"), list))
    print(f"    mapping_source  : {result.get('mapping_source')}")
    print(f"    doc_type        : {result.get('doc_type')}")
    print(f"    po_number       : {result.get('po_number')}")
    print(f"    net_weight      : {result.get('net_weight')}")
    print(f"    delivered_date  : {result.get('delivered_date')}")
    print(f"    color           : {result.get('color')}")
    print(f"    flagged_fields  : {result.get('flagged_fields')}")

    # ── 4. Get result ────────────────────────────────────────────────
    print("\n[4] GET /result/{job_id}")
    r = httpx.get(f"{BASE}/result/{job_id}", timeout=5)
    check("Status 200", r.status_code == 200)
    check("supplier_name matches", r.json().get("supplier_name") == "Test Supplier")

    # ── 5. Candidates ────────────────────────────────────────────────
    print("\n[5] GET /mapping/candidates/{job_id}/color")
    r = httpx.get(f"{BASE}/mapping/candidates/{job_id}/color", timeout=5)
    check("Status 200", r.status_code == 200)
    body = r.json()
    check("field_name == color", body.get("field_name") == "color")
    check("candidates is list", isinstance(body.get("candidates"), list))
    print(f"    candidates: {body.get('candidates')}")

    # ── 6. Confirm / reassign ────────────────────────────────────────
    print("\n[6] POST /mapping/confirm  (reassign color)")
    r = httpx.post(f"{BASE}/mapping/confirm", json={
        "job_id": job_id,
        "field_name": "color",
        "confirmed_value": "Royal Blue",
        "action": "reassign",
    }, timeout=5)
    check("Status 200", r.status_code == 200)
    check("updated_value == Royal Blue", r.json().get("updated_value") == "Royal Blue")

    print("\n[7] POST /mapping/confirm  (mark lot not_present)")
    r = httpx.post(f"{BASE}/mapping/confirm", json={
        "job_id": job_id,
        "field_name": "lot",
        "confirmed_value": None,
        "action": "not_present",
    }, timeout=5)
    check("Status 200", r.status_code == 200)
    check("updated_value is None", r.json().get("updated_value") is None)

    # ── 7. Excel download ────────────────────────────────────────────
    print("\n[8] POST /output/excel/{job_id}")
    r = httpx.post(f"{BASE}/output/excel/{job_id}", timeout=30)
    check("Status 200", r.status_code == 200)
    ct = r.headers.get("content-type", "")
    check("Content-Type is xlsx", "spreadsheetml" in ct, ct)
    check("File is non-empty", len(r.content) > 1000, f"{len(r.content)} bytes")
    cd = r.headers.get("content-disposition", "")
    check("Has filename header", "attachment" in cd, cd)
    print(f"    Downloaded: {len(r.content):,} bytes")

    # ── 8. 404 for unknown job ───────────────────────────────────────
    print("\n[9] GET /result/nonexistent  (expect 404)")
    r = httpx.get(f"{BASE}/result/nonexistent-uuid", timeout=5)
    check("Status 404", r.status_code == 404)

    # ── 9. Invalid field name ────────────────────────────────────────
    print("\n[10] POST /mapping/confirm  (invalid field — expect 400)")
    r = httpx.post(f"{BASE}/mapping/confirm", json={
        "job_id": job_id,
        "field_name": "nonexistent_field",
        "confirmed_value": "x",
        "action": "confirm",
    }, timeout=5)
    check("Status 400", r.status_code == 400)

    _summary()


def _summary():
    total = PASS + FAIL
    print()
    print("=" * 56)
    print(f"  Results: {PASS}/{total} passed  |  {FAIL} failed")
    print("=" * 56)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
