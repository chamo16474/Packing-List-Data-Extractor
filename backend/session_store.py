"""
session_store.py — In-memory session store keyed by job_id.
No persistence between server restarts. No database needed.
"""

from __future__ import annotations
import threading
from typing import Optional
from models import PackingListRecord


class SessionStore:
    """Thread-safe in-process dict mapping job_id → PackingListRecord."""

    def __init__(self) -> None:
        self._store: dict[str, PackingListRecord] = {}
        self._lock = threading.Lock()

    def set(self, job_id: str, record: PackingListRecord) -> None:
        with self._lock:
            self._store[job_id] = record

    def get(self, job_id: str) -> Optional[PackingListRecord]:
        with self._lock:
            return self._store.get(job_id)

    def update_field(self, job_id: str, field_name: str, value: object) -> Optional[PackingListRecord]:
        """Mutate a single field on an existing record and return the updated record."""
        with self._lock:
            record = self._store.get(job_id)
            if record is None:
                return None
            # Pydantic v2: model_copy(update=...) returns a new validated instance
            updated = record.model_copy(update={field_name: value})
            self._store[job_id] = updated
            return updated

    def delete(self, job_id: str) -> bool:
        with self._lock:
            if job_id in self._store:
                del self._store[job_id]
                return True
            return False

    def all_job_ids(self) -> list[str]:
        with self._lock:
            return list(self._store.keys())


# Singleton instance — imported by main.py and all route handlers
store = SessionStore()
