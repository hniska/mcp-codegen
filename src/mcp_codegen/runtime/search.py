"""Tool discovery and progressive disclosure.

search_tools() enables finding MCP tools without loading full schemas,
matching Anthropic's "progressive disclosure" pattern.
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional, Literal
import importlib.util
import os
from pathlib import Path

DetailLevel = Literal["name", "basic", "full"]

class ToolRef:
    """Reference to a tool without loading full module.

    Attributes:
        server: Server name
        tool: Tool name
        module_path: Path to tool's Python file
        summary: Short description (from metadata or file header)
        loaded: Whether module has been imported
    """
    def __init__(
        self,
        server: str,
        tool: str,
        module_path: str,
        summary: str = ""
    ):
        self.server = server
        self.tool = tool
        self.module_path = module_path
        self.summary = summary
        self.loaded = False
        self._module = None

    def load(self) -> Any:
        """Load the tool module on demand."""
        if not self.loaded:
            spec = importlib.util.spec_from_file_location(f"{self.server}_{self.tool}", self.module_path)
            if spec and spec.loader:
                self._module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(self._module)
                self.loaded = True
        return self._module

    async def invoke(self, base_url: str, params: Any) -> Any:
        """Load and invoke the tool in one call (convenience method).

        Args:
            base_url: MCP server base URL
            params: Tool parameters

        Returns:
            Tool result
        """
        import asyncio
        mod = self.load()
        return await mod.call(base_url, params)

    def get_summary(self) -> str:
        """Extract summary from file header without loading module.

        Uses AST parsing to extract module docstring without executing code.
        More robust than regex, handles edge cases like encoding declarations.
        """
        if self.summary:
            return self.summary

        try:
            # Read only first 2KB to avoid parsing large files
            with open(self.module_path, 'r', encoding='utf-8') as f:
                content = f.read(2048)

            # Use AST to safely parse and extract docstring (no execution)
            import ast
            try:
                node = ast.parse(content)
                doc = ast.get_docstring(node)

                if doc:
                    # Extract summary from docstring (before first blank line or Params section)
                    lines = doc.split('\n')
                    summary_lines = []
                    for line in lines:
                        if line.strip() == '' or 'Params' in line:
                            break
                        summary_lines.append(line.strip())
                    self.summary = ' '.join(summary_lines)
            except SyntaxError:
                # Fallback to regex if AST parsing fails
                import re
                docstring_match = re.search(r'^\\s*"""(.+?)"""', content, re.DOTALL | re.MULTILINE)
                if docstring_match:
                    docstring = docstring_match.group(1).strip()
                    lines = docstring.split('\n')
                    summary_lines = []
                    for line in lines:
                        if line.strip() == '' or 'Params' in line:
                            break
                        summary_lines.append(line.strip())
                    self.summary = ' '.join(summary_lines)

        except Exception:
            pass  # Keep empty summary if parsing fails

        return self.summary

def search_tools(
    query: str,
    servers_dir: str = "servers",
    detail: DetailLevel = "name"
) -> List[ToolRef]:
    """Search for tools matching query.

    Args:
        query: Search query (matches server name, tool name, or summary)
        servers_dir: Base directory containing server folders
        detail: Level of detail to load ("name", "basic", "full")

    Returns:
        List of ToolRef objects matching the query

    Example:
        tools = search_tools("github create", detail="basic")
        for tool in tools:
            print(f"{tool.server}.{tool.tool}: {tool.summary}")

            # Load module on demand
            module = tool.load()
            if hasattr(module, 'Params'):
                print(f"  Params: {module.Params.__doc__}")

            # Or use convenience method for async calls
            result = await tool.invoke(base_url, module.Params(...))
    """
    results: List[ToolRef] = []

    servers_path = Path(servers_dir)
    if not servers_path.exists():
        return results

    # Search through server directories
    for server_dir in servers_path.iterdir():
        if not server_dir.is_dir() or server_dir.name.startswith('.'):
            continue

        server_name = server_dir.name

        # Check __init__.py for server metadata
        init_file = server_dir / "__init__.py"
        server_tools: List[Dict[str, Any]] = []
        if init_file.exists():
            try:
                # Try to load server metadata (if available)
                spec = importlib.util.spec_from_file_location(f"{server_name}_init", str(init_file))
                if spec and spec.loader:
                    init_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(init_module)
                    server_tools = getattr(init_module, 'SERVER_TOOLS', [])
            except Exception:
                pass  # Skip if can't load

        # Search through tool files
        for tool_file in server_dir.glob("*.py"):
            if tool_file.name == "__init__.py":
                continue

            tool_name = tool_file.stem

            # Check if matches query (server name, tool name always checked)
            query_lower = query.lower()
            if query_lower in server_name.lower() or query_lower in tool_name.lower():
                # Quick match without loading summary
                results.append(ToolRef(
                    server=server_name,
                    tool=tool_name,
                    module_path=str(tool_file),
                    summary=""  # Will be loaded on demand
                ))
                continue

            # For full/basic detail mode, check summary
            if detail in ("basic", "full"):
                # Create temporary ToolRef and extract summary
                temp_ref = ToolRef(
                    server=server_name,
                    tool=tool_name,
                    module_path=str(tool_file)
                )
                summary = temp_ref.get_summary()

                if query_lower in summary.lower():
                    results.append(temp_ref)

    return results

def list_servers(servers_dir: str = "servers") -> List[str]:
    """List all available servers.

    Args:
        servers_dir: Base directory containing server folders

    Returns:
        List of server names
    """
    servers_path = Path(servers_dir)
    if not servers_path.exists():
        return []

    return [
        d.name for d in servers_path.iterdir()
        if d.is_dir() and not d.name.startswith('.')
    ]

def list_tools(server: str, servers_dir: str = "servers") -> List[str]:
    """List all tools for a server.

    Args:
        server: Server name
        servers_dir: Base directory containing server folders

    Returns:
        List of tool names
    """
    server_path = Path(servers_dir) / server
    if not server_path.exists():
        return []

    tools = []
    for py_file in server_path.glob("*.py"):
        if py_file.name != "__init__.py":
            tools.append(py_file.stem)

    return tools
