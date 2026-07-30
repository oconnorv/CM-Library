from catalog_match.normalize import extract_year, fold, normalize_author, normalize_title


def test_title_strips_gmd_and_punctuation():
    assert normalize_title("The great houses of New Orleans [microform] :") == "great houses of new orleans"


def test_title_strips_leading_article():
    assert normalize_title("A history of Mecklenburg County") == "history of mecklenburg county"
    assert normalize_title("La vie de Charlotte") == "vie de charlotte"


def test_title_folds_diacritics():
    assert normalize_title("Précis d'histoire") == normalize_title("Precis d histoire")


def test_title_empty():
    assert normalize_title("") == ""


def test_author_strips_life_dates():
    assert normalize_author("Graham, Billy, 1918-2018.") == "graham billy"
    assert normalize_author("Twain, Mark, 1835-1910") == "twain mark"
    assert normalize_author("Smith, John, b. 1870") == "smith john"


def test_author_strips_relator():
    assert normalize_author("Jones, Mary, editor.") == "jones mary"


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
