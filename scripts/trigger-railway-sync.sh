#!/bin/bash
# Trigger architecture sync via Railway
# This script deploys a one-off container to Railway that syncs ARCHITECTURE.md to Neo4j

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "[ARCH-sync] Preparing Railway sync..."

# Create a temporary directory for the sync job
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Copy necessary files
cp "$PROJECT_ROOT/ARCHITECTURE.md" "$TEMP_DIR/"
cp "$SCRIPT_DIR/railway-sync-architecture.js" "$TEMP_DIR/sync.js"

# Create package.json
cat > "$TEMP_DIR/package.json" << 'EOF'
{
  "name": "architecture-sync",
  "version": "1.0.0",
  "description": "One-off architecture sync to Neo4j",
  "main": "sync.js",
  "dependencies": {
    "neo4j-driver": "^5.15.0"
  }
}
EOF

# Create Dockerfile
cat > "$TEMP_DIR/Dockerfile" << 'EOF'
FROM node:20-slim
WORKDIR /app
COPY package.json .
RUN npm install
COPY ARCHITECTURE.md .
COPY sync.js .
CMD ["node", "sync.js"]
EOF

echo "[ARCH-sync] Files prepared in $TEMP_DIR"
echo "[ARCH-sync] To complete the sync, run:"
echo ""
echo "  cd $TEMP_DIR"
echo "  railway up --service=skill-sync-service"
echo ""
echo "[ARCH-sync] Or manually copy ARCHITECTURE.md to the moltbot service and run:"
echo "  railway run --service=moltbot 'node scripts/railway-sync-architecture.js'"
echo ""

# Keep temp dir available for manual execution
rm -rf "$TEMP_DIR"

# Alternative: Try to use the existing moltbot service if available
echo "[ARCH-sync] Attempting sync via existing moltbot service..."

# Check if we can access the moltbot service
cd "$PROJECT_ROOT"

# Try running the sync script through the moltbot service
# This requires the moltbot service to have node and neo4j-driver available
if railway service 2>/dev/null | grep -q "moltbot"; then
    echo "[ARCH-sync] Found moltbot service, attempting sync..."
    railway run --service="moltbot" "node scripts/railway-sync-architecture.js" 2>&1 || {
        echo "[ARCH-sync] Direct sync failed. Manual steps required:"
        echo ""
        echo "1. Ensure moltbot service has neo4j-driver:"
        echo "   railway run --service=moltbot 'npm install neo4j-driver'"
        echo ""
        echo "2. Copy ARCHITECTURE.md to the service (it's deployed with the repo)"
        echo ""
        echo "3. Run the sync:"
        echo "   railway run --service=moltbot 'node scripts/railway-sync-architecture.js'"
    }
else
    echo "[ARCH-sync] moltbot service not found in Railway project"
    echo "[ARCH-sync] Available services:"
    railway service 2>/dev/null || echo "  (unable to list services)"
fi
