# Digitized Matching

Fuzzy-matches bibliographic records from our catalog against trustworthy,
library-maintained repositories — **HathiTrust**, **Internet Archive**,
**DigitalNC**, and **WorldCat** — and writes candidate match URLs to a CSV for
human double-checking, so accepted links can be added to the catalog.

Because identifiers (ISBN, OCLC number, etc.) in many of our records are
untrustworthy from past cataloging practice, matching is driven by **title,
author, and publication year**, not identifiers. Where the pipeline *does* use
an identifier, it is either newly verified against WorldCat during the run, or
it is a hint whose result still has to pass the fuzzy title check.

## How it works

For each record: **load → normalize → query sources → score → emit CSV rows**.

1. **Normalize.** Titles and authors are lowercased, diacritics folded,
   ISBD/MARC punctuation and bracketed terms (`[microform]`) stripped, leading
   articles removed, author life dates (`, 1918-2018`) and relator terms dropped.
2. **Query.** Each enabled source returns candidates:
   - **WorldCat** (Search API v2, needs your WSKey): fielded `ti:`/`au:` search.
     Runs first — a candidate scoring ≥ the *verified threshold* (default 95)
     establishes a **trusted OCLC number** for the record.
   - **HathiTrust** (Bibliographic API, no key): identifier lookup only — there
     is no title-search API. Uses the trusted OCLC number from WorldCat, plus
     any OCLC/ISBN/ISSN/LCCN already on the record as untrusted hints.
   - **Internet Archive** (advanced search API, no key): `mediatype:texts`
     title/creator search. Queries run narrowest-first (full title + author)
     and widen — dropping the author, then shortening to the main title before
     the subtitle — only when a query returns nothing.
   - **DigitalNC** (TIND search at lib.digitalnc.org, no key): title/author
     search. See "Verifying DigitalNC" below.
3. **Score.** 0–100 weighted similarity: title 60% (token-sort ratio), author
   25% (token-set ratio, so "Last, First" ≡ "First Last"), year 15% (penalized
   by distance). Components missing on either side are dropped and the weights
   renormalized — records without authors aren't penalized. For **serials** the
   year component is always skipped (a run spans years). When full titles
   disagree only because the repository carries a different subtitle, an
   exactly-equal main title scores 90 — provided an author or year corroborates
   — so those rows surface but sort below exact matches.
4. **Emit.** Candidates scoring ≥ the emit threshold (default 85, at most 3 per
   source per record) become rows in the review CSV, sorted best-first, with the
   URL, score, rights info, and a blank `review_status` column for staff.

Item-level exports list one row per copy; rows with identical title/author/date
are queried once, with all their call numbers merged into the output row.

## Setup

All commands below are run from this `Digitized-Matching/` directory.

```bash
cd Digitized-Matching
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml   # then add your WorldCat WSKey + secret
```

`config.yaml` is git-ignored — credentials never enter the repository. Without
it, the keyless sources (`internet_archive`, `hathitrust`, `digitalnc`) still
work, but note that with this export HathiTrust produces nothing without
WorldCat: the export has no identifier columns, so the trusted-OCLC path is the
only way in.

## Usage

Pilot run (keyless sources, 25 records — start here):

```bash
python -m catalog_match --input ItemRecordExport.xlsx --output matches.csv \
    --sources internet_archive,digitalnc --formats Book,Serial --limit 25
```

Full run with everything:

```bash
python -m catalog_match --input ItemRecordExport.xlsx --output matches.csv \
    --formats Book,Serial
```

Interrupted? Progress is checkpointed in `matches.csv.checkpoint.db`; records
whose sources all succeeded are skipped on re-run and new rows are appended:

```bash
python -m catalog_match --input ItemRecordExport.xlsx --output matches.csv \
    --formats Book,Serial --resume
```

Options: `--threshold 90` (stricter emit cutoff), `--limit N`, `-v` (per-record
logging), `--sources` (comma list; aliases `ia`, `ht`, `wc`), `--config PATH`.

**Input formats.** `.xlsx`, `.csv`, `.tsv`. The `ItemRecordExport.xlsx` column
layout (`Title, Author, Format, Pub Date, Call No., …`) is recognized
automatically; other layouts can be mapped with
`--csv-map "id=BibID,title=Title245,author=Creator"`. Canonical fields:
`id, title, author, year, publisher, material_type, call_number, isbn, issn,
oclc, lccn` (only title is required; records without an id get stable
`row-N` ids matching the spreadsheet row).

**Runtime.** Politeness rate limits (see `config.example.yaml`) mean roughly
2–4 seconds per record with all four sources — a full ~40k-record run is a
multi-day job. Run it in `screen`/`tmux`, lean on `--resume`, or split by
`--formats`. Format counts in this export: ~39k Book, ~1.4k Serial.

## The review workflow

Open `matches.csv` in Excel/Sheets, filter or sort by `score` descending, and
fill in `review_status` (e.g. `accepted` / `rejected` / `unsure`). Columns:

| column | meaning |
|---|---|
| `local_id` | record id, or `row-N` = row N of the input spreadsheet |
| `call_numbers` | all copies' call numbers, `;`-joined |
| `source` | which repository the candidate came from |
| `match_url` | the link to verify and, if accepted, add to the catalog |
| `rights_or_access` | e.g. HathiTrust `Full view` vs `Limited (search-only)` |
| `score` | 0–100 similarity (higher = more confident) |
| `matched_via` | `fuzzy` (title/author search), `verified-oclc` (OCLC confirmed via WorldCat this run), `hinted-id` (record's own untrusted identifier — passed the fuzzy check, but scrutinize) |

Serials caveat: repository links are usually title-level; which volumes/years
the repository actually holds still needs human eyes.

## First-run verification checklist

This tool was developed in an environment whose network policy blocked the
library APIs, so response parsing follows each API's documentation but could
not be exercised live. On first pilot run, confirm:

1. `--sources ia --limit 5` emits plausible archive.org URLs for well-known titles.
2. With your WSKey in `config.yaml`: `--sources wc,ht --limit 5` emits WorldCat
   matches and (for verified matches held by HathiTrust) HathiTrust rows.
3. **Verifying DigitalNC**: `--sources digitalnc --limit 5 -v`. If every record
   logs a "returned non-JSON" warning, TIND's JSON output format differs from
   the expected `of=recjson`; try `curl 'https://lib.digitalnc.org/search?p=charlotte&of=recjson&rg=3'`
   and adjust `catalog_match/sources/digitalnc.py` (or ask NCDHC — as a DPLA
   hub they also expose OAI-PMH for bulk harvest, a good plan B).

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest tests/
```

All connector tests run against canned API responses — no network or
credentials needed. Add a new repository by subclassing `Source` in
`catalog_match/sources/` and registering it in `build_sources`.
