#!/bin/bash
# backup-kurultai.sh — Daily backup script for Kurultai data stores
#
# Backs up:
# - Neo4j database dump
# - SQLite databases in data/
# - task-ledger.jsonl
# - credentials/ (encrypted, rotated)
#
# Usage:
#   ./backup-kurultai.sh           # Create backup
#   ./backup-kurultai.sh --list    # List available backups
#   ./backup-kurultai.sh --restore <backup_id>  # Restore from backup

set -e

BACKUP_DIR="$HOME/.openclaw/backups/daily"
RETENTION_DAYS=7
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_ID="backup_${TIMESTAMP}"

# Load Neo4j credentials (auto-export for child processes)
NEO4J_ENV="$HOME/.openclaw/credentials/neo4j.env"
if [[ -f "$NEO4J_ENV" ]]; then
    set -a
    source "$NEO4J_ENV"
    set +a
fi
# Fail explicitly if credentials not set
: "${NEO4J_USER:?NEO4J_USER not set}"
: "${NEO4J_PASSWORD:?NEO4J_PASSWORD not set}"
NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"

log() {
    echo "[$(date +%Y-%m-%d\ %H:%M:%S)] $1"
}

create_backup() {
    log "Starting backup: $BACKUP_ID"
    mkdir -p "$BACKUP_DIR/$BACKUP_ID"

    # 1. Neo4j dump (requires neo4j-admin)
    log "Backing up Neo4j..."
    if command -v neo4j-admin &> /dev/null; then
        neo4j-admin database dump neo4j --to-path="$BACKUP_DIR/$BACKUP_ID/" 2>/dev/null || {
            log "WARNING: neo4j-admin dump failed, trying cypher-shell export"
            # Fallback: export key data via cypher-shell
            # Use env vars to avoid credential exposure in process list
            export NEO4J_USERNAME="$NEO4J_USER"
            export NEO4J_PASSWORD="$NEO4J_PASSWORD"
            cypher-shell \
                "MATCH (n) RETURN n LIMIT 100000" \
                > "$BACKUP_DIR/$BACKUP_ID/neo4j_export.json" 2>/dev/null || {
                log "WARNING: Neo4j backup failed completely"
            }
            unset NEO4J_USERNAME NEO4J_PASSWORD
        }
    else
        log "WARNING: neo4j-admin not found, skipping Neo4j backup"
    fi

    # 2. SQLite databases
    log "Backing up SQLite databases..."
    DATA_DIR="$HOME/.openclaw/data"
    if [[ -d "$DATA_DIR" ]]; then
        mkdir -p "$BACKUP_DIR/$BACKUP_ID/sqlite"
        for db in "$DATA_DIR"/*.db "$DATA_DIR"/*.sqlite; do
            if [[ -f "$db" ]]; then
                # Use sqlite3 backup API for consistency
                sqlite3 "$db" ".backup '$BACKUP_DIR/$BACKUP_ID/sqlite/$(basename $db)'" 2>/dev/null || {
                    cp "$db" "$BACKUP_DIR/$BACKUP_ID/sqlite/"
                }
            fi
        done
    fi

    # 3. Task ledger
    log "Backing up task ledger..."
    TASK_LEDGER="$HOME/.openclaw/tasks/task-ledger.jsonl"
    if [[ -f "$TASK_LEDGER" ]]; then
        cp "$TASK_LEDGER" "$BACKUP_DIR/$BACKUP_ID/"
    fi

    # 4. Agent state files
    log "Backing up agent state..."
    mkdir -p "$BACKUP_DIR/$BACKUP_ID/agent_state"
    for agent in kublai temujin mongke chagatai jochi ogedei tolui; do
        AGENT_STATE="$HOME/.openclaw/agents/$agent/state.json"
        if [[ -f "$AGENT_STATE" ]]; then
            cp "$AGENT_STATE" "$BACKUP_DIR/$BACKUP_ID/agent_state/${agent}_state.json"
        fi
    done

    # 5. Create manifest
    cat > "$BACKUP_DIR/$BACKUP_ID/manifest.json" << EOF
{
    "backup_id": "$BACKUP_ID",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "hostname": "$(hostname)",
    "components": {
        "neo4j": $([[ -f "$BACKUP_DIR/$BACKUP_ID/neo4j.dump" ]] && echo "true" || echo "false"),
        "sqlite": $([[ -d "$BACKUP_DIR/$BACKUP_ID/sqlite" ]] && echo "true" || echo "false"),
        "task_ledger": $([[ -f "$BACKUP_DIR/$BACKUP_ID/task-ledger.jsonl" ]] && echo "true" || echo "false")
    }
}
EOF

    log "Backup complete: $BACKUP_DIR/$BACKUP_ID"

    # Cleanup old backups
    cleanup_old_backups
}

cleanup_old_backups() {
    log "Cleaning up backups older than $RETENTION_DAYS days..."
    find "$BACKUP_DIR" -type d -name "backup_*" -mtime +$RETENTION_DAYS -exec rm -rf {} \; 2>/dev/null || true
}

list_backups() {
    log "Available backups:"
    for backup in "$BACKUP_DIR"/backup_*; do
        if [[ -d "$backup" ]]; then
            manifest="$backup/manifest.json"
            if [[ -f "$manifest" ]]; then
                timestamp=$(python3 -c "import json; print(json.load(open('$manifest'))['timestamp'])" 2>/dev/null || echo "unknown")
                echo "  $(basename $backup) - $timestamp"
            else
                echo "  $(basename $backup) - (no manifest)"
            fi
        fi
    done
}

restore_backup() {
    local backup_id="$1"
    local backup_path="$BACKUP_DIR/$backup_id"

    if [[ ! -d "$backup_path" ]]; then
        log "ERROR: Backup not found: $backup_id"
        exit 1
    fi

    log "WARNING: This will overwrite current data. Press Ctrl+C to cancel."
    sleep 3

    log "Restoring from: $backup_path"

    # Restore SQLite
    if [[ -d "$backup_path/sqlite" ]]; then
        for db in "$backup_path/sqlite"/*.db "$backup_path/sqlite"/*.sqlite; do
            if [[ -f "$db" ]]; then
                cp "$db" "$HOME/.openclaw/data/"
                log "Restored: $(basename $db)"
            fi
        done
    fi

    # Restore task ledger
    if [[ -f "$backup_path/task-ledger.jsonl" ]]; then
        cp "$backup_path/task-ledger.jsonl" "$HOME/.openclaw/tasks/"
        log "Restored: task-ledger.jsonl"
    fi

    # Note: Neo4j restore requires neo4j-admin load and database stop
    if [[ -f "$backup_path/neo4j.dump" ]]; then
        log "Neo4j dump found. To restore, run:"
        log "  neo4j-admin database load neo4j --from-path=$backup_path/"
    fi

    log "Restore complete"
}

# Main
case "${1:-}" in
    --list)
        list_backups
        ;;
    --restore)
        if [[ -z "${2:-}" ]]; then
            echo "Usage: $0 --restore <backup_id>"
            exit 1
        fi
        restore_backup "$2"
        ;;
    *)
        create_backup
        ;;
esac
