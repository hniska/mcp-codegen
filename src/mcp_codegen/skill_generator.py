"""Generate Claude Code skills for MCP servers.

This module generates skill files that help Claude Code discover and use
generated MCP tools automatically.
"""
from __future__ import annotations
from pathlib import Path
from typing import List, Any


def generate_skill(
    server_name: str,
    server_url: str,
    tools: List[Any],
    output_dir: str = ".claude/skills"
) -> str:
    """Generate a Claude Code skill for an MCP server.

    Args:
        server_name: Name of the MCP server (e.g., "smhi", "trafikverket")
        server_url: URL of the MCP server
        tools: List of tool objects from fetch_schema
        output_dir: Directory to write skill files (default: .claude/skills)

    Returns:
        Path to the generated skill directory
    """
    # Create skill directory
    skill_dir = Path(output_dir) / f"mcp-{server_name}"
    skill_dir.mkdir(parents=True, exist_ok=True)

    # Generate description based on tool names and descriptions
    tool_categories = _categorize_tools(tools)
    description = _generate_description(server_name, tool_categories)

    # Generate skill content
    skill_content = _render_skill(server_name, server_url, tools, tool_categories)

    # Write SKILL.md
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(skill_content, encoding="utf-8")

    return str(skill_dir)


def _categorize_tools(tools: List[Any]) -> dict:
    """Categorize tools by common patterns in their names and descriptions.

    Returns:
        Dictionary mapping category names to tool lists
    """
    categories = {
        "weather": [],
        "traffic": [],
        "camera": [],
        "road": [],
        "location": [],
        "data": [],
        "other": []
    }

    for tool in tools:
        name = tool.name.lower()
        desc = (getattr(tool, 'description', '') or '').lower()

        # Categorize based on keywords
        if "weather" in name or "weather" in desc:
            categories["weather"].append(tool)
        elif "traffic" in name or "traffic" in desc:
            categories["traffic"].append(tool)
        elif "camera" in name or "camera" in desc:
            categories["camera"].append(tool)
        elif "road" in name or "road" in desc:
            categories["road"].append(tool)
        elif "location" in name or "near" in name or "geo" in name:
            categories["location"].append(tool)
        elif "get" in name or "list" in name or "search" in name:
            categories["data"].append(tool)
        else:
            categories["other"].append(tool)

    # Remove empty categories
    return {k: v for k, v in categories.items() if v}


def _generate_description(server_name: str, tool_categories: dict) -> str:
    """Generate a concise skill description with trigger words.

    Args:
        server_name: Name of the server
        tool_categories: Categorized tools

    Returns:
        Description string for the skill frontmatter (max 1024 chars)
    """
    # Start with server name
    desc_parts = [f"Access {server_name.upper()} MCP server tools"]

    # Add categories as trigger words
    category_desc = {
        "weather": "weather forecasts and conditions",
        "traffic": "traffic flow and incidents",
        "camera": "traffic cameras and images",
        "road": "road conditions and information",
        "location": "location-based queries",
        "data": "data retrieval and search"
    }

    active_categories = []
    for cat, tools in tool_categories.items():
        if cat in category_desc:
            active_categories.append(category_desc[cat])

    if active_categories:
        desc_parts.append(f"for {', '.join(active_categories)}")

    # Add activation clause
    desc_parts.append(f". Activates when user mentions {server_name}")

    # Add category keywords
    keywords = list(tool_categories.keys())
    if keywords:
        desc_parts.append(f" or asks about {', '.join(keywords[:4])}")

    desc_parts.append(". Tools located in servers/ directory.")

    return "".join(desc_parts)[:1024]  # Limit to 1024 chars


