#!/bin/bash
# run_weekly.sh — Weekly USPTO bibliographic data update script
# Designed to run every Wednesday at 1 AM via cron
# Downloads from last Thursday to this Wednesday, processes into database

set -euo pipefail

WORKDIR="/data/BiblioData"
DB="${WORKDIR}/bibliographic_data.db"
LOGDIR="${WORKDIR}/logs"
LOGFILE="${WORKDIR}/biblio_mirror.log"

# Compute date range: last Thursday to this Wednesday
START_DATE=$(date -d "last Thursday" +%Y-%m-%d)
END_DATE=$(date +%Y-%m-%d)

mkdir -p "${LOGDIR}" "${WORKDIR}/downloads/publication" "${WORKDIR}/downloads/grant" \
          "${WORKDIR}/extracted/publication" "${WORKDIR}/extracted/grant"

echo "" >> "${LOGFILE}"
echo "========================================" >> "${LOGFILE}"
echo "$(date -Iseconds): Starting weekly run — ${START_DATE} to ${END_DATE}" >> "${LOGFILE}"
echo "========================================" >> "${LOGFILE}"

# Download publications
echo "$(date -Iseconds): Downloading publications..." >> "${LOGFILE}"
python3 "${WORKDIR}/download_uspto.py" \
    --dataset publication \
    --start-date "${START_DATE}" \
    --end-date "${END_DATE}" \
    --output-dir "${WORKDIR}" \
    --skip-existing \
    2>&1 | tee -a "${LOGFILE}"

# Download grants
echo "$(date -Iseconds): Downloading grants..." >> "${LOGFILE}"
python3 "${WORKDIR}/download_uspto.py" \
    --dataset grant \
    --start-date "${START_DATE}" \
    --end-date "${END_DATE}" \
    --output-dir "${WORKDIR}" \
    --skip-existing \
    2>&1 | tee -a "${LOGFILE}"

# Process publications
echo "$(date -Iseconds): Processing publications..." >> "${LOGFILE}"
python3 "${WORKDIR}/process_uspto.py" \
    --dataset publication \
    --db "${DB}" \
    2>&1 | tee -a "${LOGFILE}"

# Process grants
echo "$(date -Iseconds): Processing grants..." >> "${LOGFILE}"
python3 "${WORKDIR}/process_uspto.py" \
    --dataset grant \
    --db "${DB}" \
    2>&1 | tee -a "${LOGFILE}"

# Delete source data after successful processing
echo "$(date -Iseconds): Cleaning up source data..." >> "${LOGFILE}"
python3 "${WORKDIR}/process_uspto.py" \
    --dataset publication \
    --db "${DB}" \
    --delete-source-data \
    2>&1 | tee -a "${LOGFILE}"

python3 "${WORKDIR}/process_uspto.py" \
    --dataset grant \
    --db "${DB}" \
    --delete-source-data \
    2>&1 | tee -a "${LOGFILE}"

echo "$(date -Iseconds): Weekly run complete" >> "${LOGFILE}"
echo "Publications: $(sqlite3 "${DB}" 'SELECT COUNT(*) FROM publication;')" >> "${LOGFILE}"
echo "Grants: $(sqlite3 "${DB}" 'SELECT COUNT(*) FROM grant;')" >> "${LOGFILE}"