#!/bin/bash
# Neo4j backup script

BACKUP_DIR="$HOME/kurultai/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="neo4j-backup-$DATE.dump"

echo "Starting Neo4j backup..."

# Create backup using neo4j-admin
/opt/homebrew/bin/neo4j-admin database dump neo4j --to="$BACKUP_DIR/$BACKUP_FILE" 2>/dev/null || \
/opt/homebrew/Cellar/neo4j/5.26.5/bin/neo4j-admin database dump neo4j --to="$BACKUP_DIR/$BACKUP_FILE" 2>/dev/null || \
echo "⚠️  neo4j-admin not found, skipping dump"

# Also backup critical files
tar czf "$BACKUP_DIR/config-backup-$DATE.tar.gz" -C "$HOME/kurultai/kublai-repo" .env openclaw.json 2>/dev/null

# Clean up old backups (keep 7 days)
find "$BACKUP_DIR" -name "neo4j-backup-*.dump" -mtime +7 -delete 2>/dev/null
find "$BACKUP_DIR" -name "config-backup-*.tar.gz" -mtime +7 -delete 2>/dev/null

echo "✅ Backup complete: $BACKUP_FILE"
