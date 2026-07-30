"""Score a repository candidate against a local record on title/author/year."""

from __future__ import annotations

from rapidfuzz import fuzz

from .normalize import extract_year, main_title, normalize_author, normalize_title
from .records import LocalRecord
from .sources import Candidate

_TITLE_WEIGHT = 0.60
_AUTHOR_WEIGHT = 0.25
_YEAR_WEIGHT = 0.15
# How much a year of distance costs, out of 100; ±2 years still scores well
_YEAR_PENALTY_PER_YEAR = 15
# Ceiling for a match that rests on main titles agreeing while subtitles differ.
# Kept below a full-title match so those rows sort lower in the review queue,
# but above the default emit threshold (85) so reviewers see them at all.
_MAIN_TITLE_CAP = 90.0
# Main titles this short ("Poems") match too much; require the full title to agree
_MIN_MAIN_TITLE_WORDS = 2


def title_similarity(local_title: str, candidate_title: str) -> tuple[float, bool]:
    """(similarity, rescued): full normalized titles compared; when they
    disagree, exactly-equal main titles rescue the score (capped), since
    repositories often carry a different subtitle for the same work.
    """
    full = float(fuzz.token_sort_ratio(normalize_title(local_title), normalize_title(candidate_title)))
    local_main = main_title(local_title)
    if len(local_main.split()) < _MIN_MAIN_TITLE_WORDS:
        return full, False
    if local_main == main_title(candidate_title) and full < _MAIN_TITLE_CAP:
        return _MAIN_TITLE_CAP, True
    return full, False


def score_candidate(record: LocalRecord, candidate: Candidate) -> float:
    """Weighted 0-100 similarity. Components missing on either side are dropped
    and the remaining weights renormalized, so a record without an author
    (anonymous works) isn't penalized for the candidate lacking one too.
    The year component is skipped for serials — a serial's run spans years, so
    date distance carries no signal about whether it's the same publication.
    """
    title_score, rescued = title_similarity(record.title, candidate.title)
    components: list[tuple[float, float]] = [(_TITLE_WEIGHT, title_score)]

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

    if rescued and len(components) == 1:
        # A rescued title standing entirely alone is too thin — generic main
        # titles ("Annual report : ...") would sail past the threshold with no
        # author or year to corroborate. Fall back to the full-title comparison.
        full = float(fuzz.token_sort_ratio(normalize_title(record.title), normalize_title(candidate.title)))
        components = [(_TITLE_WEIGHT, full)]

    total_weight = sum(w for w, _ in components)
    return round(sum(w * s for w, s in components) / total_weight, 1)
