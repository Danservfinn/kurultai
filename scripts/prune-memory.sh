#!/bin/bash
# Weekly Memory Pruning Script
# 
# Inspired by Cognee's auto-pruning:
# - Decay stale edges (not accessed in 14 days)
# - Prune orphaned nodes (no connections, older than 30 days)
# - Archive old memory files (older than 30 days)
#
# Run via cron: 0 3 * * 0 (Sunday at 3 AM)

set -e

echo "=== Memory Pruning — $(date) ==="
echo ""

# Configuration
NEO4J_URI="bolt://localhost:7687"
MEMORY_DIR="/Users/kublai/.openclaw/agents/main/memory"
ARCHIVE_DIR="/Users/kublai/.openclaw/agents/main/memory/archive"
DAYS_BEFORE_DECAY=14
DAYS_BEFORE_PRUNE=30

# Create archive directory if needed
mkdir -p "$ARCHIVE_DIR"

echo "Step 1: Decay stale Neo4j edges (not accessed in $DAYS_BEFORE_DECAY days)..."
echo ""

# Decay stale edges
cypher_decay="
MATCH ()-[r]-()
WHERE r.last_accessed < datetime() - duration('P${DAYS_BEFORE_DECAY}D')
SET r.weight = r.weight * 0.5
RETURN count(r) as weakened_edges
"

# Run via cypher-shell or neo4j-cypher
if command -v cypher-shell &> /dev/null; then
    result=$(cypher-shell -u neo4j -p password "$cypher_decay" 2>/dev/null || echo "Neo4j not available")
    echo "Result: $result"
else
    echo "Skipping: cypher-shell not found"
fi

echo ""
echo "Step 2: Prune orphaned Neo4j nodes (no connections, older than $DAYS_BEFORE_PRUNE days)..."
echo ""

# Prune orphaned nodes
cypher_prune="
MATCH (n)
WHERE NOT ()--(n)
  AND n.created_at < datetime() - duration('P${DAYS_BEFORE_PRUNE}D')
DETACH DELETE n
RETURN count(n) as pruned_nodes
"

if command -v cypher-shell &> /dev/null; then
    result=$(cypher-shell -u neo4j -p password "$cypher_prune" 2>/dev/null || echo "Neo4j not available")
    echo "Result: $result"
else
    echo "Skipping: cypher-shell not found"
fi

echo ""
echo "Step 3: Archive old memory files (older than $DAYS_BEFORE_PRUNE days)..."
echo ""

# Archive old memory files
archived=0
for file in "$MEMORY_DIR"/*.md; do
    if [ -f "$file" ]; then
        # Check file age
        file_age=$(( ($(date +%s) - $(stat -f%m "$file" 2>/dev/null || stat -c%Y "$file" 2>/dev/null)) / 86400 ))
        
        if [ "$file_age" -gt "$DAYS_BEFORE_PRUNE" ]; then
            filename=$(basename "$file")
            archive_name="${filename%.md}-$(date +%Y%m%d).md"
            
            mv "$file" "$ARCHIVE_DIR/$archive_name"
            echo "Archived: $filename → $archive_name"
            archived=$((archived + 1))
        fi
    fi
done

echo ""
echo "Archived $archived files"

echo ""
echo "Step 4: Clean up old archive files (older than 90 days)..."
echo ""

# Clean old archives
deleted=0
for file in "$ARCHIVE_DIR"/*.md; do
    if [ -f "$file" ]; then
        file_age=$(( ($(date +%s) - $(stat -f%m "$file" 2>/dev/null || stat -c%Y "$file" 2>/dev/null)) / 86400 ))
        
        if [ "$file_age" -gt 90 ]; then
            rm "$file"
            echo "Deleted: $(basename "$file")"
            deleted=$((deleted + 1))
        fi
    fi
done

echo ""
echo "Deleted $deleted old archive files"

echo ""
echo "=== Pruning Complete — $(date) ==="
echo ""
echo "Summary:"
echo "  - Stale edges decayed: See Neo4j result"
echo "  - Orphaned nodes pruned: See Neo4j result"
echo "  - Memory files archived: $archived"
echo "  - Old archives deleted: $deleted"
echo ""
echo "Next run: Sunday at 3 AM"
