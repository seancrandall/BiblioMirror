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
./run_weekly.sh [--embeddings]
```

- `--embeddings` — after downloading and processing, calculate vector embeddings for any new abstracts

### `watch_progress.sh`

Monitors the bulk load. Polls every 5 minutes and displays record counts, file progress, and whether downloads are still running.

```bash
./watch_progress.sh
```

### `calculate_embeddings.py`

Calculates vector embeddings for patent abstracts using a local ollama embedding model. Only processes records that have an abstract but no embedding yet — idempotent and resumable.

```bash
python3 calculate_embeddings.py \
    [--db PATH] \
    [--dataset {publication,grant,both}] \
    [--model MODEL] \
    [--ollama-url URL] \
    [--batch-size N] \
    [--limit N] \
    [--log-level {DEBUG,INFO,WARNING,ERROR}]
```

- `--dataset` — which dataset to process (default: `both`)
- `--model` — ollama embedding model name (default: `nomic-embed-text`)
- `--ollama-url` — ollama API base URL (default: `http://localhost:11434`)
- `--batch-size` — number of abstracts per API call (default: 50)
- `--limit` — max records per dataset, 0 for unlimited (default: 0)

**Prerequisites**: ollama must be running with the embedding model pulled:
```bash
ollama pull nomic-embed-text
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

## Embeddings

Abstract embeddings enable semantic similarity search across patents. The `calculate_embeddings.py` module uses a local ollama embedding model (`nomic-embed-text`, 768 dimensions) to compute vector embeddings of patent abstracts and store them as BLOBs in the database.

**Quick start**:
```bash
# Ensure ollama is running with the model
ollama pull nomic-embed-text

# Calculate embeddings for all records missing them
python3 calculate_embeddings.py --db bibliographic_data.db

# Or include embeddings in a full-corpus or weekly run
./process_all.sh --embeddings
./run_weekly.sh --embeddings
```

The weekly cron job includes `--embeddings` by default. Design patents (kind code S1) have no abstracts and are skipped automatically.

## Database Schema

The database (`bibliographic_data.db`) uses a shared `person` table for both inventors and applicants, with role-specific attributes on the junction tables. Key tables:

| Table | Purpose |
|-------|---------|
| `publication` | Pre-grant publications (A1, A2, P1) — includes `abstract_embedding` BLOB |
| `grant` | Issued patents (B1, B2, S1, E1, P2, P3) — includes `abstract_embedding` BLOB |
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
├── calculate_embeddings.py  # Abstract → vector embeddings via ollama
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
- `requests` — HTTP client for USPTO API and ollama
- `pytest` — for running the test suite

```bash
pip install lxml requests pytest
```

## Date Ranges

- **Publications**: Available from March 15, 2001 (APPBLXML dataset)
- **Grants**: Available from January 1, 2002 (PTBLXML dataset)