"""Test runtime search functionality."""
import tempfile
from pathlib import Path
import sys
import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mcp_codegen.runtime.search import search_tools, list_servers, list_tools, ToolRef

def test_search_tools():
    """Test search_tools function."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a server structure
        server_dir = Path(tmpdir) / "github"
        server_dir.mkdir()
        (server_dir / "__init__.py").write_text('SERVER_TOOLS = []')
        (server_dir / "create_pr.py").write_text('"""Create a PR"""')

        tools = search_tools("create", servers_dir=tmpdir, detail="basic")

        assert len(tools) > 0
        assert any(t.tool == "create_pr" for t in tools)

def test_list_servers():
    """Test list_servers function."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create server directories
        (Path(tmpdir) / "server1").mkdir()
        (Path(tmpdir) / "server2").mkdir()
        (Path(tmpdir) / ".hidden").mkdir()  # Should be ignored

        servers = list_servers(tmpdir)

        assert "server1" in servers
        assert "server2" in servers
        assert ".hidden" not in servers

def test_list_tools():
    """Test list_tools function."""
    with tempfile.TemporaryDirectory() as tmpdir:
        server_dir = Path(tmpdir) / "github"
        server_dir.mkdir()
        (server_dir / "tool1.py").write_text("")
        (server_dir / "tool2.py").write_text("")
        (server_dir / "__init__.py").write_text("")

        tools = list_tools("github", tmpdir)

        assert "tool1" in tools
        assert "tool2" in tools

def test_tool_ref_get_summary():
    """Test ToolRef.get_summary() without loading."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tool_file = Path(tmpdir) / "test_tool.py"
        tool_file.write_text('"""Test tool for summarization."""\nfoo = 1')

        ref = ToolRef(
            server="test",
            tool="test_tool",
            module_path=str(tool_file)
        )

        summary = ref.get_summary()
        assert "Test tool" in summary
        assert not ref.loaded  # Should not have loaded the module

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
