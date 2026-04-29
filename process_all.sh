#!/bin/bash
# process_all.sh — Full-corpus download + process
# Downloads the entire USPTO bibliographic dataset from day one, then processes into SQLite.
# Safe to re-run: downloads skip existing files, processing skips already-processed files.

set -euo pipefail

WORKDIR="/data/USPTO/BiblioData"
DB="${WORKDIR}/bibliographic_data.db"
LOGDIR="${WORKDIR}/logs"
LOGFILE="${WORKDIR}/biblio_mirror.log"
TODAY=$(date +%Y-%m-%d)

mkdir -p "${LOGDIR}" "${WORKDIR}/downloads/publication" "${WORKDIR}/downloads/grant" \
          "${WORKDIR}/extracted/publication" "${WORKDIR}/extracted/grant"

echo "" >> "${LOGFILE}"
echo "========================================" >> "${LOGFILE}"
echo "$(date -Iseconds): Starting full-corpus run" >> "${LOGFILE}"
echo "========================================" >> "${LOGFILE}"

# Create schema (idempotent — all DDL is CREATE IF NOT EXISTS)
echo "=== $(date -Iseconds): Initializing database schema ==="
echo "$(date -Iseconds): Initializing database schema" >> "${LOGFILE}"
python3 "${WORKDIR}/init_db.py" --db "${DB}" 2>&1 | tee -a "${LOGFILE}"

# Download full publication corpus (2001-03-15 to today)
echo "=== $(date -Iseconds): Downloading publications (2001-03-15 to ${TODAY}) ==="
echo "$(date -Iseconds): Downloading publications" >> "${LOGFILE}"
python3 "${WORKDIR}/download_uspto.py" \
    --dataset publication \
    --start-date 2001-03-15 \
    --end-date "${TODAY}" \
    --output-dir "${WORKDIR}" \
    --skip-existing \
    2>&1 | tee -a "${LOGFILE}"

# Download full grant corpus (2002-01-01 to today)
echo "=== $(date -Iseconds): Downloading grants (2002-01-01 to ${TODAY}) ==="
echo "$(date -Iseconds): Downloading grants" >> "${LOGFILE}"
python3 "${WORKDIR}/download_uspto.py" \
    --dataset grant \
    --start-date 2002-01-01 \
    --end-date "${TODAY}" \
    --output-dir "${WORKDIR}" \
    --skip-existing \
    2>&1 | tee -a "${LOGFILE}"

# Process publications
echo "=== $(date -Iseconds): Processing publications ==="
echo "$(date -Iseconds): Processing publications" >> "${LOGFILE}"
python3 "${WORKDIR}/process_uspto.py" --dataset publication --db "${DB}" --delete-source-data --log-level INFO 2>&1 | tee -a "${LOGFILE}"

# Process grants
echo "=== $(date -Iseconds): Processing grants ==="
echo "$(date -Iseconds): Processing grants" >> "${LOGFILE}"
python3 "${WORKDIR}/process_uspto.py" --dataset grant --db "${DB}" --delete-source-data --log-level INFO 2>&1 | tee -a "${LOGFILE}"

echo "=== $(date -Iseconds): Done ==="
echo "$(date -Iseconds): Full-corpus run complete" >> "${LOGFILE}"
echo "Publications: $(sqlite3 "${DB}" 'SELECT COUNT(*) FROM publication;')"
echo "Grants: $(sqlite3 "${DB}" 'SELECT COUNT(*) FROM grant;')"
echo "Publications with abstracts: $(sqlite3 "${DB}" 'SELECT COUNT(*) FROM publication WHERE abstract_text IS NOT NULL;')"
echo "Grants with abstracts: $(sqlite3 "${DB}" 'SELECT COUNT(*) FROM grant WHERE abstract_text IS NOT NULL;')"
echo "Processed pub files: $(sqlite3 "${DB}" "SELECT COUNT(*) FROM processed_file WHERE dataset='publication';")"
echo "Processed grant files: $(sqlite3 "${DB}" "SELECT COUNT(*) FROM processed_file WHERE dataset='grant';')"