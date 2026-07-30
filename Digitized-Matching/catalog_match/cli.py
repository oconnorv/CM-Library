"""Command-line pipeline: load records → query sources → score → review CSV.

Example (pilot run against the keyless sources):
    python -m catalog_match --input ItemRecordExport.xlsx --output matches.csv \
        --sources internet_archive,digitalnc --formats Book,Serial --limit 25
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

from .checkpoint import Checkpoint
from .normalize import normalize_author, normalize_title
from .output import ReviewCsv
from .records import LocalRecord, load_records
from .scoring import score_candidate
from .sources import build_sources

log = logging.getLogger("catalog_match")

DEFAULT_SOURCES = "worldcat,hathitrust,internet_archive,digitalnc"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="catalog_match",
        description="Fuzzy-match catalog records against HathiTrust, Internet Archive, DigitalNC, and WorldCat.",
    )
    parser.add_argument("--input", required=True, help="Bib record export (.csv, .tsv, or .xlsx)")
    parser.add_argument("--output", required=True, help="Review CSV to write")
    parser.add_argument("--sources", default=DEFAULT_SOURCES, help=f"Comma-separated sources (default: {DEFAULT_SOURCES}; aliases ia, ht, wc)")
    parser.add_argument("--config", default="config.yaml", help="YAML config with WorldCat WSKey etc. (default: config.yaml)")
    parser.add_argument("--csv-map", default="", help='Map input column names, e.g. "id=BibID,title=Title245"')
    parser.add_argument("--formats", default="", help='Only process these material types, e.g. "Book,Serial" (default: all)')
    parser.add_argument("--threshold", type=float, default=None, help="Emit threshold 0-100 (overrides config; default 85)")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N records (0 = all) — use for pilot runs")
    parser.add_argument("--resume", action="store_true", help="Skip records already in the checkpoint and append to the output CSV")
    parser.add_argument("-v", "--verbose", action="store_true", help="Per-record debug logging")
    return parser.parse_args(argv)


def load_config(path: str) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        return {}
    with open(config_path) as fh:
        return yaml.safe_load(fh) or {}


def parse_csv_map(raw: str) -> dict[str, str]:
    mapping = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise SystemExit(f"--csv-map entries must look like field=Column, got: {pair}")
        field_name, column = pair.split("=", 1)
        mapping[field_name.strip()] = column.strip()
    return mapping


def dedupe_key(record: LocalRecord) -> tuple[str, str, str]:
    """Item-level exports repeat title/author/date for multiple copies; querying
    the APIs once per group is enough. Call numbers of all copies are merged."""
    return (normalize_title(record.title), normalize_author(record.author), record.year)


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    config = load_config(args.config)
    match_config = config.get("match", {})
    emit_threshold = args.threshold if args.threshold is not None else float(match_config.get("emit_threshold", 85))
    verified_threshold = float(match_config.get("verified_threshold", 95))
    max_per_source = int(match_config.get("max_candidates_per_source", 3))

    try:
        sources = build_sources([s for s in args.sources.split(",") if s.strip()], config)
    except ValueError as exc:
        raise SystemExit(str(exc))
    formats = {f.strip().lower() for f in args.formats.split(",") if f.strip()}

    # Group duplicate copies before querying
    groups: dict[tuple, tuple[LocalRecord, list[str]]] = {}
    skipped_format = 0
    for record in load_records(args.input, parse_csv_map(args.csv_map)):
        if formats and record.material_type.lower() not in formats:
            skipped_format += 1
            continue
        key = dedupe_key(record)
        if key in groups:
            if record.call_number:
                groups[key][1].append(record.call_number)
        else:
            groups[key] = (record, [record.call_number] if record.call_number else [])

    log.info(
        "%d unique title/author/date groups to match (%d rows skipped by --formats filter)",
        len(groups), skipped_format,
    )

    checkpoint = Checkpoint(str(args.output) + ".checkpoint.db")
    if args.resume:
        log.info("resuming: %d groups already processed", checkpoint.count())
    review = ReviewCsv(args.output, append=args.resume)

    processed = emitted = errors = 0
    try:
        for record, call_numbers in groups.values():
            if args.limit and processed >= args.limit:
                break
            if args.resume and checkpoint.is_processed(record.record_id):
                continue
            processed += 1

            verified_oclc: str | None = None
            record_had_error = False
            for name, source in sources.items():
                try:
                    candidates = source.search(record, verified_oclc=verified_oclc)
                except Exception as exc:
                    # Keep going: one flaky source shouldn't kill a day-long run
                    log.warning("source %s failed on %s (%r): %s", name, record.record_id, record.title[:60], exc)
                    errors += 1
                    record_had_error = True
                    continue
                scored = sorted(
                    ((score_candidate(record, c), c) for c in candidates),
                    key=lambda pair: pair[0],
                    reverse=True,
                )
                if name == "worldcat" and scored and scored[0][0] >= verified_threshold:
                    verified_oclc = scored[0][1].identifier or None
                kept = 0
                for score, candidate in scored:
                    if score < emit_threshold or kept >= max_per_source:
                        break
                    review.write_candidate(record, "; ".join(call_numbers), candidate, score)
                    emitted += 1
                    kept += 1
                log.debug("%s: %s -> %d candidates, %d kept", record.record_id, name, len(candidates), kept)

            # Only checkpoint fully-successful records so --resume retries failures
            if not record_had_error:
                checkpoint.mark_processed(record.record_id)
            if processed % 100 == 0:
                log.info("processed %d groups, emitted %d candidate rows (%d source errors)", processed, emitted, errors)
    except KeyboardInterrupt:
        log.warning("interrupted — progress saved; re-run with --resume to continue")
    finally:
        review.close()
        checkpoint.close()

    log.info("done: %d groups processed, %d candidate rows written to %s (%d source errors)", processed, emitted, args.output, errors)
    return 0


def main() -> None:
    sys.exit(run())
