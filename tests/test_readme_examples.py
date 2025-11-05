"""Integration tests for README.md Python code examples.

Tests that all code examples shown in README.md actually work as documented.
These tests verify the complete user experience and catch regressions.
"""
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from io import StringIO

import pytest
import pytest_asyncio

from mcp_codegen.codegen import fetch_schema, render_module, generate_fs_layout_wrapper


# Test server configuration
TEST_SERVER_URL = "https://smhi-mcp.hakan-3a6.workers.dev"
TEST_TOOL_NAME = "get_weather_forecast"
TEST_TOOL_PARAMS = {"lat": 64.75, "lon": 20.95, "limit": 1}


@pytest.fixture
def temp_module_dir():
    """Create a temporary directory for generated modules."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest_asyncio.fixture
async def schema():
    """Fetch schema from test server."""
    return await fetch_schema(TEST_SERVER_URL)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_single_file_module_usage(temp_module_dir, schema):
    """Test Example #1: Single-file module generation and usage.

    From README:
        from weather_tools import get_weather_forecast
        params = get_weather_forecast.Params(lat=64.75, lon=20.95, limit=1)
        result = await get_weather_forecast.call('https://...', params)
    """
    # Step 1: Generate single-file module
    code = render_module("weather_tools", schema)
    module_path = temp_module_dir / "weather_tools.py"
    module_path.write_text(code, encoding="utf-8")

    # Step 2: Add temp_module_dir to sys.path so we can import it
    sys.path.insert(0, str(temp_module_dir))
    try:
        # Step 3: Import the generated module
        import weather_tools

        # Step 4: Create Params object with type hints
        params = weather_tools.get_weather_forecast.Params(
            lat=64.75,
            lon=20.95,
            limit=1
        )

        # Step 5: Call the tool
        result = await weather_tools.get_weather_forecast.call(
            TEST_SERVER_URL,
            params
        )

        # Step 6: Verify result structure
        assert result is not None
        assert isinstance(result, (str, dict))

        # If string, it should be the response text
        if isinstance(result, str):
            assert len(result) > 0
        # If dict, verify it has expected keys
        elif isinstance(result, dict):
            assert "location" in result or "forecast" in result or "temperature" in result

    finally:
        sys.path.remove(str(temp_module_dir))
        # Clean up imported module
        if "weather_tools" in sys.modules:
            del sys.modules["weather_tools"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fs_layout_import_pattern(temp_module_dir, schema):
    """Test Example #2: Filesystem layout import and usage.

    From README:
        from servers.weather.get_weather_forecast import call, Params
        result = await call('https://...', Params(lat=64.75, lon=20.95))
    """
    # Step 1: Generate filesystem layout
    # Creates temp_module_dir/weather/ with tools inside
    generate_fs_layout_wrapper(TEST_SERVER_URL, "weather", schema, str(temp_module_dir))

    # Verify directory structure was created
    weather_dir = temp_module_dir / "weather"
    assert weather_dir.exists(), "weather subdirectory not created"

    tool_file = weather_dir / "get_weather_forecast.py"
    assert tool_file.exists(), "tool file not created"

    # Step 2: Create servers directory structure for imports to work
    servers_dir = temp_module_dir / "servers"
    servers_dir.mkdir(exist_ok=True)
    import shutil
    shutil.copytree(weather_dir, servers_dir / "weather", dirs_exist_ok=True)

    # Step 3: Add to sys.path
    sys.path.insert(0, str(temp_module_dir))
    try:
        # Step 4: Import from fs-layout
        from servers.weather.get_weather_forecast import call, Params

        # Step 4: Create Params and call tool
        params = Params(lat=64.75, lon=20.95, limit=1)
        result = await call(TEST_SERVER_URL, params)

        # Step 5: Verify result
        assert result is not None
        assert isinstance(result, (str, dict))

    finally:
        sys.path.remove(str(temp_module_dir))
        # Clean up imported modules
        modules_to_remove = [m for m in sys.modules if m.startswith("servers")]
        for mod in modules_to_remove:
            del sys.modules[mod]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_tools_with_load(temp_module_dir, schema):
    """Test Example #3: Tool search with .load() and .call().

    From README:
        from mcp_codegen.runtime import search_tools
        tools = search_tools("weather forecast")
        for tool in tools:
            module = tool.load()
            result = await module.call(base_url, module.Params(...))
    """
    # Step 1: Generate filesystem layout (search needs this)
    generate_fs_layout_wrapper(TEST_SERVER_URL, "weather", schema, str(temp_module_dir))

    # Step 2: Create servers directory structure
    import shutil
    servers_dir = temp_module_dir / "servers"
    servers_dir.mkdir(exist_ok=True)
    shutil.copytree(temp_module_dir / "weather", servers_dir / "weather", dirs_exist_ok=True)

    # Step 3: Add to sys.path for imports
    sys.path.insert(0, str(temp_module_dir))
    try:
        # Step 4: Import search_tools
        from mcp_codegen.runtime import search_tools

        # Step 5: Search for tools
        found_tools = search_tools("weather", servers_dir=str(servers_dir))

        assert len(found_tools) > 0, "No tools found in search"

        # Step 5: Test loading and calling tools
        for tool_ref in found_tools[:1]:  # Test first result
            # Verify tool_ref attributes
            assert hasattr(tool_ref, "server"), "ToolRef missing 'server' attribute"
            assert hasattr(tool_ref, "tool"), "ToolRef missing 'tool' attribute"
            assert tool_ref.server == "weather", "Wrong server name"

            # Load the tool module
            module = tool_ref.load()
            assert module is not None, "Failed to load tool"
            assert hasattr(module, "Params"), "Loaded module missing Params class"
            assert hasattr(module, "call"), "Loaded module missing call function"

            # Create params for get_weather_forecast if that's what we loaded
            if tool_ref.tool == "get_weather_forecast":
                params = module.Params(lat=64.75, lon=20.95, limit=1)
                result = await module.call(TEST_SERVER_URL, params)
                assert result is not None, "Tool call returned None"

    finally:
        sys.path.remove(str(temp_module_dir))
        # Clean up
        modules_to_remove = [m for m in sys.modules if m.startswith("servers")]
        for mod in modules_to_remove:
            del sys.modules[mod]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_multiple_tool_imports(temp_module_dir, schema):
    """Test Example #6: Multiple tool imports and chained calls.

    From README:
        from github_tools import create_pr, list_repos
        async def deploy_pr():
            repos = await list_repos.call(base_url, list_repos.Params())
            for repo in repos:
                pr = await create_pr.call(base_url, create_pr.Params(...))
    """
    # Generate module with multiple tools
    code = render_module("weather_tools", schema)
    module_path = temp_module_dir / "weather_tools.py"
    module_path.write_text(code, encoding="utf-8")

    sys.path.insert(0, str(temp_module_dir))
    try:
        # Import multiple tools from the same module
        import weather_tools

        # Verify multiple tool classes are available
        assert hasattr(weather_tools, "get_weather_forecast")
        assert hasattr(weather_tools, "list_snowmobile_conditions")

        # Test calling multiple tools
        params1 = weather_tools.get_weather_forecast.Params(
            lat=64.75, lon=20.95, limit=1
        )
        result1 = await weather_tools.get_weather_forecast.call(
            TEST_SERVER_URL, params1
        )
        assert result1 is not None

        # Call another tool
        params2 = weather_tools.list_snowmobile_conditions.Params()
        result2 = await weather_tools.list_snowmobile_conditions.call(
            TEST_SERVER_URL, params2
        )
        assert result2 is not None

    finally:
        sys.path.remove(str(temp_module_dir))
        if "weather_tools" in sys.modules:
            del sys.modules["weather_tools"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_generated_type_safety(temp_module_dir, schema):
    """Test Example #6: Type safety in generated code.

    Verify that generated Params classes enforce type hints via Pydantic.
    """
    code = render_module("weather_tools", schema)
    module_path = temp_module_dir / "weather_tools.py"
    module_path.write_text(code, encoding="utf-8")

    sys.path.insert(0, str(temp_module_dir))
    try:
        import weather_tools

        # Test 1: Required parameters are enforced
        with pytest.raises(Exception):  # Will raise Pydantic ValidationError
            params = weather_tools.get_weather_forecast.Params()  # Missing lat, lon

        # Test 2: Type checking is enforced
        with pytest.raises(Exception):  # Will raise Pydantic ValidationError
            params = weather_tools.get_weather_forecast.Params(
                lat="not_a_number",  # Should be float
                lon=20.95
            )

        # Test 3: Valid params work
        params = weather_tools.get_weather_forecast.Params(
            lat=64.75,
            lon=20.95,
            limit=1
        )
        assert params.lat == 64.75
        assert params.lon == 20.95
        assert params.limit == 1

        # Test 4: Optional parameters can be omitted
        params2 = weather_tools.get_weather_forecast.Params(
            lat=64.75,
            lon=20.95
            # limit is optional, can be omitted
        )
        assert params2.lat == 64.75

        # Test 5: Model serialization works
        dict_data = params.model_dump(mode="json", exclude_none=True)
        assert isinstance(dict_data, dict)
        assert "lat" in dict_data
        assert "lon" in dict_data

    finally:
        sys.path.remove(str(temp_module_dir))
        if "weather_tools" in sys.modules:
            del sys.modules["weather_tools"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_all_tools_accessible(schema):
    """Test that all tools from schema are accessible in generated code."""
    # Generate module
    code = render_module("all_tools", schema)

    # Verify all tool names appear as classes
    for tool in schema:
        # Tool names get converted to safe Python identifiers
        tool_name = tool.name.replace("-", "_")
        assert f"class {tool_name}" in code, f"Tool {tool.name} not found in generated code"
        assert f"def call(" in code, f"Tool {tool.name} missing call method"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
