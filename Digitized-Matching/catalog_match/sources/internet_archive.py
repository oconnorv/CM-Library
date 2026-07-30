"""Internet Archive connector via the open advancedsearch.php JSON API (no key)."""

from __future__ import annotations

from ..normalize import main_title, normalize_author, normalize_title
from ..records import LocalRecord
from . import Candidate, Source

SEARCH_URL = "https://archive.org/advancedsearch.php"
# A phrase query has to match the indexed title word-for-word from the start, so
# a long local title with a subtitle the repository spells differently matches
# nothing. Queries therefore run narrowest-first and widen only on zero results.
_MAX_QUERY_WORDS = 10


def _quote(text: str) -> str:
    return '"' + text.replace('"', " ").strip() + '"'


def _clip(text: str, words: int = _MAX_QUERY_WORDS) -> str:
    return " ".join(text.split()[:words])


class InternetArchiveSource(Source):
    name = "internet_archive"

    def _queries(self, record: LocalRecord) -> list[str]:
        """Query attempts, most precise first; the first with any hit wins."""
        full = _clip(normalize_title(record.title))
        main = main_title(record.title)
        author = normalize_author(record.author)

        attempts = []
        for title in (full, main):
            if not title:
                continue
            query = f"mediatype:texts AND title:{_quote(title)}"
            if author:
                attempts.append(f"{query} AND creator:{_quote(author)}")
            attempts.append(query)
        # Preserve order, drop repeats (a title with no subtitle yields main == full)
        return list(dict.fromkeys(attempts))

    def search(self, record: LocalRecord, verified_oclc: str | None = None) -> list[Candidate]:
        for query in self._queries(record):
            response = self.session.get(
                SEARCH_URL,
                params={
                    "q": query,
                    "fl[]": ["identifier", "title", "creator", "year", "date"],
                    "rows": 10,
                    "page": 1,
                    "output": "json",
                },
            )
            response.raise_for_status()
            docs = response.json().get("response", {}).get("docs", [])
            if docs:
                # Scoring always compares against the record's full title, so a
                # widened query never loosens the bar a candidate has to clear
                return [self._to_candidate(doc) for doc in docs]
        return []

    def _to_candidate(self, doc: dict) -> Candidate:
        creator = doc.get("creator", "")
        if isinstance(creator, list):
            creator = "; ".join(creator)
        title_field = doc.get("title", "")
        if isinstance(title_field, list):
            title_field = title_field[0] if title_field else ""
        identifier = doc.get("identifier", "")
        return Candidate(
            source=self.name,
            title=title_field,
            author=creator,
            year=str(doc.get("year") or doc.get("date") or ""),
            url=f"https://archive.org/details/{identifier}",
            identifier=identifier,
        )
