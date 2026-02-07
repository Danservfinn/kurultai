#!/bin/bash
# Simplified Authentik Deployment Script for Railway
# This script handles the deployment of Authentik services with proper error handling

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ID="26201f75-3375-46ce-98c7-9d1dde5f9569"
DOMAIN="kublai.kurult.ai"

# Service IDs (will be populated)
DB_SERVICE=""
SERVER_SERVICE=""
WORKER_SERVICE=""
PROXY_SERVICE=""

# Generated secrets (will be populated)
AUTHENTIK_SECRET_KEY=""
AUTHENTIK_BOOTSTRAP_PASSWORD=""
AUTHENTIK_POSTGRESQL__PASSWORD=""
SIGNAL_LINK_TOKEN=""

print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Check prerequisites
check_prerequisites() {
    print_header "Checking Prerequisites"

    if ! command -v railway &> /dev/null; then
        print_error "Railway CLI not found. Install with: npm install -g @railway/cli"
        exit 1
    fi

    if ! railway whoami &> /dev/null; then
        print_error "Not logged into Railway. Run: railway login"
        exit 1
    fi

    # Link to project
    if ! railway status &> /dev/null; then
        print_info "Linking to Railway project..."
        railway link --project "$PROJECT_ID" << 'EOF'
1
1
EOF
    fi

    print_success "Prerequisites met"
}

# Generate secrets
generate_secrets() {
    print_header "Generating Secrets"

    AUTHENTIK_SECRET_KEY=$(openssl rand -hex 32)
    AUTHENTIK_BOOTSTRAP_PASSWORD=$(openssl rand -base64 24)
    AUTHENTIK_POSTGRESQL__PASSWORD=$(openssl rand -base64 24)
    SIGNAL_LINK_TOKEN=$(openssl rand -hex 32)

    print_success "Secrets generated"
    print_info "Save these credentials:"
    echo ""
    echo "AUTHENTIK_BOOTSTRAP_PASSWORD: $AUTHENTIK_BOOTSTRAP_PASSWORD"
    echo ""
}

# Get or create services
get_or_create_services() {
    print_header "Getting/Creating Services"

    # Check existing services
    local services_json
    services_json=$(railway status --json 2>/dev/null)

    # Find or create PostgreSQL service
    DB_SERVICE=$(echo "$services_json" | grep -o '"Postgres-P5UQ"' | head -1 | tr -d '"' || echo "")
    if [ -z "$DB_SERVICE" ]; then
        DB_SERVICE=$(echo "$services_json" | grep -o '"Postgres-[^"]*"' | head -1 | tr -d '"' || echo "")
    fi
    if [ -z "$DB_SERVICE" ]; then
        DB_SERVICE=$(echo "$services_json" | grep -o '"postgres[^"]*"' | head -1 | tr -d '"' || echo "")
    fi

    # Find other services
    SERVER_SERVICE=$(echo "$services_json" | grep -o '"unique-manifestation"' | head -1 | tr -d '"' || echo "")
    WORKER_SERVICE=$(echo "$services_json" | grep -o '"powerful-growth"' | head -1 | tr -d '"' || echo "")
    PROXY_SERVICE=$(echo "$services_json" | grep -o '"loyal-enchantment"' | head -1 | tr -d '"' || echo "")

    print_info "Found services:"
    echo "  Database: ${DB_SERVICE:-'Not found - will need to create'}"
    echo "  Server: ${SERVER_SERVICE:-'Not found - will need to create'}"
    echo "  Worker: ${WORKER_SERVICE:-'Not found - will need to create'}"
    echo "  Proxy: ${PROXY_SERVICE:-'Not found - will need to create'}"
}

# Set project-level environment variables
set_project_env() {
    print_header "Setting Project Environment Variables"

    # Set variables at project level
    railway variables set \
        AUTHENTIK_SECRET_KEY="$AUTHENTIK_SECRET_KEY" \
        AUTHENTIK_BOOTSTRAP_PASSWORD="$AUTHENTIK_BOOTSTRAP_PASSWORD" \
        AUTHENTIK_EXTERNAL_HOST="https://$DOMAIN" \
        SIGNAL_LINK_TOKEN="$SIGNAL_LINK_TOKEN" \
        AUTHENTIK_URL="http://authentik-server:9000" \
        2>/dev/null || print_warning "Some project variables may already be set"

    print_success "Project environment variables set"
}

