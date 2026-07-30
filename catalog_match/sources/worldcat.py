"""WorldCat Search API v2 connector (OAuth2 client-credentials with a WSKey).

Docs: https://developer.api.oclc.org/wcv2
A confident match here supplies a *trusted* OCLC number that the HathiTrust
connector can look up, repairing the local record's unreliable identifiers.
"""

from __future__ import annotations

import time

from ..normalize import normalize_author, normalize_title
from ..records import LocalRecord
from . import Candidate, Source

TOKEN_URL = "https://oauth.oclc.org/token"
SEARCH_URL = "https://americas.discovery.api.oclc.org/worldcat/search/v2/brief-bibs"
_MAX_QUERY_WORDS = 10


class WorldCatSource(Source):
    name = "worldcat"

    def __init__(self, session, config):
        super().__init__(session, config)
        creds = (config.get("worldcat") or {})
        self.key = creds.get("key", "")
        self.secret = creds.get("secret", "")
        if not self.key or not self.secret or self.key == "YOUR_WSKEY":
            raise ValueError(
                "WorldCat requires a WSKey: copy config.example.yaml to config.yaml and "
                "fill in worldcat.key / worldcat.secret, or run without the worldcat source."
            )
        self._token = ""
        self._token_expires = 0.0

    def _access_token(self) -> str:
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        response = self.session.post(
            TOKEN_URL,
            auth=(self.key, self.secret),
            data={"grant_type": "client_credentials", "scope": "wcapi"},
        )
        response.raise_for_status()
        payload = response.json()
        self._token = payload["access_token"]
        self._token_expires = time.time() + float(payload.get("expires_in", 1200))
        return self._token

    def search(self, record: LocalRecord, verified_oclc: str | None = None) -> list[Candidate]:
        title = normalize_title(record.title)
        if not title:
            return []
        query = f'ti:"{" ".join(title.split()[:_MAX_QUERY_WORDS])}"'
        author = normalize_author(record.author)
        if author:
            query += f' AND au:"{author}"'

        response = self.session.get(
            SEARCH_URL,
            params={"q": query, "limit": 10, "orderBy": "bestMatch"},
            headers={"Authorization": f"Bearer {self._access_token()}", "Accept": "application/json"},
        )
        response.raise_for_status()
        records = response.json().get("briefRecords") or []

        candidates = []
        for brief in records:
            oclc_number = str(brief.get("oclcNumber", ""))
            candidates.append(
                Candidate(
                    source=self.name,
                    title=brief.get("title", ""),
                    author=brief.get("creator", ""),
                    year=str(brief.get("date", "")),
                    url=f"https://search.worldcat.org/title/{oclc_number}" if oclc_number else "",
                    identifier=oclc_number,
                )
            )
        return candidates
