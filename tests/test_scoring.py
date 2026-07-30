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