def _render_skill(
    server_name: str,
    server_url: str,
    tools: List[Any],
    tool_categories: dict
) -> str:
    """Render the complete SKILL.md content.

    Args:
        server_name: Name of the server
        server_url: URL of the server
        tools: List of all tools
        tool_categories: Categorized tools

    Returns:
        Complete SKILL.md content as a string
    """
    description = _generate_description(server_name, tool_categories)

    # Build tool list by category
    tools_section = []
    for category, category_tools in tool_categories.items():
        tools_section.append(f"### {category.title()} Tools\n")
        for tool in category_tools[:5]:  # Limit to 5 per category
            desc = getattr(tool, 'description', '') or ''
            tools_section.append(f"- `{tool.name}`: {desc[:100]}{'...' if len(desc) > 100 else ''}")
        if len(category_tools) > 5:
            tools_section.append(f"- ...and {len(category_tools) - 5} more {category} tools")
        tools_section.append("")

    tools_text = "\n".join(tools_section)

    # Generate example tool name for documentation
    example_tool = tools[0].name if tools else "example_tool"

    content = f"""---
name: mcp-{server_name}
description: {description}
---

# {server_name.upper()} MCP Server Tools

This skill provides access to the {server_name.upper()} MCP server tools.

## Server Information

- **Server Name:** {server_name}
- **Server URL:** `{server_url}`
- **Tools Location:** `servers/{server_name}/`
- **Import Server URL:** `from servers.{server_name} import SERVER_URL`

## Available Tools

{tools_text}

## Quick Start

### 1. Discover Tools

Search for relevant tools without loading schemas:

```python
from mcp_codegen.runtime import search_tools

# Find tools in this server
tools = search_tools("{server_name}")
for tool in tools:
    print(f"{{tool.server}}/{{tool.tool}}: {{tool.summary}}")
```

### 2. Import and Use a Tool

```python
from servers.{server_name}.{example_tool} import call, Params
from servers.{server_name} import SERVER_URL

# Create parameters
params = Params(...)  # Check tool file for required parameters

# Call the tool
result = await call(SERVER_URL, params)
```

### 3. Multi-Tool Workflows

Import multiple tools as needed:

```python
from servers.{server_name}.tool1 import call as tool1, Params as Params1
from servers.{server_name}.tool2 import call as tool2, Params as Params2
from servers.{server_name} import SERVER_URL

# Use tools
result1 = await tool1(SERVER_URL, Params1(...))
result2 = await tool2(SERVER_URL, Params2(...))
```

## Usage Pattern

When the user asks about {server_name}-related tasks:

1. **Search** for relevant tools: `search_tools("query")`
2. **Import** the specific tool: `from servers.{server_name}.tool_name import call, Params`
3. **Get server URL**: `from servers.{server_name} import SERVER_URL`
4. **Create params**: `params = Params(...)`
5. **Call tool**: `result = await call(SERVER_URL, params)`
6. **Present results** to the user

## Important Notes

- All tool calls are **async** - always use `await`
- Server URL is available as `SERVER_URL` in `servers.{server_name}.__init__`
- Each tool is a small standalone file (~1.5-2KB)
- Tools have full type hints and Pydantic parameter validation
- Check individual tool files for parameter documentation

## Tool Files

All tools are located in `servers/{server_name}/`:
- Each tool is a separate `.py` file
- Import only what you need for fast loading
- Tools are browsable and have inline documentation
"""

    return content


def generate_multi_server_skill(
    servers: List[tuple[str, str, List[Any]]],
    output_dir: str = ".claude/skills"
) -> str:
    """Generate a unified skill covering multiple MCP servers.

    Args:
        servers: List of (server_name, server_url, tools) tuples
        output_dir: Directory to write skill files

    Returns:
        Path to the generated skill directory
    """
    skill_dir = Path(output_dir) / "mcp-tools"
    skill_dir.mkdir(parents=True, exist_ok=True)

    # Collect all tool categories across servers
    all_categories = set()
    server_summaries = []

    for server_name, server_url, tools in servers:
        categories = _categorize_tools(tools)
        all_categories.update(categories.keys())
        tool_count = len(tools)
        server_summaries.append(
            f"- **{server_name}** ({tool_count} tools): {server_url}"
        )

    # Build description
    category_list = ", ".join(sorted(all_categories)[:6])
    description = f"Access multiple MCP servers for {category_list}. Activates when user asks about these topics or mentions server names. Tools in servers/ directory."

    # Build content
    servers_list = "\n".join(server_summaries)

    content = f"""---
name: mcp-tools
description: {description[:1024]}
---

# MCP Tools - Multi-Server Access

This skill provides unified access to multiple MCP servers.

## Available Servers

{servers_list}

## Quick Usage

### Search Across All Servers

```python
from mcp_codegen.runtime import search_tools

# Search across all servers
tools = search_tools("weather")
for tool in tools:
    print(f"{{tool.server}}/{{tool.tool}}")
```

### Use Tools from Specific Server

```python
# Import from specific server
from servers.server_name.tool_name import call, Params
from servers.server_name import SERVER_URL

result = await call(SERVER_URL, Params(...))
```

### Multi-Server Orchestration

```python
# Use tools from multiple servers
from servers.server1.tool1 import call as call1, Params as P1
from servers.server2.tool2 import call as call2, Params as P2
from servers.server1 import SERVER_URL as URL1
from servers.server2 import SERVER_URL as URL2

result1 = await call1(URL1, P1(...))
result2 = await call2(URL2, P2(...))
```

## Workflow

1. Search for tools: `search_tools("query")`
2. Import tool: `from servers.{'{server}'}.{'{tool}'} import call, Params`
3. Get URL: `from servers.{'{server}'} import SERVER_URL`
4. Call: `await call(SERVER_URL, Params(...))`
5. Present results

All tools are async, type-safe, and standalone.
"""

    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(content, encoding="utf-8")

    return str(skill_dir)
