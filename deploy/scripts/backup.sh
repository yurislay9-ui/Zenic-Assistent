#!/bin/bash
# ============================================================
#  ZENIC-AGENTS v16 - Database Backup Script
#  Phase 3: VPS Deploy
#
#  Creates timestamped PostgreSQL backup with compression.
#  Designed to run as a Docker compose service or cron job.
#
#  Usage:
#    docker compose run --rm backup
#    # Or manually:
#    ./deploy/scripts/backup.sh
# ============================================================

set -euo pipefail

BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/zenic_${TIMESTAMP}.sql.gz"

# Retention policy: keep last 30 days
RETENTION_DAYS=30

echo "=== ZENIC-AGENTS Backup ==="
echo "Timestamp: ${TIMESTAMP}"
echo "Target: ${BACKUP_FILE}"

# Ensure backup directory exists
mkdir -p "${BACKUP_DIR}"

# Create compressed backup
echo "Creating backup..."
pg_dump \
    --host="${PGHOST:-db}" \
    --username="${PGUSER:-zenic}" \
    --dbname="${PGDATABASE:-zenic_db}" \
    --format=plain \
    --no-owner \
    --no-acl \
    | gzip > "${BACKUP_FILE}"

BACKUP_SIZE=$(du -sh "${BACKUP_FILE}" | cut -f1)
echo "Backup complete: ${BACKUP_FILE} (${BACKUP_SIZE})"

# Cleanup old backups
echo "Cleaning up backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name "zenic_*.sql.gz" -mtime +${RETENTION_DAYS} -delete 2>/dev/null || true

REMAINING=$(ls -1 "${BACKUP_DIR}"/zenic_*.sql.gz 2>/dev/null | wc -l)
echo "Remaining backups: ${REMAINING}"
echo "=== Backup Complete ==="
