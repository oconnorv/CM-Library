"""Normalization of titles, authors, and years for fuzzy comparison.

MARC cataloging conventions (ISBD punctuation, GMDs, name dates, relator
terms) add noise that would depress fuzzy scores, so we strip them before
comparing rather than comparing raw strings.
"""

from __future__ import annotations

import re
import unicodedata

# Bracketed general material designations and similar: [microform], [electronic resource]...
_BRACKETED = re.compile(r"\[[^\]]*\]")
# Leading articles in languages common to US research collections
_ARTICLES = re.compile(
    r"^(the|an?|la|le|les|l'|el|los|las|un|una|une|der|die|das|den|ein|eine|il|lo|gli|de|het|een)\s+",
    re.IGNORECASE,
)
_PUNCT = re.compile(r"[^\w\s]")
_WS = re.compile(r"\s+")
# Apostrophes are dropped rather than spaced, so "King's" -> "kings" instead of
# the stray one-letter token "king s", which breaks phrase queries
_APOSTROPHE = re.compile(r"[’']")
# ISBD separates the main title from its subtitle with " : " (or " ; ")
_SUBTITLE = re.compile(r"\s+[:;=]\s+|\s+/\s+")
# Life dates appended to headings: ", 1870-1950" / ", b. 1870" / ", d. 1950" / ", 1870-"
_AUTHOR_DATES = re.compile(r",?\s*(b\.|d\.|ca\.|fl\.|active)?\s*\d{3,4}\??\s*-?\s*(\d{3,4}\??)?\.?\s*$")
_RELATORS = re.compile(
    r",?\s*(author|editor|compiler|translator|illustrator|joint author|ed|comp|tr|ill)\.?\s*$",
    re.IGNORECASE,
)
# Lookarounds, not \b: years are often glued to letters ("c1976") but must not
# be carved out of longer digit runs
_YEAR = re.compile(r"(?<!\d)(1[4-9]\d{2}|20\d{2})(?!\d)")


def fold(text: str) -> str:
    """Casefold and strip diacritics (é -> e) so accent variants compare equal."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def normalize_title(title: str) -> str:
    if not title:
        return ""
    title = _BRACKETED.sub(" ", title)
    title = fold(title)
    title = _APOSTROPHE.sub("", title)
    title = _PUNCT.sub(" ", title)
    title = _ARTICLES.sub("", title)
    return _WS.sub(" ", title).strip()


def main_title(title: str) -> str:
    """Normalized title up to the subtitle break.

    Repositories often carry a different subtitle for the same work (our
    "Foxfire 4 : fiddle making, springhouses..." is Internet Archive's
    "Foxfire 4 : water systems, fiddle making..."), so the main title is the
    part that can be relied on for a phrase search.
    """
    if not title:
        return ""
    return normalize_title(_SUBTITLE.split(title, maxsplit=1)[0])


def normalize_author(author: str) -> str:
    if not author:
        return ""
    author = author.strip()
    # Trailing life dates and relator terms appear in either order
    # ("Golden, Harry, 1902-1981, author."), so strip until nothing more comes off
    while True:
        stripped = _RELATORS.sub("", _AUTHOR_DATES.sub("", author))
        if stripped == author:
            break
        author = stripped
    author = fold(author)
    author = _APOSTROPHE.sub("", author)
    author = _PUNCT.sub(" ", author)
    return _WS.sub(" ", author).strip()


def extract_year(text: str) -> str:
    """Pull the first plausible publication year (1400-2099) out of free text."""
    if not text:
        return ""
    m = _YEAR.search(str(text))
    return m.group(1) if m else ""
