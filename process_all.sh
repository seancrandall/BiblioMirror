#!/bin/bash
# process_all.sh — Process all unprocessed files for both datasets
# Run this periodically while downloads are in progress

set -euo pipefail

WORKDIR="/data/BiblioData"
DB="${WORKDIR}/bibliographic_data.db"

echo "=== $(date -Iseconds): Processing publications ==="
python3 "${WORKDIR}/process_uspto.py" --dataset publication --db "${DB}" --log-level INFO 2>&1

echo "=== $(date -Iseconds): Processing grants ==="
python3 "${WORKDIR}/process_uspto.py" --dataset grant --db "${DB}" --log-level INFO 2>&1

echo "=== $(date -Iseconds): Done ==="
echo "Publications: $(sqlite3 "${DB}" 'SELECT COUNT(*) FROM publication;')"
echo "Grants: $(sqlite3 "${DB}" 'SELECT COUNT(*) FROM grant;')"
echo "Processed pub files: $(sqlite3 "${DB}" "SELECT COUNT(*) FROM processed_file WHERE dataset='publication';")"
echo "Processed grant files: $(sqlite3 "${DB}" "SELECT COUNT(*) FROM processed_file WHERE dataset='grant';")"