#!/bin/bash
# run_weekly.sh — Weekly USPTO bibliographic data update script (streaming mode)
# Designed to run every Wednesday at 1 AM via cron
# Downloads from last Thursday to today, processes each file one-at-a-time

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
echo "$(date -Iseconds): Starting weekly run (streaming) — ${START_DATE} to ${END_DATE}" >> "${LOGFILE}"
echo "========================================" >> "${LOGFILE}"

# Ensure DB schema exists (idempotent)
python3 "${WORKDIR}/init_db.py" --db "${DB}" 2>&1 | tee -a "${LOGFILE}"

# Download + process publications (streaming)
echo "$(date -Iseconds): Downloading + processing publications..." >> "${LOGFILE}"
python3 "${WORKDIR}/download_uspto.py" \
    --dataset publication \
    --start-date "${START_DATE}" \
    --end-date "${END_DATE}" \
    --output-dir "${WORKDIR}" \
    --skip-existing \
    --process \
    --db "${DB}" \
    2>&1 | tee -a "${LOGFILE}"

# Download + process grants (streaming)
echo "$(date -Iseconds): Downloading + processing grants..." >> "${LOGFILE}"
python3 "${WORKDIR}/download_uspto.py" \
    --dataset grant \
    --start-date "${START_DATE}" \
    --end-date "${END_DATE}" \
    --output-dir "${WORKDIR}" \
    --skip-existing \
    --process \
    --db "${DB}" \
    2>&1 | tee -a "${LOGFILE}"

echo "$(date -Iseconds): Weekly run complete (streaming)" >> "${LOGFILE}"
echo "Publications: $(sqlite3 "${DB}" 'SELECT COUNT(*) FROM publication;')" >> "${LOGFILE}"
echo "Grants: $(sqlite3 "${DB}" 'SELECT COUNT(*) FROM grant;')" >> "${LOGFILE}"

# Calculate embeddings if requested
if [ "$EMBEDDINGS" = true ]; then
    echo "$(date -Iseconds): Calculating abstract embeddings..." >> "${LOGFILE}"
    python3 "${WORKDIR}/calculate_embeddings.py" --db "${DB}" 2>&1 | tee -a "${LOGFILE}"
fi