"""HathiTrust Bibliographic API connector (identifier lookup, no key required).

Docs: https://www.hathitrust.org/member-libraries/resources-for-librarians/data-resources/bibliographic-api/
There is no title-search API, so this source looks up identifiers:
  - a WorldCat-verified OCLC number from this run (matched_via=verified-oclc), and
  - the local record's own OCLC/ISBN/ISSN/LCCN hints (matched_via=hinted-id).
Hinted-id hits are exactly the untrustworthy identifiers this project exists to
work around, so the pipeline still requires them to pass the fuzzy title check.
"""

from __future__ import annotations

from ..records import LocalRecord
from . import Candidate, Source

API_URL = "https://catalog.hathitrust.org/api/volumes/brief/json/{idtype}:{value}"


class HathiTrustSource(Source):
    name = "hathitrust"

    def search(self, record: LocalRecord, verified_oclc: str | None = None) -> list[Candidate]:
        lookups: list[tuple[str, str, str]] = []  # (idtype, value, matched_via)
        if verified_oclc:
            lookups.append(("oclc", verified_oclc, "verified-oclc"))
        for oclc in record.oclc_numbers:
            if oclc != verified_oclc:
                lookups.append(("oclc", oclc, "hinted-id"))
        lookups += [("isbn", isbn, "hinted-id") for isbn in record.isbns]
        lookups += [("issn", issn, "hinted-id") for issn in record.issns]
        if record.lccn:
            lookups.append(("lccn", record.lccn, "hinted-id"))

        candidates: list[Candidate] = []
        seen_records: set[str] = set()
        for idtype, value, matched_via in lookups:
            response = self.session.get(API_URL.format(idtype=idtype, value=value))
            if response.status_code == 404:
                continue
            response.raise_for_status()
            payload = response.json()
            items = payload.get("items") or []
            for rec_number, rec in (payload.get("records") or {}).items():
                if rec_number in seen_records:
                    continue
                seen_records.add(rec_number)
                titles = rec.get("titles") or [""]
                rec_items = [i for i in items if i.get("fromRecord") == rec_number] or items
                full_view = any(i.get("usRightsString") == "Full view" for i in rec_items)
                candidates.append(
                    Candidate(
                        source=self.name,
                        title=titles[0],
                        # The brief response carries no author; scoring drops the
                        # author component and leans on title (+ year for books)
                        year=str(rec.get("publishDates", [""])[0]) if rec.get("publishDates") else "",
                        url=rec.get("recordURL", ""),
                        identifier=rec_number,
                        rights="Full view" if full_view else "Limited (search-only)",
                        matched_via=matched_via,
                    )
                )
        return candidates
