"""Internet Archive connector via the open advancedsearch.php JSON API (no key)."""

from __future__ import annotations

from ..normalize import normalize_author, normalize_title
from ..records import LocalRecord
from . import Candidate, Source

SEARCH_URL = "https://archive.org/advancedsearch.php"
# Long subtitles hurt phrase queries; a title prefix is enough to recall candidates
_MAX_QUERY_WORDS = 10


def _quote(text: str) -> str:
    return '"' + text.replace('"', " ").strip() + '"'


class InternetArchiveSource(Source):
    name = "internet_archive"

    def search(self, record: LocalRecord, verified_oclc: str | None = None) -> list[Candidate]:
        title = normalize_title(record.title)
        if not title:
            return []
        query = f"mediatype:texts AND title:{_quote(' '.join(title.split()[:_MAX_QUERY_WORDS]))}"
        author = normalize_author(record.author)
        if author:
            query += f" AND creator:{_quote(author)}"

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

        candidates = []
        for doc in docs:
            creator = doc.get("creator", "")
            if isinstance(creator, list):
                creator = "; ".join(creator)
            title_field = doc.get("title", "")
            if isinstance(title_field, list):
                title_field = title_field[0] if title_field else ""
            year = str(doc.get("year") or doc.get("date") or "")
            identifier = doc.get("identifier", "")
            candidates.append(
                Candidate(
                    source=self.name,
                    title=title_field,
                    author=creator,
                    year=year,
                    url=f"https://archive.org/details/{identifier}",
                    identifier=identifier,
                )
            )
        return candidates
