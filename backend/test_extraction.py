"""
test_extraction.py — Diagnose why line_items is always empty.

Run: python test_extraction.py  (from the backend/ directory)
"""
import sys, os, json, logging, textwrap

# Make sure cwd is backend/
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

logging.basicConfig(level=logging.DEBUG,
                    format="%(levelname)s | %(name)s | %(message)s")

# ── Minimal AML sample text (matches the worked example in PACKING_LIST_SKILL.md) ──
SAMPLE_TEXT = textwrap.dedent("""
    ARTISTIC MILLINERS (PVT) LTD
    INVOICE NO : AM2/EXP/35795/2026  DATED : 7-Jan-26
    TOTAL METERS: 11120  TOTAL ROLLS: 116
    TOTAL GROSS WT: 5288.00 KGS  TOTAL NET WT: 5143.00 KGS
    PRODUCT: 55% COTTON, 30% T400, 15% NYLON, DENIM FABRIC WIDTH 49\"/50\" INCH

    PO # 140928  AMS-1317-I DARK COBRA CT (R11419999)
    QUANTITY: 5,000 METERS AND 48 ROLLS

    LOT NO      PO #    Shade  Roll No    Length(mts)  Length(yds)  Points/Roll  Pts/100m2  Gross kgs  Nett kgs
    072168/002  140928  B      559988021  130.0        142.17       11           6.41       58.00      56.75
    "           140928  A      559988023  74.0         80.93        6            6.14       34.00      32.75
    "           140928  A      559988024  130.0        142.17       8            4.66       59.00      57.75
    "           140928  A      559988025  130.0        142.17       28           16.32      59.00      57.75
    "           140928  A      559988027  130.0        142.17       15           8.74       59.00      57.75
    TOTAL: 5 rolls  594.0 mts  ...

    PO # 140929  AMS-1317-II DARKER CT
    LOT NO      PO #    Shade  Roll No    Length(mts)  Length(yds)  Points/Roll  Pts/100m2  Gross kgs  Nett kgs
    072168/003  140929  C      560693001  120.0        131.23       3            1.91       54.00      52.75
    "           140929  C      560693002  120.0        131.23       3            1.91       53.00      51.75
    TOTAL: 2 rolls  240.0 mts  ...
""").strip()


print("\n" + "="*70)
print("STEP 1 — Calling OpenRouter AI directly")
print("="*70)

try:
    from extractor.openrouter_agent import call_openrouter, _load_skill, _call_model, _parse_json_response, _normalize_skill_response
    import config

    print(f"API KEY configured: {'YES' if config.OPENROUTER_API_KEY and config.OPENROUTER_API_KEY != 'your-openrouter-api-key-here' else 'NO — MISSING!'}")
    print(f"MAX_TOKENS: {config.OPENROUTER_MAX_TOKENS}")
    print(f"TIMEOUT: {config.OPENROUTER_TIMEOUT_SECONDS}s")

    skill = _load_skill()
    print(f"Skill file loaded: {len(skill)} chars\n")

    # ── Test raw API call with small sample ──
    print("Calling primary model (gemini-2.0-flash) with sample text...")
    system_prompt = skill
    user_message = (
        "Supplier hint: ARTISTIC MILLINERS\n"
        "Document layout type: roll_level\n\n"
        "Extract all data from this packing list.\n"
        "Return ONLY the JSON object described in the skill. No explanation.\n\n"
        f"DOCUMENT TEXT:\n{SAMPLE_TEXT}"
    )

    import requests, time
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "X-Title": "Packing List Extractor - TEST",
    }
    payload = {
        "model": "google/gemini-2.0-flash-001",
        "temperature": 0.0,
        "max_tokens": config.OPENROUTER_MAX_TOKENS,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
    }

    start = time.monotonic()
    try:
        resp = requests.post(
            f"{config.OPENROUTER_BASE_URL}/chat/completions",
            headers=headers, json=payload,
            timeout=config.OPENROUTER_TIMEOUT_SECONDS,
        )
    except Exception as e:
        print(f"❌ HTTP request FAILED: {e}")
        sys.exit(1)

    elapsed = time.monotonic() - start
    print(f"HTTP status: {resp.status_code}  ({elapsed:.1f}s)")

    if resp.status_code != 200:
        print(f"❌ API error body: {resp.text[:500]}")
        sys.exit(1)

    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        print("❌ No choices in response")
        print("Full response:", json.dumps(data, indent=2)[:1000])
        sys.exit(1)

    raw_text = choices[0]["message"]["content"]
    print(f"✅ Got response: {len(raw_text)} chars\n")
    print("--- First 800 chars of raw response ---")
    print(raw_text[:800])
    print("--- Last 300 chars ---")
    print(raw_text[-300:])
    print()

