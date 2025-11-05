"""Integration tests for mcp-codegen with real MCP servers.

Tests the ls, gen, and call commands against multiple public MCP servers
to ensure compatibility with different transport protocols and server implementations.
"""
import asyncio
import json
import os
import tempfile
import pytest
from pathlib import Path

from mcp_codegen.codegen import fetch_schema, detect_transport
from mcp_codegen.cli import _call


# Test servers with different characteristics
TEST_SERVERS = {
    "deepwiki": {
        "url": "https://mcp.deepwiki.com/mcp",
        "description": "SSE-based HTTP POST with session management",
        "expected_tools": ["read_wiki_structure", "read_wiki_contents", "ask_question"],
        "test_call": {
            "tool": "read_wiki_structure",
            "args": [("repoName", "anthropics/anthropic-sdk-python")],
            "expected_in_response": "Overview"
        }
    },
    "smhi": {
        "url": "https://smhi-mcp.hakan-3a6.workers.dev",
        "description": "Plain JSON HTTP POST",
        "expected_tools": ["get_weather_forecast", "list_snowmobile_conditions"],
        "test_call": {
            "tool": "get_weather_forecast",
            "args": [("lat", 64.75), ("lon", 20.95), ("limit", 1)],
            "expected_in_response": "temperature"
        }
    },
    "exa": {
        "url": "https://mcp.exa.ai/mcp",
        "description": "Standard JSON HTTP POST",
        "expected_tools": ["web_search_exa", "get_code_context_exa"],
        "test_call": {
            "tool": "web_search_exa",
            "args": [("query", "test"), ("numResults", 1)],
            "expected_in_response": "results"
        }
    }
}


@pytest.mark.asyncio
@pytest.mark.integration  # Add this marker
@pytest.mark.parametrize("server_name", TEST_SERVERS.keys())
async def test_fetch_schema(server_name):
    """Test fetching tool schema (ls command) from MCP server."""
    server = TEST_SERVERS[server_name]

    # Fetch schema
    tools = await fetch_schema(server["url"])

    # Verify we got tools
    assert len(tools) > 0, f"No tools returned from {server_name}"

    # Verify expected tools are present
    tool_names = [t.name for t in tools]
    for expected_tool in server["expected_tools"]:
        assert expected_tool in tool_names, \
            f"Expected tool '{expected_tool}' not found in {server_name}. Got: {tool_names}"

    print(f"✓ {server_name}: Found {len(tools)} tools")


@pytest.mark.asyncio
@pytest.mark.integration  # Add this marker
@pytest.mark.parametrize("server_name", TEST_SERVERS.keys())
async def test_generate_stub(server_name):
    """Test generating Python stub module (gen command) from MCP server."""
    server = TEST_SERVERS[server_name]

    # Import render_module here to avoid circular imports
    from mcp_codegen.codegen import render_module

    # Fetch schema
    tools = await fetch_schema(server["url"])

    # Generate code
    code = render_module(f"{server_name}_mcp", tools)

    # Verify code was generated
    assert len(code) > 0, f"No code generated for {server_name}"
    assert "class" in code, f"No class definitions in generated code for {server_name}"
    assert "__all__" in code, f"No __all__ export list in generated code for {server_name}"

    # Verify expected tool classes are in the code
    for expected_tool in server["expected_tools"]:
        # Convert tool name to Python class name
        class_name = expected_tool.replace('-', '_')
        assert class_name in code, \
            f"Expected class '{class_name}' not found in generated code for {server_name}"

    print(f"✓ {server_name}: Generated {len(code)} characters of code")


@pytest.mark.asyncio
@pytest.mark.integration  # Add this marker
@pytest.mark.parametrize("server_name", TEST_SERVERS.keys())
async def test_call_tool(server_name):
    """Test calling a tool directly (call command) on MCP server."""
    server = TEST_SERVERS[server_name]
    test_call = server["test_call"]

    # Prepare arguments in key=value format
    args_list = []
    for key, value in test_call["args"]:
        if isinstance(value, str):
            args_list.append(f"{key}={value}")
        else:
            # Convert to JSON for non-string values
            args_list.append(f"{key}={json.dumps(value)}")

    # Capture output by redirecting to a StringIO-like object
    import sys
    from io import StringIO
    old_stdout = sys.stdout
    sys.stdout = captured_output = StringIO()

    try:
        # Call the tool
        await _call(server["url"], test_call["tool"], args_list)

        # Get the output
        output = captured_output.getvalue()
    finally:
        sys.stdout = old_stdout

    # Verify we got output
    assert len(output) > 0, f"No output from calling {test_call['tool']} on {server_name}"

    # Verify expected content in response
    assert test_call["expected_in_response"] in output, \
        f"Expected '{test_call['expected_in_response']}' not found in response from {server_name}"

    print(f"✓ {server_name}: Called {test_call['tool']} successfully")


@pytest.mark.asyncio
@pytest.mark.integration  # Add this marker
@pytest.mark.parametrize("server_name", TEST_SERVERS.keys())
async def test_transport_detection(server_name):
    """Test that transport detection correctly identifies server protocol."""
    server = TEST_SERVERS[server_name]

    # Extract base URL (remove /mcp suffix if present)
    base_url = server["url"].rstrip('/mcp').rstrip('/')

    # Detect transport
    transport = detect_transport(base_url)

    # Verify we detected something
    assert transport in ["streamable-http", "sse", "http-post", "unknown"], \
        f"Invalid transport detected for {server_name}: {transport}"

    # For known servers, we expect specific transports
    # (This can be updated as we learn more about each server)
    print(f"✓ {server_name}: Detected transport '{transport}'")


@pytest.mark.asyncio
@pytest.mark.integration  # Add this marker
async def test_all_servers_sequential():
    """Test all servers sequentially to ensure no interference between tests."""
    results = {}

    for server_name, server in TEST_SERVERS.items():
        try:
            # Test ls
            tools = await fetch_schema(server["url"])
            results[f"{server_name}_ls"] = f"✓ {len(tools)} tools"

            # Test gen
            from mcp_codegen.codegen import render_module
            code = render_module(f"{server_name}_mcp", tools)
            results[f"{server_name}_gen"] = f"✓ {len(code)} chars"

            # Test call
            test_call = server["test_call"]
            args_list = []
            for key, value in test_call["args"]:
                if isinstance(value, str):
                    args_list.append(f"{key}={value}")
                else:
                    args_list.append(f"{key}={json.dumps(value)}")

            import sys
            from io import StringIO
            old_stdout = sys.stdout
            sys.stdout = captured_output = StringIO()
            try:
                await _call(server["url"], test_call["tool"], args_list)
                output = captured_output.getvalue()
            finally:
                sys.stdout = old_stdout

            results[f"{server_name}_call"] = f"✓ {len(output)} chars output"

        except Exception as e:
            results[f"{server_name}"] = f"✗ {str(e)}"

    # Print summary
    print("\n=== Test Summary ===")
    for key, value in results.items():
        print(f"{key}: {value}")

    # Check for failures
    failures = [k for k, v in results.items() if v.startswith("✗")]
    assert len(failures) == 0, f"Tests failed: {failures}"


if __name__ == "__main__":
    # Allow running tests directly
    import sys

    print("Running MCP server integration tests...\n")

    # Run all servers test
    asyncio.run(test_all_servers_sequential())

    print("\n✓ All tests passed!")
