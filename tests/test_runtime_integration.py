"""Integration tests for runtime module features mentioned in README.

Tests for search_tools and other runtime utilities documented in the README.
"""
import sys
import tempfile
import shutil
from pathlib import Path

import pytest
import pytest_asyncio

from mcp_codegen.codegen import fetch_schema, generate_fs_layout_wrapper
from mcp_codegen.runtime import search_tools


# Test server configuration
TEST_SERVER_URL = "https://smhi-mcp.hakan-3a6.workers.dev"


@pytest.fixture
def temp_servers_dir():
    """Create temporary directory for generated servers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest_asyncio.fixture
async def weather_schema():
    """Fetch weather schema from test server."""
    return await fetch_schema(TEST_SERVER_URL)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_tools_basic(temp_servers_dir, weather_schema):
    """Test Example #3: Basic tool search functionality.

    From README:
        from mcp_codegen.runtime import search_tools
        tools = search_tools("weather forecast")
        for tool in tools:
            print(f"{tool.server}/{tool.tool}")
            print(f"  {tool.summary}")
    """
    # Step 1: Generate filesystem layout (search needs this)
    generate_fs_layout_wrapper(
        TEST_SERVER_URL,
        "weather",
        weather_schema,
        str(temp_servers_dir)
    )

    # Create servers directory structure
    servers_dir = temp_servers_dir / "servers"
    servers_dir.mkdir(exist_ok=True)
    shutil.copytree(temp_servers_dir / "weather", servers_dir / "weather", dirs_exist_ok=True)

    # Step 2: Search for tools
    tools = search_tools("weather", servers_dir=str(servers_dir))

    # Step 3: Verify search results
    assert len(tools) > 0, "No tools found matching 'weather'"

    # Step 4: Verify tool attributes
    for tool in tools:
        assert hasattr(tool, "server"), "ToolRef missing 'server' attribute"
        assert hasattr(tool, "tool"), "ToolRef missing 'tool' attribute"
        assert hasattr(tool, "summary"), "ToolRef missing 'summary' attribute"
        assert hasattr(tool, "module_path"), "ToolRef missing 'module_path' attribute"

        assert tool.server == "weather", f"Wrong server: {tool.server}"
        assert isinstance(tool.tool, str), "Tool name should be string"
        assert len(tool.tool) > 0, "Tool name is empty"
        assert isinstance(tool.summary, str), "Summary should be string"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_tools_specific_query(temp_servers_dir, weather_schema):
    """Test searching for specific tools by name."""
    # Generate filesystem layout
    generate_fs_layout_wrapper(
        TEST_SERVER_URL,
        "weather",
        weather_schema,
        str(temp_servers_dir)
    )

    # Create servers directory structure
    servers_dir = temp_servers_dir / "servers"
    servers_dir.mkdir(exist_ok=True)
    shutil.copytree(temp_servers_dir / "weather", servers_dir / "weather", dirs_exist_ok=True)

    # Search for specific tool
    tools = search_tools("forecast", servers_dir=str(servers_dir))

    assert len(tools) > 0, "No tools found matching 'forecast'"

    # Verify we got the right tool
    tool_names = [t.tool for t in tools]
    assert "get_weather_forecast" in tool_names, "get_weather_forecast not in results"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_tools_load_method(temp_servers_dir, weather_schema):
    """Test Example #3: ToolRef.load() method.

    From README:
        tools = search_tools("weather")
        for tool in tools:
            module = tool.load()
            result = await module.call(base_url, module.Params(...))
    """
    # Generate filesystem layout
    generate_fs_layout_wrapper(
        TEST_SERVER_URL,
        "weather",
        weather_schema,
        str(temp_servers_dir)
    )

    # Create servers directory structure
    servers_dir = temp_servers_dir / "servers"
    servers_dir.mkdir(exist_ok=True)
    shutil.copytree(temp_servers_dir / "weather", servers_dir / "weather", dirs_exist_ok=True)

    # Add to sys.path so imports work
    sys.path.insert(0, str(temp_servers_dir))
    try:
        # Search for tools
        tools = search_tools("weather", servers_dir=str(servers_dir))

        assert len(tools) > 0, "No tools found"

        # Test load() on first tool
        first_tool = tools[0]
        module = first_tool.load()

        # Verify loaded module has required attributes
        assert module is not None, "Failed to load module"
        assert hasattr(module, "Params"), "Loaded module missing Params class"
        assert hasattr(module, "call"), "Loaded module missing call function"

        # If it's get_weather_forecast, we can test calling it
        if first_tool.tool == "get_weather_forecast":
            params = module.Params(lat=64.75, lon=20.95, limit=1)
            result = await module.call(TEST_SERVER_URL, params)
            assert result is not None, "Tool call returned None"

    finally:
        sys.path.remove(str(temp_servers_dir))
        # Clean up modules
        modules_to_remove = [m for m in sys.modules if m.startswith("servers")]
        for mod in modules_to_remove:
            del sys.modules[mod]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_tools_no_results(temp_servers_dir, weather_schema):
    """Test search with query that returns no results."""
    # Generate filesystem layout
    generate_fs_layout_wrapper(
        TEST_SERVER_URL,
        "weather",
        weather_schema,
        str(temp_servers_dir)
    )

    # Create servers directory structure
    servers_dir = temp_servers_dir / "servers"
    servers_dir.mkdir(exist_ok=True)
    shutil.copytree(temp_servers_dir / "weather", servers_dir / "weather", dirs_exist_ok=True)

    # Search for something that doesn't exist
    tools = search_tools("nonexistent_tool", servers_dir=str(servers_dir))

    # Should return empty list, not error
    assert isinstance(tools, list), "search_tools should return list"
    assert len(tools) == 0, "Should return empty list for no matches"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_tools_multiple_servers(temp_servers_dir, weather_schema):
    """Test searching across multiple generated servers.

    Simulates having multiple servers in servers/ directory.
    """
    # Generate first server
    generate_fs_layout_wrapper(
        TEST_SERVER_URL,
        "weather",
        weather_schema,
        str(temp_servers_dir)
    )

    # Create servers directory structure
    servers_dir = temp_servers_dir / "servers"
    servers_dir.mkdir(exist_ok=True)
    shutil.copytree(temp_servers_dir / "weather", servers_dir / "weather", dirs_exist_ok=True)

    # Search across all servers
    tools = search_tools("temperature", servers_dir=str(servers_dir))

    # Should find temperature-related tools
    tool_names = [t.tool for t in tools]
    assert any("temperature" in name or "temp" in name for name in tool_names), \
        "Should find temperature-related tools"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_client_import_from_runtime(temp_servers_dir, weather_schema):
    """Test that Client can be imported from mcp_codegen.runtime.

    This is used by generated fs-layout code:
        from mcp_codegen.runtime.client import Client
    """
    # Verify Client is importable from runtime
    from mcp_codegen.runtime import Client

    assert Client is not None, "Client should be importable from runtime"
    assert hasattr(Client, "__aenter__"), "Client should support async context manager"
    assert hasattr(Client, "__aexit__"), "Client should support async context manager"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_client_direct_import(temp_servers_dir, weather_schema):
    """Test that Client can be imported directly from runtime.client.

    This is what the fs-layout generated code uses:
        from mcp_codegen.runtime.client import Client
    """
    from mcp_codegen.runtime.client import Client

    assert Client is not None, "Client should be importable from runtime.client"

    # Test instantiation
    client = Client(TEST_SERVER_URL)
    assert client is not None, "Should be able to instantiate Client"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
