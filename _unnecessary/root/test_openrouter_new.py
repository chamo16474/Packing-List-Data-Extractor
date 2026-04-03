import os
import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent / "backend"))

import config
from extractor.openrouter_agent import call_openrouter

def test_openrouter():
    print(f"Testing OpenRouter with model: {config.OPENROUTER_MODEL}")
    print(f"API Key present: {bool(config.OPENROUTER_API_KEY)}")
    
    test_text = "INVOICE NO: INV-12345\nDATE: 2024-01-01\nLOT: A123\nQUALITY: 100% COTTON\nCOLOR: RED\nROLL 1: 100 MTR"
    
    results = call_openrouter(test_text, "roll_level", "Test Supplier")
    
    if results:
        print("Success! Extracted fields:")
        for k, v in results.items():
            if k != "line_items":
                print(f"  {k}: {v}")
            else:
                print(f"  line_items: {len(v)} items")
    else:
        print("Failed to get results from OpenRouter.")

if __name__ == "__main__":
    test_openrouter()
