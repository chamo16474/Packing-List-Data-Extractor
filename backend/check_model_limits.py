"""check_model_limits.py — Query OpenRouter for model token limits."""
import os, sys, json, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

headers = {"Authorization": "Bearer " + config.OPENROUTER_API_KEY}

# Get model info
print("Fetching model info from OpenRouter...")
resp = requests.get(
    config.OPENROUTER_BASE_URL + "/models",
    headers=headers, timeout=15
)
print("HTTP:", resp.status_code)
if resp.status_code == 200:
    models = resp.json().get("data", [])
    # Find gemini models
    for m in models:
        mid = m.get("id", "")
        if "gemini" in mid.lower():
            ctx = m.get("context_length", "?")
            top_p = m.get("top_provider", {})
            max_out = top_p.get("max_completion_tokens", "?")
            print(f"  {mid:<45} context={ctx}  max_output={max_out}")
else:
    print("Error:", resp.text[:300])