except Exception as e:
    import traceback
    print(f"❌ STEP 1 FAILED: {e}")
    traceback.print_exc()
    sys.exit(1)


print("\n" + "="*70)
print("STEP 2 — Parsing the JSON response")
print("="*70)

parsed = _parse_json_response(raw_text)
if parsed is None:
    print("❌ _parse_json_response returned None — JSON parsing FAILED")
    sys.exit(1)

rolls = parsed.get("rolls", [])
print(f"✅ JSON parsed OK — keys: {list(parsed.keys())}")
print(f"   rolls array length: {len(rolls)}")
if rolls:
    print(f"   First roll: {rolls[0]}")
    print(f"   Last roll:  {rolls[-1]}")
else:
    print("❌ 'rolls' array is EMPTY in AI response!")
    print("   Full parsed dict:", json.dumps(parsed, indent=2)[:1000])


print("\n" + "="*70)
print("STEP 3 — Normalizing to line_items")
print("="*70)

normalized = _normalize_skill_response(parsed)
line_items = normalized.get("line_items", [])
print(f"line_items count: {len(line_items)}")
if line_items:
    print(f"First item: {line_items[0]}")
    print(f"Last item:  {line_items[-1]}")
else:
    print("❌ line_items is EMPTY after normalization!")


print("\n" + "="*70)
print("STEP 4 — Full call_openrouter() wrapper")
print("="*70)

ai_results = call_openrouter(SAMPLE_TEXT, "roll_level", "ARTISTIC MILLINERS")
li_from_call = ai_results.get("line_items", [])
print(f"call_openrouter() line_items count: {len(li_from_call)}")
if li_from_call:
    print("✅ line_items populated correctly")
else:
    print("❌ line_items STILL empty from call_openrouter()")


print("\n" + "="*70)
print("STEP 5 — canonical_mapper test")
print("="*70)

from mapper.canonical_mapper import map_to_canonical
record = map_to_canonical(
    regex_results={},
    ai_results=ai_results,
    all_tables=[],
    doc_type="roll_level",
    supplier_name="ARTISTIC MILLINERS",
    source_file="test.pdf",
    full_text=SAMPLE_TEXT,
)
print(f"record.line_items count: {len(record.line_items)}")
if record.line_items:
    print(f"✅ SUCCESS — First item: {record.line_items[0]}")
else:
    print("❌ STILL EMPTY after canonical mapper")

print(f"\nrecord.pieces : {record.pieces}")
print(f"record.meters : {record.meters}")
print(f"record.lot    : {record.lot}")
print(f"record.color  : {record.color}")


print("\n" + "="*70)
print("STEP 6 — Excel output test")
print("="*70)

from output.excel_writer import generate_excel
xlsx = generate_excel(record, "test-job-001")
print(f"Excel generated: {len(xlsx)} bytes")
if record.line_items:
    print(f"✅ Excel should have {len(record.line_items)} data rows")
else:
    print("❌ Excel will have only 1 summary row (no line_items)")

print("\n✅ Test complete.\n")
