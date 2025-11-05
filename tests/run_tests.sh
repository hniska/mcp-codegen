#!/bin/bash
# Quick test runner for mcp-codegen integration tests

set -e

echo "==================================="
echo "MCP-Codegen Integration Test Suite"
echo "==================================="
echo ""

# Check if pytest is available
if ! command -v pytest &> /dev/null; then
    echo "Error: pytest not found. Install with: pip install pytest pytest-asyncio"
    exit 1
fi

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

echo "Running tests from: $(pwd)"
echo ""

# Run pytest with verbose output
echo "--- Running pytest ---"
pytest tests/test_mcp_servers.py -v --tb=short "$@"

echo ""
echo "==================================="
echo "✓ All tests passed!"
echo "==================================="
