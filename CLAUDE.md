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

# Download + process in streaming mode (recommended: minimizes disk usage)
# Each zip is downloaded, extracted, processed, and cleaned up before moving to the next.
python3 download_uspto.py --dataset publication --start-date 2001-03-15 --end-date YYYY-MM-DD --process --db bibliographic_data.db
python3 download_uspto.py --dataset grant --start-date 2002-01-01 --end-date YYYY-MM-DD --process --db bibliographic_data.db

# Download data only (no processing — leaves zips and XMLs on disk)
python3 download_uspto.py --dataset publication --start-date 2001-03-15 --end-date YYYY-MM-DD

# Process existing XML into database (standalone, for already-downloaded data)
python3 process_uspto.py --dataset {publication,grant}
python3 process_uspto.py --dataset {publication,grant} --delete-source-data  # cleanup after import
python3 process_uspto.py --dataset {publication,grant} --file specific.xml  # single file

# Full-corpus load (streaming mode — uses --process to interleave download and processing)
./process_all.sh

# Weekly cron job (streaming mode — downloads from last Thursday to today)
./run_weekly.sh

# Run tests
pytest test_uspto.py -v

# Monitor bulk load progress (polls every 5 min)
./watch_progress.sh
```

## Architecture

Two modes: **streaming** (recommended) and **separate** (legacy).

### Streaming mode (`--process` flag)

With `--process --db`, `download_uspto.py` downloads one zip at a time, extracts its XMLs, deletes the zip, processes each XML into the database, then deletes the XML before moving to the next zip. This keeps peak disk usage at roughly one zip + one XML + database size (vs. 3x for the legacy mode).

1. **`download_uspto.py --process`** — For each zip: download → extract → delete zip → process XML into DB → delete XML. Uses `process_file()` from `process_uspto.py` internally. Checks `processed_file` table for idempotency — re-runs skip already-processed files and clean up leftover disk artifacts.

2. **`process_all.sh` / `run_weekly.sh`** — Shell scripts that use `--process --db` mode. `process_all.sh` runs a full corpus load; `run_weekly.sh` runs incremental weekly updates.

### Separate mode (legacy)

Without `--process`, `download_uspto.py` downloads all zips and extracts all XMLs, then `process_uspto.py` processes them in a separate step. This requires enough disk for all zips + all XMLs + the database simultaneously (~150GB for full corpus). Use `--delete-source-data` to clean up after processing.

### Core modules

- **`download_uspto.py`** — Queries the USPTO ODP REST API (`APPBLXML` for publications, `PTBLXML` for grants), downloads zip files, extracts XML. With `--process`, also processes each file into the database immediately. Uses rate limiting (default 3 rps) and retry logic for 429/5xx. Splits large date ranges into configurable batch-weeks.

- **`process_uspto.py`** — Parses XML and loads into SQLite. `process_file()` is the entry point used by streaming mode. Standalone CLI mode processes all unprocessed XMLs in `extracted/{dataset}/`. Features: XML splitting, entity dedup via SHA256 hashes, idempotent processing via `processed_file` table, `--delete-source-data` for cleanup.

- **`init_db.py`** — Creates the full schema (25+ tables, indexes, seed data). All DDL is `CREATE IF NOT EXISTS`, so it's safe to re-run.

## Key Design Decisions

- **Streaming mode (recommended)**: With `--process --db`, each zip is processed and cleaned up before downloading the next. Peak disk usage is ~one zip + one XML + database size (~55GB for full corpus vs. ~155GB in legacy mode).
- **Entity deduplication**: Shared `person` table for both inventors and applicants across publications and grants. Dedup is by `entity_hash` (SHA256 of normalized field concatenation). Same person appearing in multiple patents gets one row.
- **Idempotent processing**: The `processed_file` table tracks which XML files have been imported. Re-running either mode skips already-processed files. In streaming mode, the `processed_file` check happens before downloading, so interrupted runs resume cleanly.
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