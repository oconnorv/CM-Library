"""End-to-end pipeline test with a stubbed source — no network."""

import csv

from catalog_match import cli
from catalog_match.sources import Candidate, Source


class StubSource(Source):
    name = "internet_archive"
    calls = []

    def __init__(self, session=None, config=None):
        pass

    def search(self, record, verified_oclc=None):
        StubSource.calls.append(record.record_id)
        return [
            Candidate(source=self.name, title=record.title, author=record.author, year=record.year, url="https://archive.org/details/stub", identifier="stub"),
            Candidate(source=self.name, title="Completely unrelated item", author="Nobody", year="1850", url="https://archive.org/details/no", identifier="no"),
        ]


def write_input(path):
    path.write_text(
        "Title,Author,Format,Pub Date,Call No.\n"
        '"The gospel according to Billy","Ashman, Charles R.",Book,1977,NCR B G7343\n'
        '"The gospel according to Billy","Ashman, Charles R.",Book,1977,NCR B G7343 c.2\n'
        '"Charlotte medical journal",,Serial,1895,NCR 610.5\n'
        '"A vinyl record",,Vinyl,1970,NCR 780\n'
    )


def run_cli(tmp_path, monkeypatch, extra_args=()):
    monkeypatch.setitem(
        __import__("catalog_match.sources", fromlist=["build_sources"]).__dict__,
        "build_sources",
        lambda names, config: {"internet_archive": StubSource()},
    )
    monkeypatch.setattr(cli, "build_sources", lambda names, config: {"internet_archive": StubSource()})
    input_path = tmp_path / "export.csv"
    output_path = tmp_path / "matches.csv"
    write_input(input_path)
    args = ["--input", str(input_path), "--output", str(output_path), "--sources", "internet_archive", *extra_args]
    assert cli.run(args) == 0
    with open(output_path) as fh:
        return list(csv.DictReader(fh))


def test_pipeline_dedupes_copies_filters_formats_and_scores(tmp_path, monkeypatch):
    StubSource.calls = []
    rows = run_cli(tmp_path, monkeypatch, ("--formats", "Book,Serial"))
    # 2 book copies deduped into 1 group + 1 serial; vinyl filtered out
    assert len(StubSource.calls) == 2
    # Only the high-scoring candidate per group survives the threshold
    assert len(rows) == 2
    book_row = next(r for r in rows if r["material_type"] == "Book")
    assert book_row["call_numbers"] == "NCR B G7343; NCR B G7343 c.2"
    assert float(book_row["score"]) >= 85
    assert book_row["match_url"] == "https://archive.org/details/stub"
    assert book_row["review_status"] == ""
    assert set(rows[0]) == set(__import__("catalog_match.output", fromlist=["COLUMNS"]).COLUMNS)


def test_pipeline_resume_skips_processed(tmp_path, monkeypatch):
    StubSource.calls = []
    run_cli(tmp_path, monkeypatch, ("--formats", "Book,Serial"))
    first_calls = len(StubSource.calls)
    rows = run_cli(tmp_path, monkeypatch, ("--formats", "Book,Serial", "--resume"))
    # Second run does no new work and does not duplicate rows
    assert len(StubSource.calls) == first_calls
    assert len(rows) == 2
