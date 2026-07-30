"""Resumable progress tracking so multi-day runs survive interruption.

A SQLite file next to the output CSV records which local record ids have been
fully processed; --resume skips them and appends new rows to the same CSV.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


class Checkpoint:
    def __init__(self, path: str | Path):
        self.conn = sqlite3.connect(str(path))
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS processed (record_id TEXT PRIMARY KEY, processed_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        self.conn.commit()

    def is_processed(self, record_id: str) -> bool:
        row = self.conn.execute("SELECT 1 FROM processed WHERE record_id = ?", (record_id,)).fetchone()
        return row is not None

    def mark_processed(self, record_id: str) -> None:
        self.conn.execute("INSERT OR IGNORE INTO processed (record_id) VALUES (?)", (record_id,))
        self.conn.commit()

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM processed").fetchone()[0]

    def close(self) -> None:
        self.conn.close()
