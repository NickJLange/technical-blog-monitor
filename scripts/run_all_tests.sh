#!/bin/bash
# Run all tests for the Technical Blog Monitor

set -e  # Exit on error

# Ensure we are running from the project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Unset BROWSER to avoid Pydantic settings conflict
unset BROWSER

echo "======================================"
echo "Running All Tests"
echo "======================================"
echo "Working Directory: $(pwd)"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track failures
FAILED=0

# Function to run a test and track results
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    echo "--------------------------------------"
    echo "Running: $test_name"
    echo "--------------------------------------"
    
    if eval "$test_command"; then
        echo -e "${GREEN}✓ $test_name passed${NC}"
        echo ""
        return 0
    else
        echo -e "${RED}✗ $test_name failed${NC}"
        echo ""
        FAILED=$((FAILED + 1))
        return 1
    fi
}

# 1. Unit Tests
run_test "Unit Tests (pytest)" "uv run pytest monitor/tests/" || true

# 2. Basic Integration Tests
run_test "Basic Integration Tests" "uv run python tests/integration/test_basic.py" || true

# 3. Feed Tests
run_test "Feed Parsing Tests" "uv run python tests/integration/test_feeds.py" || true

# 4. Full Pipeline Test
run_test "Full Pipeline Test" "uv run python tests/e2e/test_full_pipeline.py" || true

# 5. Postgres E2E Test
run_test "Postgres E2E Test" "uv run python tests/e2e/test_postgres_pipeline.py" || true

# 6. Linting
run_test "Code Linting (ruff)" "uv run ruff check ." || true

# 7. Type Checking
run_test "Type Checking (mypy)" "uv run mypy monitor/" || true

# Summary
echo "======================================"
echo "Test Summary"
echo "======================================"

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}$FAILED test suite(s) failed${NC}"
    exit 1
fi
