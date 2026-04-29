#!/bin/bash
# watch_progress.sh — Monitor the bulk load progress
# Run: ./watch_progress.sh
# Polls every 5 minutes and shows record counts

DB="/data/USPTO/BiblioData/bibliographic_data.db"

while true; do
    PUBS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM publication;" 2>/dev/null || echo "DB locked")
    GRANTS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM grant;" 2>/dev/null || echo "DB locked")
    PROC_PUB=$(sqlite3 "$DB" "SELECT COUNT(*) FROM processed_file WHERE dataset='publication';" 2>/dev/null || echo "?")
    PROC_GRANT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM processed_file WHERE dataset='grant';" 2>/dev/null || echo "?")
    EXTRACTED_PUB=$(ls /data/BiblioData/extracted/publication/ipab*.xml 2>/dev/null | wc -l)
    EXTRACTED_GRANT=$(ls /data/BiblioData/extracted/grant/ipgb*.xml 2>/dev/null | wc -l)
    DOWNLOADED_PUB=$(ls /data/BiblioData/downloads/publication/ipab*.zip 2>/dev/null | wc -l)
    DOWNLOADED_GRANT=$(ls /data/BiblioData/downloads/grant/ipgb*.zip 2>/dev/null | wc -l)
    PERSONS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM person;" 2>/dev/null || echo "?")
    DB_SIZE=$(du -sh "$DB" 2>/dev/null | cut -f1 || echo "?")
    DL_RUNNING=$(ps aux | grep -c '[d]ownload_uspto' 2>/dev/null || echo "?")

    echo ""
    echo "=========================================="
    echo "  $(date '+%Y-%m-%d %H:%M:%S') — Bulk Load Progress"
    echo "=========================================="
    echo "  Publications:     ${PUBS} (${PROC_PUB}/${EXTRACTED_PUB} files processed)"
    echo "  Grants:           ${GRANTS} (${PROC_GRANT}/${EXTRACTED_GRANT} files processed)"
    echo "  Unique persons:   ${PERSONS}"
    echo "  ---"
    echo "  Pub zips:         ${DOWNLOADED_PUB} downloaded"
    echo "  Grant zips:       ${DOWNLOADED_GRANT} downloaded"
    echo "  ---"
    echo "  DB size:          ${DB_SIZE}"
    echo "  Download procs:   ${DL_RUNNING} running"
    echo "=========================================="

    sleep 300  # 5 minutes
done
