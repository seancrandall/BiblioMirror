# USPTO Bibliographic Data Mirror

Mirrors USPTO patent grant and publication bibliographic data from the [Open Data Portal](https://developer.uspto.gov/data) into a local SQLite database.

## Quick Start

```bash
# 1. Set your API key
export ODP_API_KEY="your-api-key-here"

# 2. Initialize the database
python3 init_db.py

# 3. Download data (publications from 2001, grants from 2002)
python3 download_uspto.py --dataset publication --start-date 2001-03-15 --end-date 2026-04-25
python3 download_uspto.py --dataset grant --start-date 2002-01-01 --end-date 2026-04-25

# 4. Process into database
python3 process_uspto.py --dataset publication
python3 process_uspto.py --dataset grant

# 5. (Optional) Delete source files after verified import
python3 process_uspto.py --dataset publication --delete-source-data
python3 process_uspto.py --dataset grant --delete-source-data
```

## API Key

The USPTO ODP API requires an API key. Get one at [developer.uspto.gov](https://developer.uspto.gov/).

Three ways to provide it, in priority order:

1. **Environment variable**: `export ODP_API_KEY="your-key"`
2. **Command-line flag**: `--api-key-file /path/to/keyfile`
3. **Error**: If neither is provided, the script exits with instructions.

## Scripts

### `init_db.py`

Creates the SQLite database (`bibliographic_data.db`) with all tables, indexes, and seed data. Idempotent — safe to run multiple times.

```bash
python3 init_db.py [--db PATH]
```

### `download_uspto.py`

Downloads zip files from the USPTO ODP API and extracts the XML files.

```bash
python3 download_uspto.py \
    --dataset {publication,grant} \
    --start-date YYYY-MM-DD \
    --end-date YYYY-MM-DD \
    [--output-dir DIR] \
    [--api-key-file PATH] \
    [--batch-weeks N] \
    [--skip-existing] \
    [--rps N] \
    [--log-level {DEBUG,INFO,WARNING,ERROR}]
```

- `--dataset publication` uses the APPBLXML endpoint (applications/pre-grant publications)
- `--dataset grant` uses the PTBLXML endpoint (issued patents)
- `--batch-weeks` splits large date ranges into chunks (default: 10 weeks)
- `--skip-existing` skips already-downloaded files (default: enabled)
- `--rps` controls request rate (default: 3 requests/second)

### `process_uspto.py`

Parses XML files and inserts into the database. Skips already-processed files.

```bash
python3 process_uspto.py \
    --dataset {publication,grant} \
    [--input-dir DIR] \
    [--db PATH] \
    [--delete-source-data] \
    [--file FILE ...] \
    [--log-level {DEBUG,INFO,WARNING,ERROR}]
```

- `--delete-source-data` removes source XML and zip files after confirmed import
- `--file` processes specific files instead of scanning the input directory
- If no `--file` is given, processes all unprocessed XML files in the input directory

### `run_weekly.sh`

Wrapper script for the cron job. Downloads from last Thursday to today (Wednesday), processes both datasets, and deletes source files.

```bash
./run_weekly.sh
```

### `watch_progress.sh`

Monitors the bulk load. Polls every 5 minutes and displays record counts, file progress, and whether downloads are still running.

```bash
./watch_progress.sh
```

### `test_uspto.py`

Test suite (requires `pytest`):

```bash
pytest test_uspto.py -v
```

## Cron Setup

To run the weekly update automatically every Wednesday at 1 AM:

```bash
sudo cp /tmp/uspto-biblio-mirror /etc/cron.d/uspto-biblio-mirror
```

Make sure `ODP_API_KEY` is set in the environment (e.g., in `~/.bashrc` or a `.env` file sourced by the script).

## Database Schema

The database (`bibliographic_data.db`) uses a shared `person` table for both inventors and applicants, with role-specific attributes on the junction tables. Key tables:

| Table | Purpose |
|-------|---------|
| `publication` | Pre-grant publications (A1, A2, P1) |
| `grant` | Issued patents (B1, B2, S1, E1, P2, P3) |
| `person` | Shared entity for inventors and applicants |
| `assignee` | Assignees with role codes |
| `examiner` | Primary and assistant examiners |
| `attorney_agent_firm` | Attorneys, agents, and firms |
| `classification_ipcr` | IPCR classifications |
| `classification_cpc` | CPC classifications |
| `reference_cited` | Patent and NPL citations (grants only) |
| `priority_claim` | Domestic and foreign priority claims |
| `related_document` | Continuations, divisions, provisionals |
| `pct_filing_data` | PCT/regional filing data |
| `processed_file` | Tracks which XML files have been imported |

Plus junction tables (`publication_inventor`, `grant_examiner`, etc.) and lookup tables (`assignee_role_code`, `kind_code`).

## Directory Structure

```
BiblioData/
├── bibliographic_data.db    # SQLite database
├── biblio_mirror.log       # Continuous log
├── init_db.py               # Database initialization
├── download_uspto.py        # Download from USPTO ODP
├── process_uspto.py         # Parse XML → SQLite
├── run_weekly.sh             # Cron wrapper
├── watch_progress.sh         # Progress monitor
├── test_uspto.py             # Test suite
├── design_plan.md            # Detailed design checklist
├── downloads/
│   ├── publication/          # Downloaded zip files
│   └── grant/
├── extracted/
│   ├── publication/          # Extracted XML files
│   └── grant/
├── logs/
└── tests/
    └── fixtures/             # 10-record test subsets
```

## Dependencies

- Python 3.8+
- `lxml` — XML parsing
- `requests` — HTTP client for USPTO API
- `pytest` — for running the test suite

```bash
pip install lxml requests pytest
```

## Date Ranges

- **Publications**: Available from March 15, 2001 (APPBLXML dataset)
- **Grants**: Available from January 1, 2002 (PTBLXML dataset)