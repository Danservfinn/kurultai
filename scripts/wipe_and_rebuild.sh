#!/bin/bash
# Kurultai v0.2 Wipe and Rebuild Script
# WARNING: This deletes all Railway services! Use only for fresh deployments.

set -e

echo "=========================================="
echo "  Kurultai v0.2 Wipe and Rebuild"
echo "=========================================="
echo ""
echo "WARNING: This will DELETE all Railway services!"
echo "This action is IRREVERSIBLE!"
echo ""

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "Error: Railway CLI is not installed"
    echo "Install it with: npm install -g @railway/cli"
    exit 1
fi

# Check if logged in
if ! railway whoami &> /dev/null; then
    echo "Error: Not logged into Railway"
    echo "Login with: railway login"
    exit 1
fi

# Create backup directory
BACKUP_DIR="$HOME/kurultai-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "Creating backup in: $BACKUP_DIR"
echo ""

# Backup Railway variables
echo "Backing up Railway variables..."
railway variables --json > "$BACKUP_DIR/railway-vars.json" 2>/dev/null || echo "  (No Railway variables to backup)"

# Backup local .env
if [[ -f ".env" ]]; then
    echo "Backing up local .env..."
    cp .env "$BACKUP_DIR/.env.backup"
fi

# List current services
echo ""
echo "Current Railway services:"
railway services
echo ""

# Confirmation prompt
read -p "Type 'DELETE' to confirm deletion of ALL services: " confirm

if [[ "$confirm" != "DELETE" ]]; then
    echo ""
    echo "Aborted. No services were deleted."
    echo "Backup is available at: $BACKUP_DIR"
    exit 0
fi

echo ""
echo "Deleting services..."

# Delete each service
services=("authentik-db" "authentik-worker" "authentik-server" "authentik-proxy" "moltbot-railway-template")

for service in "${services[@]}"; do
    echo "  Deleting $service..."
    railway remove "$service" 2>/dev/null && echo "    ✓ $service deleted" || echo "    (skipped: $service not found)"
done

echo ""
echo "=========================================="
echo "  All services deleted"
echo "=========================================="
echo ""
echo "Backup location: $BACKUP_DIR"
echo ""
echo "Next steps:"
echo "  1. Rebuild services: railway up"
echo "  2. Run migrations: python scripts/run_migrations.py"
echo "  3. Generate agent keys: ./scripts/generate_agent_keys.sh"
echo ""
