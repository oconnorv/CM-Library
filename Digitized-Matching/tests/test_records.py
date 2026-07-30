import pytest
from openpyxl import Workbook

from catalog_match.records import load_records

HEADER = ["Title", "Author", "Format", "Pub Date", "Call No.", "Sort Title", "Sort Author"]
ROW = ["The gospel according to Billy", "Ashman, Charles R.", "Book", "c1977", "NCR B G7343 A7g", "GOSPEL...", "ASHMAN..."]


def test_load_item_export_xlsx(tmp_path):
    """The real ItemRecordExport.xlsx layout loads with no --csv-map at all."""
    wb = Workbook()
    ws = wb.active
    ws.append(HEADER)
    ws.append(ROW)
    ws.append(["Charlotte medical journal", "", "Serial", "1895", "NCR 610.5", "", ""])
    path = tmp_path / "export.xlsx"
    wb.save(path)

    records = list(load_records(path))
    assert len(records) == 2
    book = records[0]
    assert book.record_id == "row-2"
    assert book.title == "The gospel according to Billy"
    assert book.author == "Ashman, Charles R."
    assert book.year == "1977"  # extracted from "c1977"
    assert book.material_type == "Book"
    assert book.call_number == "NCR B G7343 A7g"
    assert not book.is_serial
    assert records[1].is_serial


def test_load_csv_with_mapping(tmp_path):
    path = tmp_path / "export.csv"
    path.write_text(
        "BibID,Title245,Creator,Date,ISBNs\n"
        'b100,"How to be born again","Graham, Billy, 1918-2018.",1977,0849900425; 978-0849900426\n'
    )
    records = list(load_records(path, {"id": "BibID", "title": "Title245", "author": "Creator", "year": "Date", "isbn": "ISBNs"}))
    assert len(records) == 1
    r = records[0]
    assert r.record_id == "b100"
    assert r.isbns == ["0849900425", "9780849900426"]


def test_missing_title_column_raises(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("Name,Year\nfoo,1990\n")
    with pytest.raises(ValueError, match="title column"):
        list(load_records(path))


def test_unknown_csv_map_field_raises(tmp_path):
    path = tmp_path / "ok.csv"
    path.write_text("Title\nfoo\n")
    with pytest.raises(ValueError, match="unknown field"):
        list(load_records(path, {"nope": "Title"}))


def test_blank_rows_skipped(tmp_path):
    path = tmp_path / "gaps.csv"
    path.write_text("Title,Author\nReal book,Someone\n,\n")
    records = list(load_records(path))
    assert len(records) == 1


def test_oclc_hint_normalization(tmp_path):
    path = tmp_path / "ids.csv"
    path.write_text('Title,OCLC\nA book,"(OCoLC)00424023; ocm424023"\n')
    records = list(load_records(path))
    assert records[0].oclc_numbers == ["424023", "424023"]


def test_unsupported_extension(tmp_path):
    path = tmp_path / "records.mrc"
    path.write_bytes(b"")
    with pytest.raises(ValueError, match="Unsupported input format"):
        list(load_records(path))
