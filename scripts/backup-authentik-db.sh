#!/bin/bash
# Authentik PostgreSQL Backup Script
# Runs via Railway cron or scheduled task

set -euo pipefail

# Configuration
BACKUP_BUCKET="${R2_BUCKET:-authentik-backups}"
BACKUP_PREFIX="${R2_PREFIX:-authentik/db}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
DB_HOST="${AUTHENTIK_POSTGRESQL__HOST:-authentik-db.railway.internal}"
DB_NAME="${AUTHENTIK_POSTGRESQL__NAME:-authentik}"
DB_USER="${AUTHENTIK_POSTGRESQL__USER:-postgres}"
DB_PASSWORD="${AUTHENTIK_POSTGRESQL__PASSWORD:-}"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="authentik_backup_${DATE}.sql.gz"

# Check required environment variables
if [ -z "$DB_PASSWORD" ]; then
    echo "ERROR: AUTHENTIK_POSTGRESQL__PASSWORD is required"
    exit 1
fi

if [ -z "$R2_ACCESS_KEY_ID" ] || [ -z "$R2_SECRET_ACCESS_KEY" ]; then
    echo "WARNING: R2 credentials not set, backup will be stored locally only"
    UPLOAD_TO_R2=false
else
    UPLOAD_TO_R2=true
fi

echo "Starting Authentik database backup..."
echo "Database: $DB_NAME on $DB_HOST"
echo "Backup file: $BACKUP_FILE"

# Create backup using pg_dump
export PGPASSWORD="$DB_PASSWORD"
pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" --clean --if-exists | gzip > "/tmp/$BACKUP_FILE"

BACKUP_SIZE=$(stat -f%z "/tmp/$BACKUP_FILE" 2>/dev/null || stat -c%s "/tmp/$BACKUP_FILE" 2>/dev/null || echo "unknown")
echo "Backup completed: $BACKUP_FILE ($BACKUP_SIZE bytes)"

# Upload to Cloudflare R2 (S3-compatible)
if [ "$UPLOAD_TO_R2" = true ]; then
    echo "Uploading to R2..."
    aws s3 cp "/tmp/$BACKUP_FILE" "s3://$BACKUP_BUCKET/$BACKUP_PREFIX/$BACKUP_FILE" \
        --endpoint-url "${R2_ENDPOINT:-https://<account-id>.r2.cloudflarestorage.com}" \
        --region auto
    echo "Upload completed"

    # Clean up old backups (retention policy)
    echo "Cleaning up backups older than $RETENTION_DAYS days..."
    aws s3 ls "s3://$BACKUP_BUCKET/$BACKUP_PREFIX/" --endpoint-url "${R2_ENDPOINT}" --region auto | \
        awk '{print $4}' | \
        while read -r file; do
            file_date=$(echo "$file" | grep -oP '\d{8}_\d{6}' || true)
            if [ -n "$file_date" ]; then
                file_ts=$(date -d "${file_date:0:8} ${file_date:9:2}:${file_date:11:2}:${file_date:13:2}" +%s 2>/dev/null || date -j -f "%Y%m%d_%H%M%S" "$file_date" +%s 2>/dev/null || echo 0)
                cutoff_ts=$(date -d "$RETENTION_DAYS days ago" +%s 2>/dev/null || date -v-${RETENTION_DAYS}d +%s 2>/dev/null)
                if [ "$file_ts" -lt "$cutoff_ts" ]; then
                    echo "Deleting old backup: $file"
                    aws s3 rm "s3://$BACKUP_BUCKET/$BACKUP_PREFIX/$file" --endpoint-url "${R2_ENDPOINT}" --region auto
                fi
            fi
        done
fi

# Clean up local file
rm -f "/tmp/$BACKUP_FILE"

echo "Backup process completed successfully"

# Health check ping (optional)
if [ -n "$HEALTHCHECK_URL" ]; then
    curl -fsS -m 10 --retry 5 "$HEALTHCHECK_URL" || true
fi
