#!/bin/bash
# process_all.sh — Full-corpus download + process (streaming mode)
# Downloads the entire USPTO bibliographic dataset, processing each file
# one-at-a-time to minimize disk usage.
# Safe to re-run: skips already-processed files via processed_file table.

set -euo pipefail

EMBEDDINGS=false
for arg in "$@"; do
    case "$arg" in
        --embeddings) EMBEDDINGS=true ;;
    esac
done

WORKDIR="/data/USPTO/BiblioData"
DB="${WORKDIR}/bibliographic_data.db"
LOGDIR="${WORKDIR}/logs"
LOGFILE="${WORKDIR}/biblio_mirror.log"
TODAY=$(date +%Y-%m-%d)

mkdir -p "${LOGDIR}" "${WORKDIR}/downloads/publication" "${WORKDIR}/downloads/grant" \
          "${WORKDIR}/extracted/publication" "${WORKDIR}/extracted/grant"

echo "" >> "${LOGFILE}"
echo "========================================" >> "${LOGFILE}"
echo "$(date -Iseconds): Starting full-corpus run (streaming)" >> "${LOGFILE}"
echo "========================================" >> "${LOGFILE}"

# Create schema (idempotent — all DDL is CREATE IF NOT EXISTS)
echo "=== $(date -Iseconds): Initializing database schema ==="
echo "$(date -Iseconds): Initializing database schema" >> "${LOGFILE}"
python3 "${WORKDIR}/init_db.py" --db "${DB}" 2>&1 | tee -a "${LOGFILE}"

# Download + process publications (streaming: one zip at a time)
echo "=== $(date -Iseconds): Downloading + processing publications (2001-03-15 to ${TODAY}) ==="
echo "$(date -Iseconds): Downloading + processing publications" >> "${LOGFILE}"
python3 "${WORKDIR}/download_uspto.py" \
    --dataset publication \
    --start-date 2001-03-15 \
    --end-date "${TODAY}" \
    --output-dir "${WORKDIR}" \
    --skip-existing \
    --process \
    --db "${DB}" \
    2>&1 | tee -a "${LOGFILE}"

# Download + process grants (streaming: one zip at a time)
echo "=== $(date -Iseconds): Downloading + processing grants (2002-01-01 to ${TODAY}) ==="
echo "$(date -Iseconds): Downloading + processing grants" >> "${LOGFILE}"
python3 "${WORKDIR}/download_uspto.py" \
    --dataset grant \
    --start-date 2002-01-01 \
    --end-date "${TODAY}" \
    --output-dir "${WORKDIR}" \
    --skip-existing \
    --process \
    --db "${DB}" \
    2>&1 | tee -a "${LOGFILE}"

echo "=== $(date -Iseconds): Done ==="
echo "$(date -Iseconds): Full-corpus run complete (streaming)" >> "${LOGFILE}"
echo "Publications: $(sqlite3 "${DB}" 'SELECT COUNT(*) FROM publication;')"
echo "Grants: $(sqlite3 "${DB}" 'SELECT COUNT(*) FROM grant;')"
echo "Publications with abstracts: $(sqlite3 "${DB}" 'SELECT COUNT(*) FROM publication WHERE abstract_text IS NOT NULL;')"
echo "Grants with abstracts: $(sqlite3 "${DB}" 'SELECT COUNT(*) FROM grant WHERE abstract_text IS NOT NULL;')"
echo "Processed pub files: $(sqlite3 "${DB}" "SELECT COUNT(*) FROM processed_file WHERE dataset='publication';")"
echo "Processed grant files: $(sqlite3 "${DB}" "SELECT COUNT(*) FROM processed_file WHERE dataset='grant';")"

# Calculate embeddings if requested
if [ "$EMBEDDINGS" = true ]; then
    echo "=== $(date -Iseconds): Calculating abstract embeddings ==="
    echo "$(date -Iseconds): Calculating abstract embeddings" >> "${LOGFILE}"
    python3 "${WORKDIR}/calculate_embeddings.py" --db "${DB}" 2>&1 | tee -a "${LOGFILE}"
fi