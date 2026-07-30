"""CSV output for the human review queue."""

from __future__ import annotations

import csv
from pathlib import Path

from .records import LocalRecord
from .sources import Candidate

COLUMNS = [
    "local_id",
    "local_title",
    "local_author",
    "local_year",
    "material_type",
    "call_numbers",
    "source",
    "match_title",
    "match_author",
    "match_year",
    "match_url",
    "match_identifier",
    "rights_or_access",
    "score",
    "matched_via",
    "review_status",  # left blank for reviewers: e.g. accepted / rejected / unsure
]


class ReviewCsv:
    def __init__(self, path: str | Path, append: bool = False):
        path = Path(path)
        exists = path.exists() and path.stat().st_size > 0
        self._fh = open(path, "a" if append else "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._fh, fieldnames=COLUMNS)
        if not (append and exists):
            self._writer.writeheader()

    def write_candidate(self, record: LocalRecord, call_numbers: str, candidate: Candidate, score: float) -> None:
        self._writer.writerow(
            {
                "local_id": record.record_id,
                "local_title": record.title,
                "local_author": record.author,
                "local_year": record.year,
                "material_type": record.material_type,
                "call_numbers": call_numbers,
                "source": candidate.source,
                "match_title": candidate.title,
                "match_author": candidate.author,
                "match_year": candidate.year,
                "match_url": candidate.url,
                "match_identifier": candidate.identifier,
                "rights_or_access": candidate.rights,
                "score": score,
                "matched_via": candidate.matched_via,
                "review_status": "",
            }
        )
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()
