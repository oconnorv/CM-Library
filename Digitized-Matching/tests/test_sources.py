"""Connector tests with a fake HTTP session — no network, no credentials."""

import json

import pytest

from catalog_match.records import LocalRecord
from catalog_match.sources import Candidate, build_sources
from catalog_match.sources.digitalnc import DigitalNCSource
from catalog_match.sources.hathitrust import HathiTrustSource
from catalog_match.sources.internet_archive import InternetArchiveSource
from catalog_match.sources.worldcat import WorldCatSource


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        if isinstance(self._payload, (dict, list)):
            return self._payload
        return json.loads(self._payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    """Stands in for RateLimitedSession; hands out queued responses and logs calls."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)


def record(**kwargs):
    defaults = dict(record_id="row-2", title="The gospel according to Billy", author="Ashman, Charles R.", year="1977")
    defaults.update(kwargs)
    return LocalRecord(**defaults)


# --- Internet Archive ---

IA_PAYLOAD = {
    "response": {
        "docs": [
            {"identifier": "gospelaccording00ashm", "title": "The gospel according to Billy", "creator": ["Ashman, Charles R."], "year": 1977},
            {"identifier": "other", "title": ["Some other book"], "date": "1980-01-01"},
        ]
    }
}


def test_internet_archive_parses_docs():
    source = InternetArchiveSource(FakeSession([FakeResponse(IA_PAYLOAD)]), {})
    candidates = source.search(record())
    assert len(candidates) == 2
    first = candidates[0]
    assert first.url == "https://archive.org/details/gospelaccording00ashm"
    assert first.author == "Ashman, Charles R."
    assert first.year == "1977"
    # list-valued title handled
    assert candidates[1].title == "Some other book"


def test_internet_archive_query_includes_title_and_creator():
    session = FakeSession([FakeResponse(IA_PAYLOAD)])
    InternetArchiveSource(session, {}).search(record())
    params = session.calls[0][2]["params"]
    assert "mediatype:texts" in params["q"]
    assert "title:" in params["q"] and "creator:" in params["q"]


def test_internet_archive_empty_title_skips_network():
    session = FakeSession([])
    assert InternetArchiveSource(session, {}).search(record(title="")) == []
    assert session.calls == []


def test_internet_archive_stops_at_first_query_with_hits():
    session = FakeSession([FakeResponse(IA_PAYLOAD), FakeResponse(IA_PAYLOAD)])
    InternetArchiveSource(session, {}).search(record())
    assert len(session.calls) == 1


def test_internet_archive_widens_query_when_no_hits():
    """Regression: a long subtitle the repository spells differently used to
    return nothing, because only the full-title phrase query was ever tried."""
    empty = {"response": {"docs": []}}
    session = FakeSession([FakeResponse(empty), FakeResponse(IA_PAYLOAD)])
    rec = record(title="Foxfire 4 : fiddle making, springhouses, horse trading, sassafras tea", author="")
    candidates = InternetArchiveSource(session, {}).search(rec)
    assert len(candidates) == 2
    queries = [call[2]["params"]["q"] for call in session.calls]
    assert 'title:"foxfire 4 fiddle making springhouses horse trading sassafras tea"' in queries[0]
    # Falls back to the main title, which is what actually matches
    assert queries[-1] == 'mediatype:texts AND title:"foxfire 4"'


def test_internet_archive_query_order_drops_creator_before_widening_title():
    empty = {"response": {"docs": []}}
    session = FakeSession([FakeResponse(empty)] * 4)
    InternetArchiveSource(session, {}).search(record(title="Old Hickory : a life of Andrew Jackson"))
    queries = [call[2]["params"]["q"] for call in session.calls]
    assert len(queries) == 4
    assert "creator:" in queries[0] and "old hickory a life of andrew jackson" in queries[0]
    assert "creator:" not in queries[1]
    assert "creator:" in queries[2] and 'title:"old hickory"' in queries[2]
    assert queries[3] == 'mediatype:texts AND title:"old hickory"'


def test_internet_archive_no_duplicate_queries_without_subtitle():
    empty = {"response": {"docs": []}}
    session = FakeSession([FakeResponse(empty)] * 4)
    InternetArchiveSource(session, {}).search(record(title="American gold", author=""))
    # main title == full title and no author, so there is only one distinct query
    assert len(session.calls) == 1


# --- WorldCat ---

WC_TOKEN = {"access_token": "tok-123", "expires_in": 1199}
WC_SEARCH = {
    "numberOfRecords": 1,
    "briefRecords": [
        {"oclcNumber": "3168894", "title": "The gospel according to Billy", "creator": "Charles R. Ashman", "date": "1977", "publisher": "Lyle Stuart"}
    ],
}


def worldcat_config():
    return {"worldcat": {"key": "k", "secret": "s"}}


def test_worldcat_requires_credentials():
    with pytest.raises(ValueError, match="WSKey"):
        WorldCatSource(FakeSession([]), {})
    with pytest.raises(ValueError, match="WSKey"):
        WorldCatSource(FakeSession([]), {"worldcat": {"key": "YOUR_WSKEY", "secret": "x"}})


def test_worldcat_token_then_search():
    session = FakeSession([FakeResponse(WC_TOKEN), FakeResponse(WC_SEARCH)])
    source = WorldCatSource(session, worldcat_config())
    candidates = source.search(record())
    assert session.calls[0][0] == "POST"  # token request first
    assert candidates[0].identifier == "3168894"
    assert candidates[0].url == "https://search.worldcat.org/title/3168894"


def test_worldcat_token_cached_between_searches():
    session = FakeSession([FakeResponse(WC_TOKEN), FakeResponse(WC_SEARCH), FakeResponse(WC_SEARCH)])
    source = WorldCatSource(session, worldcat_config())
    source.search(record())
    source.search(record())
    token_posts = [c for c in session.calls if c[0] == "POST"]
    assert len(token_posts) == 1


# --- HathiTrust ---

HT_PAYLOAD = {
    "records": {
        "001263731": {
            "recordURL": "https://catalog.hathitrust.org/Record/001263731",
            "titles": ["The gospel according to Billy."],
            "publishDates": ["1977"],
            "isbns": [], "oclcs": ["3168894"],
        }
    },
    "items": [
        {"htid": "mdp.39015000000001", "fromRecord": "001263731", "itemURL": "https://hdl.handle.net/2027/mdp.39015000000001", "rightsCode": "ic", "usRightsString": "Limited (search-only)"}
    ],
}


def test_hathitrust_verified_oclc_lookup():
    session = FakeSession([FakeResponse(HT_PAYLOAD)])
    source = HathiTrustSource(session, {})
    candidates = source.search(record(), verified_oclc="3168894")
    assert len(candidates) == 1
    c = candidates[0]
    assert c.matched_via == "verified-oclc"
    assert c.rights == "Limited (search-only)"
    assert c.url == "https://catalog.hathitrust.org/Record/001263731"
    assert "oclc:3168894" in session.calls[0][1]


def test_hathitrust_hinted_ids_and_dedupe():
    # Same HT record reachable via two hints — only emitted once
    session = FakeSession([FakeResponse(HT_PAYLOAD), FakeResponse(HT_PAYLOAD)])
    source = HathiTrustSource(session, {})
    candidates = source.search(record(oclc_numbers=["3168894"], isbns=["0818402180"]))
    assert len(candidates) == 1
    assert candidates[0].matched_via == "hinted-id"
    assert len(session.calls) == 2


def test_hathitrust_no_identifiers_no_calls():
    session = FakeSession([])
    assert HathiTrustSource(session, {}).search(record()) == []
    assert session.calls == []


def test_hathitrust_full_view_rights():
    payload = json.loads(json.dumps(HT_PAYLOAD))
    payload["items"][0]["usRightsString"] = "Full view"
    session = FakeSession([FakeResponse(payload)])
    candidates = HathiTrustSource(session, {}).search(record(), verified_oclc="3168894")
    assert candidates[0].rights == "Full view"


# --- DigitalNC ---

DNC_PAYLOAD = [
    {"recid": 12345, "title": {"title": "The gospel according to Billy"}, "authors": [{"full_name": "Ashman, Charles R."}], "imprint": {"date": "1977"}},
    {"recid": 99, "title": "Plain string title"},
]


def test_digitalnc_parses_recjson_shapes():
    session = FakeSession([FakeResponse(DNC_PAYLOAD)])
    candidates = DigitalNCSource(session, {}).search(record())
    assert len(candidates) == 2
    assert candidates[0].url == "https://lib.digitalnc.org/record/12345"
    assert candidates[0].author == "Ashman, Charles R."
    assert candidates[0].year == "1977"
    assert candidates[1].title == "Plain string title"


def test_digitalnc_html_response_raises_helpful_error():
    class HtmlResponse(FakeResponse):
        def json(self):
            raise ValueError("not json")

    session = FakeSession([HtmlResponse("<html>", 200)])
    with pytest.raises(RuntimeError, match="non-JSON"):
        DigitalNCSource(session, {}).search(record())


# --- registry ---

def test_build_sources_orders_worldcat_before_hathitrust():
    sources = build_sources(["ht", "wc"], worldcat_config())
    assert list(sources) == ["worldcat", "hathitrust"]


def test_build_sources_unknown_name():
    with pytest.raises(ValueError, match="Unknown source"):
        build_sources(["googlebooks"], {})
