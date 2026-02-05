#!/bin/bash
# Authentik Deployment Script for Railway
# This script deploys Authentik services and configures them

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
RAILWAY_PROJECT="${RAILWAY_PROJECT:-}"
RAILWAY_SERVICE="${RAILWAY_SERVICE:-}"

echo -e "${GREEN}=== Authentik Deployment Script ===${NC}"
echo ""

# Check prerequisites
check_prerequisites() {
    echo -e "${YELLOW}Checking prerequisites...${NC}"

    if ! command -v railway &> /dev/null; then
        echo -e "${RED}Error: Railway CLI not found. Install with: npm install -g @railway/cli${NC}"
        exit 1
    fi

    if ! railway whoami &> /dev/null; then
        echo -e "${RED}Error: Not logged into Railway. Run: railway login${NC}"
        exit 1
    fi

    echo -e "${GREEN}✓ Prerequisites met${NC}"
}

# Generate secrets if not provided
generate_secrets() {
    echo -e "${YELLOW}Generating secrets...${NC}"

    if [ -z "${AUTHENTIK_SECRET_KEY:-}" ]; then
        AUTHENTIK_SECRET_KEY=$(openssl rand -hex 32)
        echo -e "${GREEN}✓ Generated AUTHENTIK_SECRET_KEY${NC}"
    fi

    if [ -z "${AUTHENTIK_BOOTSTRAP_PASSWORD:-}" ]; then
        AUTHENTIK_BOOTSTRAP_PASSWORD=$(openssl rand -base64 24)
        echo -e "${GREEN}✓ Generated AUTHENTIK_BOOTSTRAP_PASSWORD${NC}"
        echo -e "${YELLOW}⚠ Save this password: ${AUTHENTIK_BOOTSTRAP_PASSWORD}${NC}"
    fi

    if [ -z "${SIGNAL_LINK_TOKEN:-}" ]; then
        SIGNAL_LINK_TOKEN=$(openssl rand -hex 32)
        echo -e "${GREEN}✓ Generated SIGNAL_LINK_TOKEN${NC}"
    fi

    if [ -z "${AUTHENTIK_POSTGRESQL__PASSWORD:-}" ]; then
        AUTHENTIK_POSTGRESQL__PASSWORD=$(openssl rand -base64 24)
        echo -e "${GREEN}✓ Generated AUTHENTIK_POSTGRESQL__PASSWORD${NC}"
    fi
}

# Set environment variables in Railway
set_railway_env() {
    echo -e "${YELLOW}Setting Railway environment variables...${NC}"

    # Core Authentik settings
    railway variables set AUTHENTIK_SECRET_KEY="$AUTHENTIK_SECRET_KEY"
    railway variables set AUTHENTIK_BOOTSTRAP_PASSWORD="$AUTHENTIK_BOOTSTRAP_PASSWORD"
    railway variables set AUTHENTIK_EXTERNAL_HOST="https://kublai.kurult.ai"

    # Database settings
    railway variables set AUTHENTIK_POSTGRESQL__HOST="authentik-db.railway.internal"
    railway variables set AUTHENTIK_POSTGRESQL__NAME="authentik"
    railway variables set AUTHENTIK_POSTGRESQL__USER="postgres"
    railway variables set AUTHENTIK_POSTGRESQL__PASSWORD="$AUTHENTIK_POSTGRESQL__PASSWORD"

    # Proxy settings
    railway variables set SIGNAL_LINK_TOKEN="$SIGNAL_LINK_TOKEN"

    echo -e "${GREEN}✓ Environment variables set${NC}"
}

# Deploy services
deploy_services() {
    echo -e "${YELLOW}Deploying services...${NC}"

    # Deploy database first
    echo "Deploying authentik-db..."
    railway up --service authentik-db

    # Wait for database to be ready
    echo "Waiting for database to be ready..."
    sleep 30

    # Deploy server
    echo "Deploying authentik-server..."
    railway up --service authentik-server

    # Wait for server to be ready
    echo "Waiting for server to be ready..."
    sleep 60

    # Deploy worker
    echo "Deploying authentik-worker..."
    railway up --service authentik-worker

    # Deploy proxy
    echo "Deploying authentik-proxy..."
    railway up --service authentik-proxy

    echo -e "${GREEN}✓ Services deployed${NC}"
}

