"""DigitalNC connector (North Carolina Digital Heritage Center).

Non-newspaper content lives on a TIND/Invenio instance at lib.digitalnc.org,
which supports the classic Invenio search interface with machine-readable
output formats. We request `of=recjson` (JSON records) and parse defensively,
since TIND recjson field shapes vary by instance configuration.

NOTE: this endpoint could not be probed from the development environment
(network policy); the first pilot run should verify it — see README. Their
Open-ONI newspaper site is a separate system and out of scope for v1.
"""

from __future__ import annotations

from ..normalize import extract_year, normalize_author, normalize_title
from ..records import LocalRecord
from . import Candidate, Source

SEARCH_URL = "https://lib.digitalnc.org/search"
RECORD_URL = "https://lib.digitalnc.org/record/{recid}"
_MAX_QUERY_WORDS = 10


def _first_string(value) -> str:
    """recjson fields may be a string, a dict with a same-named key, or a list."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return _first_string(value[0]) if value else ""
    if isinstance(value, dict):
        for key in ("title", "full_name", "name", "date", "value", "a"):
            if key in value:
                return _first_string(value[key])
    return ""


class DigitalNCSource(Source):
    name = "digitalnc"

    def search(self, record: LocalRecord, verified_oclc: str | None = None) -> list[Candidate]:
        title = normalize_title(record.title)
        if not title:
            return []
        query = f'title:"{" ".join(title.split()[:_MAX_QUERY_WORDS])}"'
        author = normalize_author(record.author)
        if author:
            query += f' author:"{author}"'

        response = self.session.get(
            SEARCH_URL,
            params={"p": query, "of": "recjson", "rg": 10},
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        try:
            results = response.json()
        except ValueError as exc:
            raise RuntimeError(
                "DigitalNC returned non-JSON for of=recjson — the TIND endpoint may have "
                "changed. Re-run without the digitalnc source, or update digitalnc.py "
                "(see README 'Verifying DigitalNC')."
            ) from exc
        if not isinstance(results, list):
            results = results.get("records", []) if isinstance(results, dict) else []

        candidates = []
        for rec in results:
            if not isinstance(rec, dict):
                continue
            recid = str(rec.get("recid") or rec.get("id") or "")
            rec_title = _first_string(rec.get("title"))
            authors = rec.get("authors") or rec.get("author") or rec.get("corporate_name")
            rec_author = _first_string(authors)
            imprint = rec.get("imprint") or rec.get("publication_info")
            year = extract_year(_first_string(imprint) or str(imprint or ""))
            if not recid or not rec_title:
                continue
            candidates.append(
                Candidate(
                    source=self.name,
                    title=rec_title,
                    author=rec_author,
                    year=year,
                    url=RECORD_URL.format(recid=recid),
                    identifier=recid,
                    rights="Open access (DigitalNC)",
                )
            )
        return candidates
