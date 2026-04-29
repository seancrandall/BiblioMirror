#!/bin/bash
# run_weekly.sh — Weekly USPTO bibliographic data update script
# Designed to run every Wednesday at 1 AM via cron
# Downloads from last Thursday to this Wednesday, processes into database

set -euo pipefail

WORKDIR="/data/USPTO/BiblioData"
DB="${WORKDIR}/bibliographic_data.db"
LOGDIR="${WORKDIR}/logs"
LOGFILE="${WORKDIR}/biblio_mirror.log"

# Compute date range: most recent Thursday to today
# USPTO publications are released Thursday, grants Tuesday.
# GNU date's "last Thursday" means previous-week Thursday on Thu-Sat,
# which gives wrong results. Use arithmetic instead.
DOW=$(date +%u)  # 1=Mon ... 7=Sun
# Days since Thursday: Thu=0, Fri=1, Sat=2, Sun=3, Mon=4, Tue=5, Wed=6
DAYS_SINCE_THU=$(( (DOW + 3) % 7 ))
START_DATE=$(date -d "${DAYS_SINCE_THU} days ago" +%Y-%m-%d)
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

# Process publications (delete source data after successful import)
echo "$(date -Iseconds): Processing publications..." >> "${LOGFILE}"
python3 "${WORKDIR}/process_uspto.py" \
    --dataset publication \
    --db "${DB}" \
    --delete-source-data \
    2>&1 | tee -a "${LOGFILE}"

# Process grants (delete source data after successful import)
echo "$(date -Iseconds): Processing grants..." >> "${LOGFILE}"
python3 "${WORKDIR}/process_uspto.py" \
    --dataset grant \
    --db "${DB}" \
    --delete-source-data \
    2>&1 | tee -a "${LOGFILE}"

echo "$(date -Iseconds): Weekly run complete" >> "${LOGFILE}"
echo "Publications: $(sqlite3 "${DB}" 'SELECT COUNT(*) FROM publication;')" >> "${LOGFILE}"
echo "Grants: $(sqlite3 "${DB}" 'SELECT COUNT(*) FROM grant;')" >> "${LOGFILE}"