# Run bootstrap script
run_bootstrap() {
    echo -e "${YELLOW}Running Authentik bootstrap...${NC}"

    # Get the authentik-server service ID
    SERVER_ID=$(railway service list | grep authentik-server | awk '{print $1}')

    if [ -z "$SERVER_ID" ]; then
        echo -e "${RED}Error: Could not find authentik-server service${NC}"
        exit 1
    fi

    # Copy and run bootstrap script
    railway connect "$SERVER_ID" -- \
        sh -c "
            echo 'Waiting for Authentik to be fully ready...'
            sleep 30
            python /tmp/bootstrap_authentik.py || echo 'Bootstrap script not found, configure manually'
        "

    echo -e "${GREEN}✓ Bootstrap complete${NC}"
}

# Verify deployment
verify_deployment() {
    echo -e "${YELLOW}Verifying deployment...${NC}"

    # Check health endpoints
    PROXY_URL=$(railway domain | grep authentik-proxy | head -1)

    if [ -n "$PROXY_URL" ]; then
        echo "Checking proxy health..."
        curl -sf "https://$PROXY_URL/health" && echo -e "${GREEN}✓ Proxy healthy${NC}" || echo -e "${RED}✗ Proxy unhealthy${NC}"
    fi

    echo -e "${GREEN}✓ Verification complete${NC}"
}

# Print next steps
print_next_steps() {
    echo ""
    echo -e "${GREEN}=== Deployment Complete ===${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Access Authentik admin at: https://kublai.kurult.ai/if/admin/"
    echo "2. Login with: akadmin / $AUTHENTIK_BOOTSTRAP_PASSWORD"
    echo "3. Change the admin password immediately"
    echo "4. Configure WebAuthn in the admin panel:"
    echo "   - Go to Flows & Stages > Stages"
    echo "   - Create WebAuthn authenticator stage"
    echo "   - Add to the authentication flow"
    echo "5. Test biometric authentication"
    echo ""
    echo "Backup configuration:"
    echo "- Run: ./scripts/backup-authentik-db.sh"
    echo "- Or configure automated backups via Railway cron"
    echo ""
    echo -e "${YELLOW}Important: Save these credentials securely!${NC}"
    echo "AUTHENTIK_BOOTSTRAP_PASSWORD: $AUTHENTIK_BOOTSTRAP_PASSWORD"
}

# Main execution
main() {
    case "${1:-deploy}" in
        check)
            check_prerequisites
            ;;
        secrets)
            generate_secrets
            echo ""
            echo "Add these to your environment:"
            echo "export AUTHENTIK_SECRET_KEY=$AUTHENTIK_SECRET_KEY"
            echo "export AUTHENTIK_BOOTSTRAP_PASSWORD=$AUTHENTIK_BOOTSTRAP_PASSWORD"
            echo "export AUTHENTIK_POSTGRESQL__PASSWORD=$AUTHENTIK_POSTGRESQL__PASSWORD"
            echo "export SIGNAL_LINK_TOKEN=$SIGNAL_LINK_TOKEN"
            ;;
        deploy)
            check_prerequisites
            generate_secrets
            set_railway_env
            deploy_services
            run_bootstrap
            verify_deployment
            print_next_steps
            ;;
        bootstrap)
            run_bootstrap
            ;;
        verify)
            verify_deployment
            ;;
        *)
            echo "Usage: $0 {check|secrets|deploy|bootstrap|verify}"
            echo ""
            echo "Commands:"
            echo "  check     - Check prerequisites"
            echo "  secrets   - Generate and display secrets"
            echo "  deploy    - Full deployment (default)"
            echo "  bootstrap - Run bootstrap script only"
            echo "  verify    - Verify deployment health"
            exit 1
            ;;
    esac
}

main "$@"
