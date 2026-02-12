#!/bin/bash
# Apply Neo4j IPv6 Fix to Railway
#
# This script applies the Neo4j IPv6 fix to your Railway deployment
# using the Railway CLI. Run this from your project root.
#
# Prerequisites:
#   - Railway CLI installed: npm install -g @railway/cli
#   - Logged in: railway login
#   - In a Railway-linked project directory
#
# Usage: ./scripts/apply-neo4j-ipv6-fix.sh [--service neo4j]

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default service name
SERVICE_NAME="neo4j"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --service)
            SERVICE_NAME="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [--service SERVICE_NAME]"
            echo ""
            echo "Options:"
            echo "  --service SERVICE_NAME  Neo4j service name (default: neo4j)"
            echo "  --help, -h              Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}     Applying Neo4j IPv6 Fix to Railway${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Check if railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo -e "${RED}ERROR: Railway CLI not found${NC}"
    echo ""
    echo "Please install the Railway CLI:"
    echo "  npm install -g @railway/cli"
    echo ""
    exit 1
fi

# Check if logged in
echo -e "${BLUE}Checking Railway CLI authentication...${NC}"
if ! railway whoami &> /dev/null; then
    echo -e "${RED}ERROR: Not logged in to Railway${NC}"
    echo ""
    echo "Please login:"
    echo "  railway login"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓ Authenticated with Railway${NC}"
echo ""

# Check if we're in a linked project
if [ ! -f ".railway/config.json" ]; then
    echo -e "${YELLOW}WARNING: No .railway/config.json found${NC}"
    echo "Make sure you're in a Railway-linked project directory."
    echo ""
    echo "To link this project:"
    echo "  railway link"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo -e "${BLUE}Applying IPv6 fix to service: ${SERVICE_NAME}${NC}"
echo ""

# Apply the fix
echo -e "${YELLOW}Step 1: Setting NEO4J_dbms_default__listen__address=::${NC}"
if railway variables --service "$SERVICE_NAME" set NEO4J_dbms_default__listen__address "::"; then
    echo -e "${GREEN}✓ Variable set successfully${NC}"
else
    echo -e "${RED}✗ Failed to set variable${NC}"
    exit 1
fi
echo ""

echo -e "${YELLOW}Step 2: Setting connector-specific addresses${NC}"
railway variables --service "$SERVICE_NAME" set NEO4J_dbms_connector_bolt_listen__address "::" || true
railway variables --service "$SERVICE_NAME" set NEO4J_dbms_connector_http_listen__address "::" || true
echo -e "${GREEN}✓ Connector addresses set${NC}"
echo ""

echo -e "${YELLOW}Step 3: Verifying configuration${NC}"
echo "Current Neo4j environment variables:"
railway variables --service "$SERVICE_NAME" | grep -E "^NEO4J_" || true
echo ""

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}     IPv6 Fix Applied Successfully!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "Next steps:"
echo "  1. Redeploy the Neo4j service:"
echo -e "     ${YELLOW}railway up --service ${SERVICE_NAME}${NC}"
echo ""
echo "  2. Wait for Neo4j to start (30-60 seconds)"
echo ""
echo "  3. Test connectivity:"
echo -e "     ${YELLOW}python3 scripts/neo4j_connection_helper.py --diagnose${NC}"
echo ""
echo "  4. Redeploy services that connect to Neo4j:"
echo -e "     ${YELLOW}railway up --service moltbot${NC}"
echo ""
echo "Documentation: docs/NEO4J_IPV6_FIX.md"
echo ""
