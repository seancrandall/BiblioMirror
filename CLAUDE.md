# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

USPTO Bibliographic Data Mirror — downloads patent grant and publication bibliographic data from the USPTO Open Data Portal (ODP) bulk API and loads it into a local SQLite database (`bibliographic_data.db`). The database is ~55 GB with millions of records.

## Commands

```bash
# Install dependencies
pip install lxml requests pytest

# Initialize database (idempotent)
python3 init_db.py [--db PATH]

# Download data (requires ODP_API_KEY env var or --api-key-file)
python3 download_uspto.py --dataset publication --start-date 2001-03-15 --end-date YYYY-MM-DD
python3 download_uspto.py --dataset grant --start-date 2002-01-01 --end-date YYYY-MM-DD

# Process XML into database
python3 process_uspto.py --dataset {publication,grant}
python3 process_uspto.py --dataset {publication,grant} --delete-source-data  # cleanup after import
python3 process_uspto.py --dataset {publication,grant} --file specific.xml  # single file

# Run tests
pytest test_uspto.py -v

# Weekly cron job (downloads from last Thursday to today, processes both datasets)
./run_weekly.sh

# Monitor bulk load progress (polls every 5 min)
./watch_progress.sh
```

## Architecture

Three-stage pipeline: **Download → Extract → Process**

1. **`download_uspto.py`** — Queries the USPTO ODP REST API (`APPBLXML` for publications, `PTBLXML` for grants), downloads zip files, extracts XML into `extracted/{dataset}/`. Uses rate limiting (default 3 rps) and retry logic for 429/5xx. Splits large date ranges into configurable batch-weeks.

2. **`process_uspto.py`** — The core. Does three things:
   - **XML splitting**: USPTO bulk files contain concatenated XML documents with individual `<?xml>` declarations. `split_xml_records()` splits on those boundaries and strips DOCTYPE lines.
   - **Parsing**: `parse_publication()` and `parse_grant()` walk the lxml tree, returning nested dicts. Grant parser handles additional elements (examiners, attorneys, references cited, grant term, classification search fields, etc.).
   - **Database loading**: `DatabaseLoader` inserts records with entity dedup via SHA256 hashes (`entity_hash` column on `person`, `assignee`, `examiner`, `attorney_agent_firm`). Uses in-memory caches to avoid repeated DB lookups. Processes files idempotently — checks `processed_file` table before re-importing. WAL journal mode for concurrent read access during bulk loads.

3. **`init_db.py`** — Creates the full schema (25+ tables, indexes, seed data). All DDL is `CREATE IF NOT EXISTS`, so it's safe to re-run.

## Key Design Decisions

- **Entity deduplication**: Shared `person` table for both inventors and applicants across publications and grants. Dedup is by `entity_hash` (SHA256 of normalized field concatenation). Same person appearing in multiple patents gets one row.
- **Idempotent processing**: The `processed_file` table tracks which XML files have been imported. Re-running `process_uspto.py` skips already-processed files.
- **Polymorphic classification tables**: `classification_ipcr`, `classification_cpc`, and `classification_national` use `source_type` ('publication'/'grant') + `source_id` to reference either main table, rather than separate tables per dataset.
- **Date ranges**: Publications available from 2001-03-15, grants from 2002-01-01.
- **API key**: `ODP_API_KEY` env var (preferred) or `--api-key-file` flag. No hardcoded path.

## Database

SQLite at `bibliographic_data.db` (~55 GB). WAL mode enabled. Key table groups:
- Main: `publication`, `grant`
- Entities: `person`, `assignee`, `examiner`, `attorney_agent_firm`
- Junctions: `{publication,grant}_{inventor,applicant,assignee}`, `grant_examiner`, `grant_attorney_agent`
- Classifications: `classification_{ipcr,cpc,national}`, `classification_locarno` (grants only)
- Grant-only: `reference_cited`, `grant_term`, `field_of_classification_search`
- Supporting: `priority_claim`, `pct_filing_data`, `pct_publishing_data`, `related_document`, `botanic`
- Metadata: `processed_file`, `processing_log`
- Lookup: `assignee_role_code`, `kind_code`

## Test Fixtures

`tests/fixtures/` contains 10-record XML subsets (`grants_10.xml`, `publications_10.xml`) for unit testing. Tests in `test_uspto.py` create a fresh in-memory DB per test via `init_db()` fixture.