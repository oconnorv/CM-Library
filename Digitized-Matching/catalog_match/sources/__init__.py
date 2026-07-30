"""Repository connectors. Each source turns a LocalRecord into Candidate matches."""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

USER_AGENT = "cm-library-catalog-match/1.0 (Charlotte Mecklenburg Library metadata reconciliation)"


@dataclass
class Candidate:
    source: str
    title: str
    author: str = ""
    year: str = ""
    url: str = ""
    identifier: str = ""
    rights: str = ""
    # How we got here: "fuzzy" (title/author search), "verified-oclc" (OCLC number
    # confirmed via WorldCat this run), or "hinted-id" (the local record's own
    # untrusted identifier — must still pass the fuzzy score threshold)
    matched_via: str = "fuzzy"


class RateLimitedSession:
    """requests.Session wrapper enforcing a minimum interval between calls,
    with exponential-backoff retries on 429/5xx and connection errors."""

    def __init__(self, min_interval: float = 1.0, max_retries: int = 4, timeout: float = 30.0):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.timeout = timeout
        self._last_request = 0.0

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        backoff = 2.0
        for attempt in range(self.max_retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            try:
                self._last_request = time.monotonic()
                response = self.session.request(method, url, **kwargs)
                if response.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                return response
            except requests.ConnectionError:
                if attempt == self.max_retries:
                    raise
                time.sleep(backoff)
                backoff *= 2
        raise RuntimeError("unreachable")

    def get(self, url: str, **kwargs) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        return self.request("POST", url, **kwargs)


class Source:
    """Base class. Subclasses set `name` and implement search().

    verified_oclc is an OCLC number confirmed via WorldCat earlier in the same
    run; identifier-lookup sources (HathiTrust) use it, search sources ignore it.
    """

    name = "source"

    def __init__(self, session: RateLimitedSession, config: dict):
        self.session = session
        self.config = config

    def search(self, record, verified_oclc: str | None = None) -> list[Candidate]:
        raise NotImplementedError


def build_sources(names: list[str], config: dict) -> dict[str, Source]:
    """Instantiate the requested sources, each with its own rate-limited session."""
    from .digitalnc import DigitalNCSource
    from .hathitrust import HathiTrustSource
    from .internet_archive import InternetArchiveSource
    from .worldcat import WorldCatSource

    registry = {
        "worldcat": WorldCatSource,
        "hathitrust": HathiTrustSource,
        "internet_archive": InternetArchiveSource,
        "digitalnc": DigitalNCSource,
    }
    aliases = {"ia": "internet_archive", "ht": "hathitrust", "wc": "worldcat"}

    requested = set()
    for raw in names:
        name = aliases.get(raw.strip().lower(), raw.strip().lower())
        if name not in registry:
            raise ValueError(f"Unknown source '{raw}'. Available: {', '.join(sorted(registry))}")
        requested.add(name)

    # Registry order is execution order: worldcat must run before hathitrust so
    # a verified OCLC number is available for the HathiTrust lookup.
    sources: dict[str, Source] = {}
    rate_limits = config.get("rate_limits", {})
    for name, cls in registry.items():
        if name in requested:
            session = RateLimitedSession(min_interval=float(rate_limits.get(name, 1.0)))
            sources[name] = cls(session, config)
    return sources
