"""Test filesystem layout generation."""
import tempfile
from pathlib import Path
import sys
import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mcp_codegen.fs_layout import generate_fs_layout

class MockSchema:
    """Mock schema for testing."""
    def __init__(self, properties=None, required=None):
        self.properties = properties or {}
        self.required = required or []

class MockTool:
    """Mock tool for testing."""
    def __init__(self, name, description, input_schema):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.protocol_version = "2025-06-18"

def test_generate_fs_layout():
    """Test generating per-tool files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tools = [
            MockTool("create_pr", "Create a PR", MockSchema({
                "title": {"type": "string"},
                "body": {"type": "string"}
            }, ["title"]))
        ]

        generate_fs_layout(
            base_url="http://example.com",
            module_name="github",
            tools=tools,
            output_dir=tmpdir
        )

        # Check directory structure
        github_dir = Path(tmpdir) / "github"
        assert github_dir.exists()
        assert (github_dir / "__init__.py").exists()
        assert (github_dir / "create_pr.py").exists()

        # Check __init__.py content
        init_content = (github_dir / "__init__.py").read_text()
        assert "github" in init_content
        assert "create_pr" in init_content

        # Check tool file content
        tool_content = (github_dir / "create_pr.py").read_text()
        assert "class Params" in tool_content
        assert "async def call" in tool_content
        assert "def call_sync" in tool_content

def test_generate_multiple_tools():
    """Test generating multiple tool files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tools = [
            MockTool("tool1", "First tool", MockSchema({}, [])),
            MockTool("tool2", "Second tool", MockSchema({}, [])),
            MockTool("tool3", "Third tool", MockSchema({}, [])),
        ]

        generate_fs_layout(
            base_url="http://example.com",
            module_name="server",
            tools=tools,
            output_dir=tmpdir
        )

        server_dir = Path(tmpdir) / "server"
        assert len(list(server_dir.glob("*.py"))) == 4  # 3 tools + __init__.py

        # Check all tools are exported in __init__.py
        init_content = (server_dir / "__init__.py").read_text()
        for tool in tools:
            assert tool.name in init_content

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
