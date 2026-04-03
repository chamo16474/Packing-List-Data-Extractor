"""simple_api_test.py — Raw OpenRouter API test."""
import os, sys, json, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

print("API KEY (first 15):", config.OPENROUTER_API_KEY[:15] if config.OPENROUTER_API_KEY else "MISSING!")
print("MAX_TOKENS:", config.OPENROUTER_MAX_TOKENS)
print("MODEL: google/gemini-2.0-flash")

headers = {
    "Authorization": "Bearer " + config.OPENROUTER_API_KEY,
    "Content-Type": "application/json",
}

# Minimal test payload
payload = {
    "model": "google/gemini-2.0-flash",
    "temperature": 0.0,
    "max_tokens": 200,
    "messages": [
        {"role": "user", "content": 'Return ONLY JSON: {"rolls": [{"roll_no": "001", "length_mts": 100.0}]}'}
    ],
}

print("\nSending minimal test request...")
resp = requests.post(
    config.OPENROUTER_BASE_URL + "/chat/completions",
    headers=headers, json=payload, timeout=30
)
print("HTTP status:", resp.status_code)
print("Response:", resp.text[:800])

if resp.status_code == 200:
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    print("\nRaw content:", content)
elif resp.status_code == 400:
    print("\n400 BAD REQUEST — check error message above for cause")
    try:
        err = resp.json()
        print("Error detail:", json.dumps(err, indent=2))
    except Exception:
        pass
