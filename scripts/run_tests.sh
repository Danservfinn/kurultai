#!/bin/bash

# Kublai Testing Suite - Local CI Script
# Runs all tests with coverage reporting
# Returns exit code 0 if all pass, 1 if any fail

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "Kublai Testing Suite - Local CI"
echo "=========================================="
echo ""

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Using Python $PYTHON_VERSION"
echo ""

# Create virtual environment if it doesn't exist
VENV_DIR="$PROJECT_ROOT/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# Upgrade pip
echo "Upgrading pip..."
pip install --quiet --upgrade pip

# Install dependencies
echo ""
echo -e "${YELLOW}Installing dependencies...${NC}"
if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
    pip install --quiet -r "$PROJECT_ROOT/requirements.txt"
fi

# Install test dependencies
echo "Installing test dependencies..."
pip install --quiet pytest pytest-cov black ruff

# Install additional test requirements if they exist
if [ -f "$PROJECT_ROOT/test-requirements.txt" ]; then
    pip install --quiet -r "$PROJECT_ROOT/test-requirements.txt"
fi

echo -e "${GREEN}Dependencies installed successfully${NC}"
echo ""

# Track overall success
OVERALL_SUCCESS=0

# Run Black formatting check (informational only)
echo "=========================================="
echo "Running Black formatting check..."
echo "=========================================="
if black --check --diff . 2>/dev/null; then
    echo -e "${GREEN}Black formatting check passed${NC}"
else
    echo -e "${YELLOW}Black formatting issues found (run 'black .' to fix)${NC}"
fi
echo ""

# Run Ruff linting (informational only)
echo "=========================================="
echo "Running Ruff linting..."
echo "=========================================="
if ruff check . 2>/dev/null; then
    echo -e "${GREEN}Ruff linting passed${NC}"
else
    echo -e "${YELLOW}Ruff linting issues found${NC}"
fi
echo ""

# Run tests with coverage
echo "=========================================="
echo "Running tests with coverage..."
echo "=========================================="

# Check if pytest.ini exists for configuration
if [ -f "$PROJECT_ROOT/pytest.ini" ]; then
    echo "Using pytest.ini configuration"
    PYTEST_ARGS=""
else
    echo "Using default pytest configuration"
    PYTEST_ARGS="-v --cov=. --cov-report=term-missing --cov-report=html:htmlcov --cov-report=xml:coverage.xml"
fi

if pytest $PYTEST_ARGS; then
    echo ""
    echo -e "${GREEN}==========================================${NC}"
    echo -e "${GREEN}All tests passed!${NC}"
    echo -e "${GREEN}==========================================${NC}"
else
    echo ""
    echo -e "${RED}==========================================${NC}"
    echo -e "${RED}Some tests failed!${NC}"
    echo -e "${RED}==========================================${NC}"
    OVERALL_SUCCESS=1
fi
echo ""

# Report coverage location
if [ -f "$PROJECT_ROOT/coverage.xml" ]; then
    echo "Coverage XML report: $PROJECT_ROOT/coverage.xml"
fi
if [ -d "$PROJECT_ROOT/htmlcov" ]; then
    echo "Coverage HTML report: $PROJECT_ROOT/htmlcov/index.html"
fi

echo ""
echo "=========================================="
if [ $OVERALL_SUCCESS -eq 0 ]; then
    echo -e "${GREEN}CI completed successfully${NC}"
else
    echo -e "${RED}CI completed with failures${NC}"
fi
echo "=========================================="

exit $OVERALL_SUCCESS
