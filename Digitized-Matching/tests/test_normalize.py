from catalog_match.normalize import (
    extract_year,
    fold,
    main_title,
    normalize_author,
    normalize_title,
    trim_dangling,
)


def test_title_strips_gmd_and_punctuation():
    assert normalize_title("The great houses of New Orleans [microform] :") == "great houses of new orleans"


def test_title_strips_leading_article():
    assert normalize_title("A history of Mecklenburg County") == "history of mecklenburg county"
    assert normalize_title("La vie de Charlotte") == "vie de charlotte"


def test_title_folds_diacritics():
    assert normalize_title("Précis historique") == normalize_title("Precis historique")
    assert normalize_title("Café société") == "cafe societe"


def test_title_empty():
    assert normalize_title("") == ""


def test_author_strips_life_dates():
    assert normalize_author("Graham, Billy, 1918-2018.") == "graham billy"
    assert normalize_author("Twain, Mark, 1835-1910") == "twain mark"
    assert normalize_author("Smith, John, b. 1870") == "smith john"


def test_author_strips_relator():
    assert normalize_author("Jones, Mary, editor.") == "jones mary"


def test_author_strips_dates_and_relator_together():
    # Regression: dates were left behind when a relator term followed them
    assert normalize_author("Golden, Harry, 1902-1981, author.") == "golden harry"
    assert normalize_author("Miller, Heather Ross, 1939-2025, editor") == "miller heather ross"


def test_apostrophes_do_not_leave_stray_tokens():
    assert normalize_title("King's Mountain") == "kings mountain"
    assert normalize_author("O'Connor, Flannery") == "oconnor flannery"


def test_main_title_splits_on_subtitle():
    assert main_title("Foxfire 4 : fiddle making, springhouses, horse trading") == "foxfire 4"
    assert main_title("King's Mountain : the epic of the Blue Ridge") == "kings mountain"
    assert main_title("Husbandmen of Plymouth ; farms and villages") == "husbandmen of plymouth"


def test_main_title_without_subtitle_is_whole_title():
    assert main_title("American gold") == "american gold"
    # A colon with no surrounding spaces is not an ISBD subtitle break
    assert main_title("Report 1972:1974") == "report 1972 1974"


def test_author_plain():
    assert normalize_author("Bruce, Curt.") == "bruce curt"


def test_extract_year():
    assert extract_year("c1976") == "1976"
    assert extract_year("[1897?]") == "1897"
    assert extract_year("19uu") == ""
    assert extract_year("") == ""
    assert extract_year("1976-1980") == "1976"


def test_fold():
    assert fold("Müller") == "muller"


def test_trim_dangling_function_words():
    # "Walsh's directory of the city of Charlotte for ..." normalizes to a
    # phrase ending in "for", which matches nothing as an exact phrase
    assert trim_dangling("walshs directory of the city of charlotte for") == "walshs directory of the city of charlotte"
    assert trim_dangling("history of the town and") == "history of the town"
    assert trim_dangling("annual report of the") == "annual report"


def test_trim_dangling_keeps_content_words():
    assert trim_dangling("great houses of new orleans") == "great houses of new orleans"
    assert trim_dangling("") == ""
