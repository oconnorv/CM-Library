"""DigitalNC connector (North Carolina Digital Heritage Center).

Non-newspaper content lives on a TIND/Invenio instance at lib.digitalnc.org,
which supports the classic Invenio search interface with machine-readable
output formats. We request `of=recjson` (JSON records) and parse defensively,
since TIND recjson field shapes vary by instance configuration.

Endpoint behavior verified live 2026-07-30: recjson is a JSON array; zero-hit
searches return an empty body; phrase queries tolerate dropped apostrophes
("walshs" matches "Walsh's") but fail on any extra token. Their Open-ONI
newspaper site is a separate system and out of scope for v1.
"""

from __future__ import annotations

from ..normalize import extract_year, main_title, normalize_author, normalize_title, trim_dangling
from ..records import LocalRecord
from . import Candidate, Source

SEARCH_URL = "https://lib.digitalnc.org/search"
RECORD_URL = "https://lib.digitalnc.org/record/{recid}"
_MAX_QUERY_WORDS = 10


def _first_string(value) -> str:
    """recjson fields may be a string, a dict with a same-named key, or a list
    whose useful element isn't necessarily first (imprint = [{publisher_name},
    {date}]), so lists are scanned for the first element that yields text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, list):
        for element in value:
            text = _first_string(element)
            if text:
                return text
        return ""
    if isinstance(value, dict):
        for key in ("title", "full_name", "name", "date", "value", "a"):
            if key in value:
                text = _first_string(value[key])
                if text:
                    return text
    return ""


class DigitalNCSource(Source):
    name = "digitalnc"

    def _queries(self, record: LocalRecord) -> list[str]:
        """Query attempts, most precise first; the first with any hit wins.
        Same widening strategy as the Internet Archive connector: drop the
        author, then shorten to the pre-subtitle main title, only on zero hits.
        """
        full = trim_dangling(" ".join(normalize_title(record.title).split()[:_MAX_QUERY_WORDS]))
        main = trim_dangling(main_title(record.title))
        author = normalize_author(record.author)

        attempts = []
        for title in (full, main):
            if not title:
                continue
            query = f'title:"{title}"'
            if author:
                attempts.append(f'{query} author:"{author}"')
            attempts.append(query)
        return list(dict.fromkeys(attempts))

    def search(self, record: LocalRecord, verified_oclc: str | None = None) -> list[Candidate]:
        for query in self._queries(record):
            candidates = self._run_query(query)
            if candidates:
                return candidates
        return []

    def _run_query(self, query: str) -> list[Candidate]:
        response = self.session.get(
            SEARCH_URL,
            params={"p": query, "of": "recjson", "rg": 10},
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        if response.status_code != 200:
            # Observed live: TIND answers 202 with an empty body when it does
            # not recognize the User-Agent. Zeroes from a soft-block must not
            # be mistaken for genuine no-match results.
            raise RuntimeError(
                f"DigitalNC answered HTTP {response.status_code} instead of results — "
                "likely bot filtering of this User-Agent. See README 'Verifying DigitalNC'."
            )
        # Zero-hit searches return a completely empty body (observed live), not []
        if not response.text.strip():
            return []
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
