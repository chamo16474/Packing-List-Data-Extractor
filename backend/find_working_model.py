"""find_working_model.py — Find which models actually work and test tiny call."""
import os, sys, json, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

headers = {"Authorization": "Bearer " + config.OPENROUTER_API_KEY, "Content-Type": "application/json"}

print("=== Available Gemini models on OpenRouter ===")
r = requests.get(config.OPENROUTER_BASE_URL + "/models", headers=headers, timeout=15)
gemini_models = []
if r.status_code == 200:
    for m in r.json().get("data", []):
        mid = m.get("id", "")
        if "gemini" in mid.lower() or "google" in mid.lower():
            ctx = m.get("context_length", "?")
            top_p = m.get("top_provider", {})
            max_out = top_p.get("max_completion_tokens", "?")
            print(f"  {mid:<55} ctx={ctx}  max_out={max_out}")
            gemini_models.append((mid, max_out))

print()

# Test models with a tiny payload
TINY_MSG = 'Return only this exact JSON: {"rolls": [{"roll_no": "TEST001", "length_mts": 100.0, "weight_nett_kgs": 50.0}]}'

models_to_test = [
    "google/gemini-2.0-flash",
    "google/gemini-2.0-flash-001",
    "google/gemini-2.5-flash-preview",
    "google/gemini-2.5-pro-preview",
    "google/gemini-flash-1.5",
    "google/gemini-pro-1.5",
]

print("=== Testing models with tiny payload (max_tokens=8192) ===")
working = []
for model in models_to_test:
    payload = {
        "model": model,
        "temperature": 0.0,
        "max_tokens": 8192,
        "messages": [{"role": "user", "content": TINY_MSG}],
    }
    try:
        resp = requests.post(
            config.OPENROUTER_BASE_URL + "/chat/completions",
            headers=headers, json=payload, timeout=30
        )
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            print(f"  ✅ {model:<45} OK — response: {content[:80]}")
            working.append(model)
        else:
            try:
                err = resp.json()
                code = err.get("error", {}).get("code", "?")
                msg  = err.get("error", {}).get("message", resp.text[:100])
            except Exception:
                code, msg = "?", resp.text[:100]
            print(f"  ❌ {model:<45} {resp.status_code} code={code}: {msg[:80]}")
    except Exception as e:
        print(f"  ⚠️  {model:<45} Exception: {e}")

print()
if working:
    print(f"✅ Working models: {working}")
    print(f"\nRecommended PRIMARY model: {working[0]}")
else:
    print("❌ No models worked! Check API key and OpenRouter account.")
