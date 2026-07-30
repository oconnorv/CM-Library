from catalog_match.records import LocalRecord
from catalog_match.scoring import score_candidate
from catalog_match.sources import Candidate


def rec(**kwargs):
    defaults = dict(record_id="r1", title="The great houses of New Orleans", author="Bruce, Curt.", year="1977")
    defaults.update(kwargs)
    return LocalRecord(**defaults)


def cand(**kwargs):
    defaults = dict(source="test", title="Great houses of New Orleans", author="Curt Bruce", year="1977")
    defaults.update(kwargs)
    return Candidate(**defaults)


def test_exact_match_scores_high():
    assert score_candidate(rec(), cand()) > 95


def test_different_book_scores_low():
    other = cand(title="Gardens of the American South", author="Lee, Anne", year="2003")
    assert score_candidate(rec(), other) < 60


def test_author_order_invariant():
    assert score_candidate(rec(author="Bruce, Curt"), cand(author="Curt Bruce")) > 95


def test_missing_author_renormalizes():
    # Record without an author should still score on title+year alone
    score = score_candidate(rec(author=""), cand(author=""))
    assert score > 95


def test_year_distance_penalizes():
    same = score_candidate(rec(), cand(year="1977"))
    far = score_candidate(rec(), cand(year="1990"))
    assert same > far


def test_serial_skips_year():
    serial = rec(material_type="Serial", title="Charlotte medical journal", author="", year="1895")
    c = cand(title="Charlotte medical journal", author="", year="1914")
    assert score_candidate(serial, c) == 100.0


def test_book_same_title_different_year_not_perfect():
    book = rec(material_type="Book", title="Charlotte medical journal", author="", year="1895")
    c = cand(title="Charlotte medical journal", author="", year="1914")
    assert score_candidate(book, c) < 100.0


def test_main_title_rescue_with_corroborating_year():
    # Same work, repository carries a different subtitle (the Foxfire 4 case)
    local = rec(title="Foxfire 4 : fiddle making, springhouses, horse trading, sassafras tea", author="", year="1977")
    c = cand(title="Foxfire 4 : water systems, fiddle making, logging, gardening", author="", year="1977")
    assert score_candidate(local, c) >= 85


def test_main_title_rescue_with_corroborating_author():
    local = rec(title="After San Jacinto : the Texas-Mexican frontier, 1836-1841", author="Nance, Joseph Milton.", year="")
    c = cand(title="after san jacinto", author="Nance, Joseph Milton", year="")
    assert score_candidate(local, c) >= 85


def test_main_title_rescue_needs_corroboration():
    # Nothing but a generic main title in common: no author, no year on either side
    local = rec(title="Annual report : Charlotte water department", author="", year="")
    c = cand(title="Annual report : Piedmont railway company", author="", year="")
    assert score_candidate(local, c) < 85


def test_main_title_rescue_skipped_for_one_word_titles():
    local = rec(title="Greensboro : a pictorial history", author="", year="1977")
    c = cand(title="Greensboro : the city of bridges", author="", year="1977")
    assert score_candidate(local, c) < 85


def test_rescued_score_sorts_below_exact_match():
    local = rec(title="Foxfire 4 : fiddle making, springhouses", author="", year="1977")
    exact = cand(title="Foxfire 4 : fiddle making, springhouses", author="", year="1977")
    rescued = cand(title="Foxfire 4 : water systems, logging", author="", year="1977")
    assert score_candidate(local, exact) > score_candidate(local, rescued)
