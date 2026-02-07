#!/bin/bash
# Kurultai v0.2 Phase 7 Test Suite Runner
# Runs unit tests, integration tests, and e2e tests

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Kurultai v0.2 Phase 7 Test Suite ==="
echo ""

# Check if we're in project directory
cd "$PROJECT_DIR"

# Parse arguments
RUN_UNIT=true
RUN_INTEGRATION=true
RUN_E2E=false
DEPLOYED_URL="https://kublai.kurult.ai"

while [[ $# -gt 0 ]]; do
    case $1 in
        --no-unit)
            RUN_UNIT=false
            shift
            ;;
        --no-integration)
            RUN_INTEGRATION=false
            shift
            ;;
        --e2e)
            RUN_E2E=true
            shift
            ;;
        --url)
            DEPLOYED_URL="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --no-unit        Skip unit tests"
            echo "  --no-integration Skip integration tests"
            echo "  --e2e            Run end-to-end tests against deployed URL"
            echo "  --url URL        Set deployed URL for e2e tests (default: https://kublai.kurult.ai)"
            echo ""
            echo "Examples:"
            echo "  $0                    # Run unit and integration tests"
            echo "  $0 --e2e              # Run all tests including e2e"
            echo "  $0 --e2e --url http://localhost:3000"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage"
            exit 1
            ;;
    esac
done

# Install test dependencies if needed
if [[ ! -d "venv" ]] && [[ ! -d ".venv" ]]; then
    echo "Installing test dependencies..."
    pip install -q pytest pytest-cov pytest-asyncio
fi

# Unit Tests
if [[ "$RUN_UNIT" == true ]]; then
    echo ""
    echo "========================================="
    echo "  Unit Tests"
    echo "========================================="
    echo ""

    pytest tests/ -v --tb=short --cov=src --cov-report=term-missing \
        --ignore=tests/integration/ --ignore=tests/chaos/ \
        --ignore=tests/performance/ --ignore=tests/security/ || true

    echo ""
fi

# Integration Tests
if [[ "$RUN_INTEGRATION" == true ]]; then
    echo ""
    echo "========================================="
    echo "  Integration Tests"
    echo "========================================="
    echo ""

    pytest tests/integration/ -v --tb=short || true

    echo ""
fi

# End-to-End Tests
if [[ "$RUN_E2E" == true ]]; then
    echo ""
    echo "========================================="
    echo "  End-to-End Tests"
    echo "========================================="
    echo "Target: $DEPLOYED_URL"
    echo ""

    # Test 1: Unauthenticated redirect to login
    echo "Test 1: Unauthenticated redirect to Authentik"
    response=$(curl -s -I "$DEPLOYED_URL/dashboard" | head -n 1)
    if echo "$response" | grep -q "302"; then
        echo "  ✓ Returns 302 redirect"
    else
        echo "  ✗ Expected 302, got: $response"
    fi

    # Test 2: Health check
    echo ""
    echo "Test 2: Health check endpoint"
    health_response=$(curl -s "$DEPLOYED_URL/health")
    if echo "$health_response" | grep -q "healthy"; then
        echo "  ✓ Health check returns healthy status"
    else
        echo "  ✗ Health check failed: $health_response"
    fi

    # Test 3: Signal link requires token
    echo ""
    echo "Test 3: Signal link requires authentication"
    signal_response=$(curl -s -w "%{http_code}" -o /dev/null -X POST "$DEPLOYED_URL/setup/api/signal-link" \
        -H "Content-Type: application/json" \
        -d '{"phoneNumber": "+1234567890"}')
    if [[ "$signal_response" == "401" ]]; then
        echo "  ✓ Signal link returns 401 Unauthorized (as expected)"
    else
        echo "  ✗ Expected 401, got: $signal_response"
    fi

    # Test 4: File consistency monitor
    echo ""
    echo "Test 4: File consistency monitor health"
    fc_response=$(curl -s "$DEPLOYED_URL/health/file-consistency")
    if echo "$fc_response" | grep -q "monitor_running.*true"; then
        echo "  ✓ File consistency monitor is running"
    else
        echo "  ✗ File consistency monitor check failed: $fc_response"
    fi

    echo ""
fi

# Summary
echo ""
echo "========================================="
echo "  Test Suite Summary"
echo "========================================="
echo ""
echo "Run individual test suites:"
echo "  Unit tests:         pytest tests/ -v --ignore=tests/integration/"
echo "  Integration tests:  pytest tests/integration/ -v"
echo "  Chaos tests:        pytest tests/chaos/ -v"
echo "  Performance tests:  pytest tests/performance/ -v"
echo "  Security tests:     pytest tests/security/ -v"
echo ""
echo "Run with coverage:"
echo "  pytest tests/ --cov=src --cov-report=html"
echo "  open htmlcov/index.html"
echo ""
