import os
import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent / "backend"))

import config
from extractor.openrouter_agent import get_available_models

def list_free_models():
    print("Fetching available free models from OpenRouter...")
    models = get_available_models()
    if models:
        print(f"Found {len(models)} free models:")
        for m in models[:20]:  # Show first 20
            print(f"  - {m}")
    else:
        print("No free models found or API error.")

if __name__ == "__main__":
    list_free_models()
