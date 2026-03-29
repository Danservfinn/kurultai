#!/bin/bash
EXPORT_DIR="$HOME/.openclaw/backups/neo4j-conversations"
mkdir -p "$EXPORT_DIR"
DATE=$(date +%Y-%m-%d)

# Read password from environment for security
NEO4J_PASSWORD="${NEO4J_PASSWORD:-$(cat ~/.openclaw/credentials/neo4j.env 2>/dev/null | grep NEO4J_PASSWORD | cut -d'=' -f2)}"

if [ -z "$NEO4J_PASSWORD" ]; then
  echo "ERROR: NEO4J_PASSWORD not set" >&2
  exit 1
fi

cypher-shell -u neo4j -p "$NEO4J_PASSWORD" --format plain \
  "MATCH (m:Message)-[:IN_THREAD]->(t:Thread)
   OPTIONAL MATCH (m)-[:SENT_BY]->(h:Human)
   RETURN m.id, m.humanId, m.contentScrubbed, m.direction, m.channel,
          toString(m.timestamp), t.id, t.status, h.displayName
   ORDER BY m.timestamp" > "$EXPORT_DIR/messages-$DATE.csv"

# Compress and keep last 30 days
gzip "$EXPORT_DIR/messages-$DATE.csv"
find "$EXPORT_DIR" -name "*.gz" -mtime +30 -delete
