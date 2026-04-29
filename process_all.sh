#!/bin/bash
# process_all.sh — Initialize schema and process all unprocessed files
# Safe to re-run: init_db is idempotent, process_uspto skips already-processed files.

set -euo pipefail

WORKDIR="/data/USPTO/BiblioData"
DB="${WORKDIR}/bibliographic_data.db"

# Create schema (idempotent — all DDL is CREATE IF NOT EXISTS)
echo "=== $(date -Iseconds): Initializing database schema ==="
python3 "${WORKDIR}/init_db.py" --db "${DB}" 2>&1

echo "=== $(date -Iseconds): Processing publications ==="
python3 "${WORKDIR}/process_uspto.py" --dataset publication --db "${DB}" --delete-source-data --log-level INFO 2>&1

echo "=== $(date -Iseconds): Processing grants ==="
python3 "${WORKDIR}/process_uspto.py" --dataset grant --db "${DB}" --delete-source-data --log-level INFO 2>&1

echo "=== $(date -Iseconds): Done ==="
echo "Publications: $(sqlite3 "${DB}" 'SELECT COUNT(*) FROM publication;')"
echo "Grants: $(sqlite3 "${DB}" 'SELECT COUNT(*) FROM grant;')"
echo "Publications with abstracts: $(sqlite3 "${DB}" 'SELECT COUNT(*) FROM publication WHERE abstract_text IS NOT NULL;')"
echo "Grants with abstracts: $(sqlite3 "${DB}" 'SELECT COUNT(*) FROM grant WHERE abstract_text IS NOT NULL;')"
echo "Processed pub files: $(sqlite3 "${DB}" "SELECT COUNT(*) FROM processed_file WHERE dataset='publication';")"
echo "Processed grant files: $(sqlite3 "${DB}" "SELECT COUNT(*) FROM processed_file WHERE dataset='grant';")"