# Set service-level environment variables
set_service_env() {
    print_header "Setting Service Environment Variables"

    # Get PostgreSQL connection details
    local pg_host=""
    local pg_db=""
    local pg_user=""
    local pg_pass=""

    if [ -n "$DB_SERVICE" ]; then
        print_info "Getting PostgreSQL connection details..."
        local db_vars
        db_vars=$(railway variables -s "$DB_SERVICE" 2>/dev/null)

        pg_host=$(echo "$db_vars" | grep PGHOST | awk -F'│' '{print $3}' | tr -d ' ' || echo "")
        pg_db=$(echo "$db_vars" | grep PGDATABASE | awk -F'│' '{print $3}' | tr -d ' ' || echo "")
        pg_user=$(echo "$db_vars" | grep PGUSER | awk -F'│' '{print $3}' | tr -d ' ' || echo "")
        pg_pass=$(echo "$db_vars" | grep PGPASSWORD | awk -F'│' '{print $3}' | tr -d ' ' || echo "")
    fi

    # Use defaults if not found
    pg_host=${pg_host:-"postgres-p5uq.railway.internal"}
    pg_db=${pg_db:-"railway"}
    pg_user=${pg_user:-"postgres"}
    pg_pass=${pg_pass:-"$AUTHENTIK_POSTGRESQL__PASSWORD"}

    # Set server service variables
    if [ -n "$SERVER_SERVICE" ]; then
        print_info "Setting variables for $SERVER_SERVICE..."
        railway variables set -s "$SERVER_SERVICE" \
            AUTHENTIK_SECRET_KEY="$AUTHENTIK_SECRET_KEY" \
            AUTHENTIK_BOOTSTRAP_PASSWORD="$AUTHENTIK_BOOTSTRAP_PASSWORD" \
            AUTHENTIK_EXTERNAL_HOST="https://$DOMAIN" \
            AUTHENTIK_POSTGRESQL__HOST="$pg_host" \
            AUTHENTIK_POSTGRESQL__NAME="$pg_db" \
            AUTHENTIK_POSTGRESQL__USER="$pg_user" \
            AUTHENTIK_POSTGRESQL__PASSWORD="$pg_pass" \
            2>/dev/null || print_warning "Failed to set some server variables"
    fi

    # Set worker service variables
    if [ -n "$WORKER_SERVICE" ]; then
        print_info "Setting variables for $WORKER_SERVICE..."
        railway variables set -s "$WORKER_SERVICE" \
            AUTHENTIK_SECRET_KEY="$AUTHENTIK_SECRET_KEY" \
            AUTHENTIK_EXTERNAL_HOST="https://$DOMAIN" \
            AUTHENTIK_POSTGRESQL__HOST="$pg_host" \
            AUTHENTIK_POSTGRESQL__NAME="$pg_db" \
            AUTHENTIK_POSTGRESQL__USER="$pg_user" \
            AUTHENTIK_POSTGRESQL__PASSWORD="$pg_pass" \
            2>/dev/null || print_warning "Failed to set some worker variables"
    fi

    # Set proxy service variables
    if [ -n "$PROXY_SERVICE" ]; then
        print_info "Setting variables for $PROXY_SERVICE..."
        railway variables set -s "$PROXY_SERVICE" \
            SIGNAL_LINK_TOKEN="$SIGNAL_LINK_TOKEN" \
            AUTHENTIK_URL="http://authentik-server:9000" \
            PORT="8080" \
            2>/dev/null || print_warning "Failed to set some proxy variables"
    fi

    print_success "Service environment variables set"
}

# Deploy a service
deploy_service() {
    local service_name=$1
    local service_dir=$2
    local max_attempts=3

    print_header "Deploying $service_name"

    if [ -z "$service_name" ]; then
        print_error "Service name is empty"
        return 1
    fi

    # Change to service directory if provided
    if [ -n "$service_dir" ] && [ -d "$service_dir" ]; then
        cd "$service_dir"
    fi

    # Deploy with retries
    local attempt=1
    while [ $attempt -le $max_attempts ]; do
        print_info "Attempt $attempt of $max_attempts..."

        if railway up --service "$service_name" 2>&1; then
            print_success "$service_name deployed successfully"
            return 0
        fi

        print_warning "Deployment failed, retrying..."
        sleep 5
        attempt=$((attempt + 1))
    done

    print_error "Failed to deploy $service_name after $max_attempts attempts"
    return 1
}

