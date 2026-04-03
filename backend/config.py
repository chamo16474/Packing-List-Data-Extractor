"""
config.py — Central configuration for the Packing List Extraction Backend.
All env vars are loaded from .env via python-dotenv at startup.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
LOGS_DIR = BASE_DIR / "logs"
CHROMA_PERSIST_DIR = str(BASE_DIR / "db" / "chroma")
EXCEL_OUTPUT_DIR = str(BASE_DIR / "output" / "excel")

# Ensure directories exist at import time
LOGS_DIR.mkdir(parents=True, exist_ok=True)
Path(CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
Path(EXCEL_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# OpenRouter settings (PRIMARY AI PROVIDER)
# ---------------------------------------------------------------------------
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
# OPENROUTER_MODEL is kept for .env backward-compatibility only.
# Actual model selection (primary = gemini-2.0-flash, fallback = gemini-2.5-pro)
# is now managed in extractor/openrouter_agent.py (Flaw H + I fix).
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash")
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
OPENROUTER_MAX_TOKENS: int = 8192          # gemini-2.0-flash hard limit (max_output=8192)
OPENROUTER_TEMPERATURE: float = 0.0        # Must be 0 for deterministic extraction
OPENROUTER_TIMEOUT_SECONDS: int = 120      # SFM 11-page docs need the full window
OPENROUTER_REQUESTS_PER_MINUTE: int = 60
OPENROUTER_REQUESTS_PER_DAY: int = 10_000

# ---------------------------------------------------------------------------
# Extraction thresholds
# ---------------------------------------------------------------------------
CONFIDENCE_THRESHOLD: float = 0.85      # below this → flagged for human review
MAX_DOCUMENT_CHARS: int = 2_000_000     # max chars sent to AI per call (increased to avoid truncation)
MAX_PDF_WORKERS: int = 4                # ThreadPoolExecutor workers for PDF pages

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

def _configure_logging() -> None:
    """Configure root logger + two file handlers (errors + gemini usage)."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(ch)

    # Error log
    err_handler = logging.FileHandler(LOGS_DIR / "errors.log", encoding="utf-8")
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(err_handler)


_configure_logging()
# test comment