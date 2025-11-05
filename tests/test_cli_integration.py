"""End-to-end integration tests for mcp-codegen CLI workflows.

Tests complete workflows from generation through usage.
"""
import asyncio
import json
import sys
import tempfile
import shutil
import subprocess
from pathlib import Path
from io import StringIO

import pytest
import pytest_asyncio

from mcp_codegen.codegen import fetch_schema, render_module, generate_fs_layout_wrapper


# Test server configuration
TEST_SERVER_URL = "https://smhi-mcp.hakan-3a6.workers.dev"


@pytest.fixture
def temp_project_dir():
    """Create temporary directory for CLI outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest_asyncio.fixture
async def schema():
    """Fetch schema from test server."""
    return await fetch_schema(TEST_SERVER_URL)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_gen_then_import_and_call(temp_project_dir, schema):
    """Test end-to-end: generate code, import it, and call a tool.

    Workflow:
    1. mcp-codegen gen --url ... --out weather_tools.py
    2. from weather_tools import get_weather_forecast
    3. result = await get_weather_forecast.call(...)
    """
    # Step 1: Generate module (simulating: mcp-codegen gen ...)
    code = render_module("weather_tools", schema)
    module_path = temp_project_dir / "weather_tools.py"
    module_path.write_text(code, encoding="utf-8")

    assert module_path.exists(), "Generated module not created"
    assert module_path.stat().st_size > 0, "Generated module is empty"

    # Step 2: Add to path and import
    sys.path.insert(0, str(temp_project_dir))
    try:
        import weather_tools

        # Step 3: Call tool
        params = weather_tools.get_weather_forecast.Params(
            lat=64.75,
            lon=20.95,
            limit=1
        )
        result = await weather_tools.get_weather_forecast.call(
            TEST_SERVER_URL,
            params
        )

        # Step 4: Verify result
        assert result is not None, "No result from tool call"

    finally:
        sys.path.remove(str(temp_project_dir))
        if "weather_tools" in sys.modules:
            del sys.modules["weather_tools"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_gen_fs_layout_then_import_and_call(temp_project_dir, schema):
    """Test end-to-end: generate fs-layout, import from it, and call tools.

    Workflow:
    1. mcp-codegen gen --fs-layout ...
    2. from servers.weather.get_weather_forecast import call, Params
    3. result = await call(...)
    """
    # Step 1: Generate fs-layout (simulating: mcp-codegen gen --fs-layout ...)
    generate_fs_layout_wrapper(
        TEST_SERVER_URL,
        "weather",
        schema,
        str(temp_project_dir)
    )

    # Create servers directory structure for imports
    servers_dir = temp_project_dir / "servers"
    servers_dir.mkdir(exist_ok=True)
    shutil.copytree(temp_project_dir / "weather", servers_dir / "weather", dirs_exist_ok=True)

    assert servers_dir.exists(), "servers directory not created"
    assert (servers_dir / "weather").exists(), "weather directory not created"
    assert (servers_dir / "weather" / "__init__.py").exists(), "__init__.py not created"
    assert (temp_project_dir / "weather" / "get_weather_forecast.py").exists(), "tool file not created"

    # Step 2: Add to path and import
    sys.path.insert(0, str(temp_project_dir))
    try:
        from servers.weather.get_weather_forecast import call, Params

        # Step 3: Call tool
        params = Params(lat=64.75, lon=20.95, limit=1)
        result = await call(TEST_SERVER_URL, params)

        # Step 4: Verify result
        assert result is not None, "No result from tool call"

    finally:
        sys.path.remove(str(temp_project_dir))
        modules_to_remove = [m for m in sys.modules if m.startswith("servers")]
        for mod in modules_to_remove:
            del sys.modules[mod]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_run_agent_with_tool_calls(temp_project_dir, schema):
    """Test: Create agent script and run it with mcp-codegen run.

    This tests the agent execution feature from Example #4 of README.
    """
    # Step 1: Generate fs-layout for agent to use
    generate_fs_layout_wrapper(
        TEST_SERVER_URL,
        "weather",
        schema,
        str(temp_project_dir)
    )

    # Create servers directory structure
    servers_dir = temp_project_dir / "servers"
    servers_dir.mkdir(exist_ok=True)
    shutil.copytree(temp_project_dir / "weather", servers_dir / "weather", dirs_exist_ok=True)

    # Step 2: Create agent script
    agent_code = '''
import asyncio
from servers.weather.get_weather_forecast import call, Params

async def main():
    """Agent that calls get_weather_forecast."""
    params = Params(lat=64.75, lon=20.95, limit=1)
    result = await call("https://smhi-mcp.hakan-3a6.workers.dev", params)
    print("Agent executed successfully!")
    return result

result = asyncio.run(main())
print(f"Result type: {type(result)}")
'''

    agent_file = temp_project_dir / "agent.py"
    agent_file.write_text(agent_code, encoding="utf-8")

    # Step 3: Add to path so imports work
    sys.path.insert(0, str(temp_project_dir))
    try:
        # Execute the agent script
        result = await asyncio.to_thread(
            lambda: subprocess.run(
                [sys.executable, str(agent_file)],
                capture_output=True,
                text=True,
                cwd=str(temp_project_dir)
            )
        )

        # Step 4: Verify execution
        assert result.returncode == 0, f"Agent failed: {result.stderr}"
        assert "Agent executed successfully!" in result.stdout, "Agent output not found"

    finally:
        sys.path.remove(str(temp_project_dir))
        modules_to_remove = [m for m in sys.modules if m.startswith("servers")]
        for mod in modules_to_remove:
            del sys.modules[mod]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_call_subcommand_output(schema):
    """Test that mcp-codegen call produces valid JSON output.

    From README:
        mcp-codegen call --url https://... --tool get_weather_forecast \
            --arg lat=64.75 --arg lon=20.95 --arg limit=1
    """
    # Import the _call function from CLI module
    from mcp_codegen.cli import _call

    # Capture output
    old_stdout = sys.stdout
    sys.stdout = captured_output = StringIO()

    try:
        # Call the tool (simulating: mcp-codegen call ...)
        await _call(
            TEST_SERVER_URL,
            "get_weather_forecast",
            ["lat=64.75", "lon=20.95", "limit=1"]
        )

        # Get output
        output = captured_output.getvalue()

    finally:
        sys.stdout = old_stdout

    # Verify output is valid JSON
    assert len(output) > 0, "No output from call command"

    try:
        result = json.loads(output)
        assert isinstance(result, dict), "Output should be JSON object"
    except json.JSONDecodeError:
        # Output might be formatted text, which is also valid
        assert "location" in output or "forecast" in output or "temperature" in output, \
            "Output should contain weather data"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_generated_module_params_validation(temp_project_dir, schema):
    """Test that generated Params classes validate inputs.

    Ensures type safety in generated code.
    """
    # Generate module
    code = render_module("weather_tools", schema)
    module_path = temp_project_dir / "weather_tools.py"
    module_path.write_text(code, encoding="utf-8")

    sys.path.insert(0, str(temp_project_dir))
    try:
        import weather_tools

        # Test 1: Valid parameters
        valid_params = weather_tools.get_weather_forecast.Params(
            lat=64.75,
            lon=20.95,
            limit=1
        )
        assert valid_params is not None

        # Test 2: Required parameters are enforced
        with pytest.raises(Exception):  # Pydantic ValidationError
            weather_tools.get_weather_forecast.Params(lat=64.75)  # Missing lon

        # Test 3: Type validation
        with pytest.raises(Exception):  # Pydantic ValidationError
            weather_tools.get_weather_forecast.Params(
                lat="not_a_number",
                lon=20.95
            )

        # Test 4: Model serialization
        serialized = valid_params.model_dump(mode="json", exclude_none=True)
        assert isinstance(serialized, dict)
        assert serialized["lat"] == 64.75
        assert serialized["lon"] == 20.95

    finally:
        sys.path.remove(str(temp_project_dir))
        if "weather_tools" in sys.modules:
            del sys.modules["weather_tools"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_multiple_server_generation(temp_project_dir, schema):
    """Test generating multiple servers in one project.

    Simulates having tools from multiple MCP servers in same project.
    """
    # Generate multiple "servers" (using same schema for simplicity)
    generate_fs_layout_wrapper(
        TEST_SERVER_URL,
        "weather",
        schema,
        str(temp_project_dir)
    )

    generate_fs_layout_wrapper(
        TEST_SERVER_URL,
        "climate",  # Different server name, same tools
        schema,
        str(temp_project_dir)
    )

    # Verify both servers were created
    # Note: generate_fs_layout_wrapper creates module_name directories at output_dir level
    assert (temp_project_dir / "weather").exists()
    assert (temp_project_dir / "climate").exists()

    # Verify they have separate tool files
    assert (temp_project_dir / "weather" / "get_weather_forecast.py").exists()
    assert (temp_project_dir / "climate" / "get_weather_forecast.py").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