# Check service health
check_service_health() {
    local service_name=$1
    local max_wait=300
    local wait_interval=10
    local elapsed=0

    print_header "Checking Health for $service_name"

    while [ $elapsed -lt $max_wait ]; do
        local status
        status=$(railway status --json 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
for edge in data['environments']['edges'][0]['node']['serviceInstances']['edges']:
    if edge['node']['serviceName'] == '$service_name':
        deployment = edge['node'].get('latestDeployment')
        if deployment:
            print(deployment.get('status', 'UNKNOWN'))
        else:
            print('NO_DEPLOYMENT')
        break
" 2>/dev/null || echo "UNKNOWN")

        case "$status" in
            "SUCCESS")
                print_success "$service_name is healthy"
                return 0
                ;;
            "CRASHED"|"FAILED")
                print_error "$service_name has crashed"
                return 1
                ;;
            "DEPLOYING"|"BUILDING"|"INITIALIZING")
                print_info "$service_name is still starting (status: $status)..."
                ;;
            *)
                print_info "Waiting for $service_name (status: $status)..."
                ;;
        esac

        sleep $wait_interval
        elapsed=$((elapsed + wait_interval))
    done

    print_error "$service_name health check timed out"
    return 1
}

# Wait for database to be ready
wait_for_database() {
    print_header "Waiting for Database"

    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if railway connect "$DB_SERVICE" -c "SELECT 1;" 2>/dev/null; then
            print_success "Database is ready"
            return 0
        fi

        print_info "Waiting for database (attempt $attempt/$max_attempts)..."
        sleep 10
        attempt=$((attempt + 1))
    done

    print_warning "Could not confirm database readiness, continuing anyway..."
    return 0
}

# Print deployment summary
print_summary() {
    print_header "Deployment Summary"

    echo ""
    echo "Services:"
    echo "  Database: $DB_SERVICE"
    echo "  Server: $SERVER_SERVICE"
    echo "  Worker: $WORKER_SERVICE"
    echo "  Proxy: $PROXY_SERVICE"
    echo ""
    echo "Access URLs:"
    echo "  Admin UI: https://$DOMAIN/if/admin/"
    echo "  Application: https://$DOMAIN"
    echo ""
    echo "Credentials:"
    echo "  Username: akadmin"
    echo "  Password: $AUTHENTIK_BOOTSTRAP_PASSWORD"
    echo ""
    echo "Next Steps:"
    echo "  1. Access the admin UI and change the default password"
    echo "  2. Configure WebAuthn in the admin panel"
    echo "  3. Test biometric authentication"
    echo ""
    echo "To view logs:"
    echo "  railway logs --service $SERVER_SERVICE"
    echo ""
}

# Main deployment flow
main() {
    print_header "Authentik Deployment to Railway"

    check_prerequisites
    generate_secrets
    get_or_create_services
    set_project_env
    set_service_env

    # Note: Due to Railway CLI limitations, manual deployment may be required
    print_header "Manual Deployment Required"

    echo ""
    echo "Due to Railway CLI limitations, please complete deployment via the dashboard:"
    echo ""
    echo "1. Go to: https://railway.com/project/$PROJECT_ID"
    echo ""
    echo "2. Deploy services in this order:"
    echo "   a. $DB_SERVICE (PostgreSQL) - Click 'Deploy' if not running"
    echo "   b. $SERVER_SERVICE (authentik-server) - Deploy after database is ready"
    echo "   c. $WORKER_SERVICE (authentik-worker) - Deploy after server is ready"
    echo "   d. $PROXY_SERVICE (authentik-proxy) - Deploy last"
    echo ""
    echo "3. Configure domain:"
    echo "   Add custom domain '$DOMAIN' to $PROXY_SERVICE"
    echo ""
    echo "4. Run bootstrap:"
    echo "   python authentik-proxy/bootstrap_authentik.py"
    echo ""

    # Save credentials to file
    cat > authentik-credentials.txt << EOF
Authentik Deployment Credentials
================================
Domain: $DOMAIN
Admin URL: https://$DOMAIN/if/admin/

Username: akadmin
Password: $AUTHENTIK_BOOTSTRAP_PASSWORD

Database Host: (see Railway dashboard)
Generated At: $(date)
EOF

    print_success "Credentials saved to authentik-credentials.txt"
    print_info "Keep this file secure!"
}

# Run main function
main "$@"
