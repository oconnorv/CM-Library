"""Score a repository candidate against a local record on title/author/year."""

from __future__ import annotations

from rapidfuzz import fuzz

from .normalize import extract_year, normalize_author, normalize_title
from .records import LocalRecord
from .sources import Candidate

_TITLE_WEIGHT = 0.60
_AUTHOR_WEIGHT = 0.25
_YEAR_WEIGHT = 0.15
# How much a year of distance costs, out of 100; ±2 years still scores well
_YEAR_PENALTY_PER_YEAR = 15


def score_candidate(record: LocalRecord, candidate: Candidate) -> float:
    """Weighted 0-100 similarity. Components missing on either side are dropped
    and the remaining weights renormalized, so a record without an author
    (anonymous works) isn't penalized for the candidate lacking one too.
    The year component is skipped for serials — a serial's run spans years, so
    date distance carries no signal about whether it's the same publication.
    """
    components: list[tuple[float, float]] = []

    title_score = fuzz.token_sort_ratio(
        normalize_title(record.title),
        normalize_title(candidate.title),
    )
    components.append((_TITLE_WEIGHT, title_score))

    rec_author = normalize_author(record.author)
    cand_author = normalize_author(candidate.author)
    if rec_author and cand_author:
        # token_set_ratio tolerates "Last, First" vs "First Last" and added middle names
        components.append((_AUTHOR_WEIGHT, fuzz.token_set_ratio(rec_author, cand_author)))

    rec_year = extract_year(record.year)
    cand_year = extract_year(candidate.year)
    if rec_year and cand_year and not record.is_serial:
        distance = abs(int(rec_year) - int(cand_year))
        components.append((_YEAR_WEIGHT, max(0.0, 100.0 - _YEAR_PENALTY_PER_YEAR * distance)))

    total_weight = sum(w for w, _ in components)
    return round(sum(w * s for w, s in components) / total_weight, 1)
