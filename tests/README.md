# MCP-Codegen Integration Tests

This directory contains integration tests that verify `mcp-codegen` works correctly with real MCP servers.

## Test Coverage

The tests verify all three main commands against multiple public MCP servers:

### Test Servers

1. **DeepWiki MCP** (`https://mcp.deepwiki.com/mcp`)
   - SSE-based HTTP POST with session management
   - Tests GitHub repository documentation tools

2. **SMHI MCP** (`https://smhi-mcp.hakan-3a6.workers.dev`)
   - Plain JSON HTTP POST
   - Tests Swedish weather data API

3. **Exa MCP** (`https://mcp.exa.ai/mcp`)
   - Standard JSON HTTP POST
   - Tests web search and code context tools

### Commands Tested

- **ls**: List available tools from server
- **gen**: Generate static Python stub modules
- **call**: Invoke tools directly

## Requirements

Install test dependencies:

```bash
# Option 1: Install with test extras (recommended)
pip install -e ".[test]"

# Option 2: Install pytest manually
pip install pytest pytest-asyncio
```

## Running Tests

### Quick Run (All Tests)

```bash
./tests/run_tests.sh
```

### Run with Pytest Directly

```bash
# Run all tests
pytest tests/test_mcp_servers.py -v

# Run specific test
pytest tests/test_mcp_servers.py::test_fetch_schema -v

# Run tests for specific server
pytest tests/test_mcp_servers.py -v -k "deepwiki"

# Run with detailed output
pytest tests/test_mcp_servers.py -v -s
```

### Run Tests Manually (Without Pytest)

```bash
cd /path/to/mcpmod-0.1.3
python tests/test_mcp_servers.py
```

## Test Structure

```
tests/
├── __init__.py              # Package marker
├── conftest.py              # Pytest configuration
├── test_mcp_servers.py      # Main integration tests
├── run_tests.sh             # Quick test runner script
└── README.md                # This file
```

## What Gets Tested

Each server is tested for:

1. **Transport Detection** - Verifies protocol detection works
2. **Schema Fetching (ls)** - Fetches and validates tool list
3. **Code Generation (gen)** - Generates Python stub modules
4. **Tool Invocation (call)** - Calls a real tool and validates response

## Adding New Test Servers

To add a new MCP server to the test suite:

1. Edit `test_mcp_servers.py`
2. Add entry to `TEST_SERVERS` dict:

```python
"server_name": {
    "url": "https://example.com/mcp",
    "description": "Brief description",
    "expected_tools": ["tool1", "tool2"],
    "test_call": {
        "tool": "tool1",
        "args": [("param", "value")],
        "expected_in_response": "expected_string"
    }
}
```

## Troubleshooting

### Tests Timeout

Some servers may be slow. Increase timeout:
```bash
pytest tests/test_mcp_servers.py -v --timeout=60
```

### Import Errors

Make sure you're running from the project root:
```bash
cd /path/to/mcpmod-0.1.3
pytest tests/
```

### Network Issues

These are integration tests that require internet access. If a server is down, tests will fail.

## CI/CD Integration

To run these tests in CI:

```yaml
# .github/workflows/test.yml
- name: Install dependencies
  run: |
    pip install -e .
    pip install pytest pytest-asyncio

- name: Run integration tests
  run: pytest tests/test_mcp_servers.py -v
  timeout-minutes: 10
```

## Notes

- Tests make real network requests to public MCP servers
- Test execution time depends on network speed and server response times
- Some tests may fail if servers are temporarily unavailable
- Tests validate compatibility with different MCP transport protocols:
  - Streamable HTTP (SSE-based)
  - Plain HTTP POST with JSON
  - Plain HTTP POST with SSE responses
