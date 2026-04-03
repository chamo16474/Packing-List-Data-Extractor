"""quick_model_test.py — Clean model test with file output."""
import os, sys, json, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

headers = {"Authorization": "Bearer " + config.OPENROUTER_API_KEY, "Content-Type": "application/json"}
TINY_MSG = 'Return only this exact JSON with no explanation: {"rolls":[{"roll_no":"TEST001","length_mts":100.0,"weight_nett_kgs":50.0,"lot_no":"LOT1","po_number":"PO123","shade":"A","weight_gross_kgs":52.0}]}'

results = []

models_to_test = [
    "google/gemini-2.0-flash",
    "google/gemini-2.0-flash-001",
    "google/gemini-2.5-flash-preview",
    "google/gemini-2.5-pro-preview",
    "google/gemini-flash-1.5",
    "google/gemini-pro-1.5",
    "meta-llama/llama-3.3-70b-instruct",
    "anthropic/claude-3-haiku",
]

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
            content = resp.json()["choices"][0]["message"]["content"].strip()[:100]
            results.append(f"OK   {model}: {content}")
        else:
            try:
                err = resp.json().get("error", {})
                results.append(f"ERR  {model}: HTTP {resp.status_code} code={err.get('code','?')} msg={str(err.get('message',''))[:80]}")
            except Exception:
                results.append(f"ERR  {model}: HTTP {resp.status_code} raw={resp.text[:100]}")
    except Exception as e:
        results.append(f"EXC  {model}: {e}")

# Write to file for clean reading
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model_test_results.txt")
with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(results) + "\n")

print("Results written to model_test_results.txt")
print("\n".join(results))
