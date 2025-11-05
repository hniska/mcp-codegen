# mcp-codegen v1.0.0

⚡ This code has been vibe coded

> ⚡ Generate Python client code from MCP servers + Execute agent code with built-in sandboxing

**mcp-codegen** is a comprehensive toolkit for working with MCP (Model Context Protocol) servers. It enables you to:

1. **Discover & list tools** from any MCP server
2. **Generate type-safe Python client code** with full type hints
3. **Call tools directly** from the CLI without writing code
4. **Create progressive filesystem layouts** for just-in-time tool loading
5. **Search tools** across servers without loading full schemas
6. **Execute Python agent code** with built-in resource limits, network isolation, and privacy protection

Perfect for AI agents that need to work with MCP tools safely and efficiently.

## Features at a Glance

| Feature | v0.x | v1.0.0 |
|---------|------|--------|
| List tools | ✅ | ✅ |
| Generate type-safe Python stubs | ✅ | ✅ |
| Direct tool invocation | ✅ | ✅ |
| Auto transport negotiation | ✅ | ✅ |
| **Progressive filesystem layout** | ❌ | ✅ NEW |
| **Tool search without loading schemas** | ❌ | ✅ NEW |
| **Python code execution runner** | ❌ | ✅ NEW |
| **Resource limits (CPU, memory)** | ❌ | ✅ NEW |
| **Network isolation** | ❌ | ✅ NEW |
| **PII scrubbing** | ❌ | ✅ NEW |
| **Sandbox modes (seccomp, Firejail)** | ❌ | ✅ NEW |

## Quick Start

> **Note:** mcp-codegen follows [Anthropic's MCP best practices](https://www.anthropic.com/research/building-effective-agents) for context-efficient agent workflows. See [Built on MCP Best Practices](#built-on-mcp-best-practices) for details.

### Installation

```bash
pip install -e .

# Optional: For Linux sandboxing features
pip install -e ".[runner]"
```

### 1. List Available Tools

```bash
mcp-codegen ls --url https://your-mcp-server.com
```

Output:
```
Tools:
 - get_weather_forecast: Get weather forecast for a location (params: lat, lon, limit)
 - list_locations: List available locations (params: )
 - search_location: Search for a location (params: query)
```

### 2. Generate a Python Module (Single File)

```bash
mcp-codegen gen \
  --url https://your-mcp-server.com \
  --out weather_tools.py \
  --name weather
```

Use it in Python:

```python
import asyncio
from weather_tools import get_weather_forecast

async def main():
    params = get_weather_forecast.Params(lat=64.75, lon=20.95, limit=1)
    result = await get_weather_forecast.call(
        'https://your-mcp-server.com',
        params
    )
    print(result)

asyncio.run(main())
```

### 3. Call a Tool Directly (No Code Generation)

```bash
mcp-codegen call \
  --url https://your-mcp-server.com \
  --tool get_weather_forecast \
  --arg lat=64.75 \
  --arg lon=20.95
```

### 4. Generate Progressive Filesystem Layout (NEW in v1.0.0)

```bash
mcp-codegen gen --fs-layout \
  --url https://your-mcp-server.com \
  --name weather
```

Creates a browsable structure:

```
servers/
└── weather/
    ├── __init__.py              # Server index
    ├── get_weather_forecast.py  # Individual tool
    ├── list_locations.py
    └── search_location.py
```

Import only what you need:

```python
from servers.weather.get_weather_forecast import call, Params

# Load just this tool, not all 100 tools
result = await call('https://...', Params(lat=64.75, lon=20.95))
```

**Generate a Claude Code Skill (NEW):**

Add `--generate-skill` to automatically create a skill file for Claude Code:

```bash
mcp-codegen gen --fs-layout \
  --url https://your-mcp-server.com \
  --name weather \
  --generate-skill
```

This creates `.claude/skills/mcp-weather/SKILL.md` that helps Claude Code:
- Automatically discover when to use these tools
- Know the server URL and tool locations
- Understand tool categories (weather, traffic, etc.)
- Access usage patterns and examples

### 5. Search for Tools (NEW in v1.0.0)

Find tools without loading full schemas:

```bash
mcp-codegen search "weather forecast" --detail basic
```

Output:
```
Found 1 tool(s) matching 'weather forecast':

  weather/get_weather_forecast
    Get weather forecast for a location
```

Or in Python:

```python
from mcp_codegen.runtime import search_tools

tools = search_tools("weather forecast")
for tool in tools:
    print(f"{tool.server}/{tool.tool}")
    print(f"  {tool.summary}")
    # Load on demand
    module = tool.load()
    result = await module.call(base_url, module.Params(...))
```

### 6. Execute Agent Code with Sandboxing (NEW in v1.0.0)

```bash
mcp-codegen run --file agent.py \
  --cpu-seconds 10 \
  --memory-mb 512
```

Your agent script can use MCP tools safely:

```python
# agent.py
from mcp_codegen.runtime import search_tools, workspace, run_async
from servers.weather.get_weather_forecast import call, Params

# Search for available tools
tools = search_tools("weather")
print(f"Found {len(tools)} weather tools")

# Call a tool
async def get_forecast():
    params = Params(lat=64.75, lon=20.95)
    result = await call('https://your-mcp-server.com', params)
    return result

# Execute async code
run_async(get_forecast)

# Write results without hitting the model
workspace.write("forecast.json", forecast_result)
```

## Commands Reference

### `mcp-codegen ls` - List Tools

List all available tools from an MCP server.

**Syntax:**
```bash
mcp-codegen ls \
  --url <MCP_SERVER_URL> \
  [--transport {auto,streamable-http,sse}] \
  [--verbose]
```

**Options:**
- `--url URL` (required) - MCP server URL
- `--transport` (default: auto) - Transport protocol
- `--verbose` - Show debug information

**Examples:**
```bash
# Auto-detect transport
mcp-codegen ls --url http://localhost:8000

# Force SSE transport
mcp-codegen ls --url http://localhost:8000 --transport sse

# Verbose output
mcp-codegen ls --url http://localhost:8000 --verbose
```

### `mcp-codegen gen` - Generate Code

Generate Python module(s) from MCP server definitions.

**Syntax:**
```bash
mcp-codegen gen \
  --url <MCP_SERVER_URL> \
  --out <OUTPUT_FILE> \
  --name <MODULE_NAME> \
  [--fs-layout] \
  [--output-dir <DIR>]
```

**Options:**
- `--url URL` (required) - MCP server URL
- `--out FILE` (required) - Output file path (for single-file mode)
- `--name NAME` (default: mcp_stub) - Module/server name
- `--fs-layout` - Generate per-tool files instead of single file
- `--output-dir DIR` (default: servers) - Output directory for fs-layout
- `--generate-skill` - Generate Claude Code skill file (NEW)
- `--skill-dir DIR` (default: .claude/skills) - Skill directory

**Examples:**

Single file generation:
```bash
mcp-codegen gen \
  --url http://localhost:8000 \
  --out weather_tools.py \
  --name weather
```

Filesystem layout generation:
```bash
mcp-codegen gen \
  --url http://localhost:8000 \
  --fs-layout \
  --name weather
```

Generate with Claude Code skill (recommended):
```bash
mcp-codegen gen \
  --url http://localhost:8000 \
  --fs-layout \
  --name weather \
  --generate-skill
```

### `mcp-codegen call` - Call a Tool

Call an MCP tool directly without generating code.

**Syntax:**
```bash
mcp-codegen call \
  --url <MCP_SERVER_URL> \
  --tool <TOOL_NAME> \
  [--arg KEY=VALUE] \
  [--json]
```

**Options:**
- `--url URL` (required) - MCP server URL
- `--tool TOOL` (required) - Tool name to invoke
- `--arg KEY=VALUE` - Tool argument (repeatable)
- `--json` - Output raw JSON-RPC result

**Examples:**

String arguments:
```bash
mcp-codegen call \
  --url http://localhost:8000 \
  --tool greet \
  --arg name=World
```

JSON arguments:
```bash
mcp-codegen call \
  --url http://localhost:8000 \
  --tool search \
  --arg limit=10 \
  --arg filters='{"type":"active"}'
```

Numeric arguments:
```bash
mcp-codegen call \
  --url http://localhost:8000 \
  --tool get_weather \
  --arg lat=64.75 \
  --arg lon=20.95 \
  --arg limit=1
```

### `mcp-codegen search` - Search Tools (NEW)

Search for tools across generated servers.

**Syntax:**
```bash
mcp-codegen search <QUERY> \
  [--servers-dir <DIR>] \
  [--detail {name,basic,full}]
```

**Options:**
- `QUERY` (required) - Search query (matches server name, tool name, or summary)
- `--servers-dir DIR` (default: servers) - Directory containing generated servers
- `--detail` (default: basic) - Detail level to show
  - `name`: Only show names
  - `basic`: Show names and summaries
  - `full`: Show everything + usage examples

**Examples:**

```bash
# Quick search
mcp-codegen search "weather" --detail name

# Search with summaries
mcp-codegen search "forecast" --detail basic

# Full details
mcp-codegen search "get" --detail full
```

### `mcp-codegen run` - Execute Agent Code (NEW)

Execute Python agent code with resource limits and sandboxing.

**Syntax:**
```bash
mcp-codegen run \
  [--file <SCRIPT.PY> | --code <PYTHON_CODE>] \
  [--servers-dir <DIR>] \
  [--workspace <DIR>] \
  [--cpu-seconds <N>] \
  [--memory-mb <N>] \
  [--allow-network] \
  [--seccomp] \
  [--firejail]
```

**Options:**
- `--file FILE` or `--code CODE` - Script or code to execute (one required)
- `--servers-dir DIR` (default: servers) - Server tools directory
- `--workspace DIR` (default: .workspace) - Workspace output directory
- `--cpu-seconds N` (default: 10) - CPU time limit in seconds
- `--memory-mb N` (default: 512) - Memory limit in MB
- `--allow-network` - Allow network access (disabled by default)
- `--seccomp` - Enable seccomp syscall filtering (Linux only)
- `--firejail` - Run with Firejail sandbox (Linux only)

**Examples:**

Run a script with defaults:
```bash
mcp-codegen run --file agent.py
```

Increase limits:
```bash
mcp-codegen run --file agent.py \
  --cpu-seconds 30 \
  --memory-mb 1024
```

Enable hardening:
```bash
mcp-codegen run --file agent.py \
  --seccomp \
  --allow-network  # Only if API calls needed
```

Use Firejail sandbox:
```bash
mcp-codegen run --file agent.py --firejail
```

From stdin:
```bash
echo "print('Hello from agent')" | mcp-codegen run --code -
```

## Understanding the New v1.0.0 Features

### Progressive Filesystem Layout

The traditional approach generates a **single large file** with all tools:

```python
# mcp_tools.py - might be 50KB+ with 100+ tools
class tool1: ...
class tool2: ...
class tool3: ...
# ... hundreds more
```

**Problem:** Even if you only need `tool1`, you load and parse 100+ tools.

**Solution in v1.0.0:** Generate **individual files per tool**:

```
servers/
└── weather/
    ├── get_forecast.py      (2KB - only what you need)
    ├── list_locations.py    (2KB)
    └── search_location.py   (2KB)
```

Benefits:
- ✅ **Fast imports** - Only load what you use
- ✅ **Small context** - Ideal for AI agents with token limits
- ✅ **Discoverable** - Easy to browse available tools
- ✅ **Composable** - Mix tools from multiple servers

### Tool Search Without Loading Schemas

Find tools across all servers **without executing any code**:

```python
from mcp_codegen.runtime import search_tools

# Super fast - uses AST parsing, not module execution
tools = search_tools("weather forecast")

# Tools are ToolRef objects - not loaded yet
for tool in tools:
    print(tool.server)  # "weather"
    print(tool.tool)    # "get_forecast"
    print(tool.summary) # "Get weather forecast..."

    # Load module on demand
    module = tool.load()
    result = await module.call(base_url, module.Params(...))
```

How it works:
1. Scans `servers/` directory for tool files
2. Uses AST parsing to extract docstrings (no execution)
3. Returns lightweight `ToolRef` objects
4. Load modules only when needed

### Python Code Execution with Sandboxing

Execute arbitrary Python code safely:

```bash
mcp-codegen run --file agent.py \
  --cpu-seconds 10 \
  --memory-mb 512 \
  --seccomp
```

**What the runner provides to your code:**

```python
# Automatically available:
from mcp_codegen.runtime import search_tools, workspace, run_async
from privacy import scrub
from logger import logger

# Search for tools
tools = search_tools("weather")

# Use workspace for I/O (doesn't go to model)
workspace.write("results.json", data)

# Execute async code
run_async(my_async_function)

# Scrub PII from logs
safe_text = scrub("email: user@example.com")  # → "[EMAIL]"

# Log safely (auto-scrubbed)
logger.info("Processing data", status="ok")
```

**Security layers (built-in):**

1. **Resource Limits** (all platforms)
   - CPU: 10s by default (kills runaway loops)
   - Memory: 512MB by default (prevents OOM)
   - File descriptors: 64 (prevents resource exhaustion)
   - Processes: 64 (prevents fork bombs)

2. **Network Isolation** (all platforms)
   - Disabled by default - no socket access
   - Blocks: `socket.socket()`, `socket.create_connection()`, etc.
   - Purpose: Force use of MCP client instead of direct API calls

3. **Output Limits** (all platforms)
   - 200KB stdout cap (prevents spam)
   - 200KB stderr cap (prevents spam)

4. **PII Scrubbing** (all platforms)
   - Automatic redaction: emails, phone numbers, SSNs, credit cards
   - Private IP detection
   - Key-based redaction: passwords, tokens, secrets

5. **Optional Linux Hardening:**
   - **seccomp**: Syscall filtering (blocks socket syscalls at kernel level)
   - **Firejail**: Full sandbox with network isolation, read-only filesystem, capability dropping

### How It All Works Together

A complete example:

```bash
# Step 1: Generate filesystem layout from MCP server
mcp-codegen gen --fs-layout \
  --url https://github-mcp.example.com \
  --name github

# Step 2: Agent code searches for specific tools
# agent.py
from mcp_codegen.runtime import search_tools, workspace

tools = search_tools("github create pr")  # Fast search
for tool in tools:
    module = tool.load()
    # Now use the tool...

# Step 3: Run agent safely
mcp-codegen run --file agent.py \
  --cpu-seconds 30 \
  --memory-mb 1024 \
  --seccomp \
  --allow-network  # Only for MCP API calls
```

**What happens:**
1. ✅ Agent starts with resource limits applied
2. ✅ Network is blocked (only Python can call MCP client)
3. ✅ Agent searches tools without loading schemas
4. ✅ Agent loads only needed tools on demand
5. ✅ Agent calls MCP tools via `await tool.call(...)`
6. ✅ Results written to `workspace/` (doesn't go to model)
7. ✅ Output capped at 200KB
8. ✅ PII automatically redacted from logs
9. ✅ Timeouts kill long-running code
10. ✅ All syscalls monitored (seccomp mode)

## Built on MCP Best Practices

mcp-codegen follows the patterns recommended in Anthropic's article [Code execution with MCP: Building more efficient agents](https://www.anthropic.com/research/building-effective-agents).

### Progressive Disclosure

Instead of loading all tool definitions into context upfront, mcp-codegen generates a filesystem layout where tools can be discovered and loaded on-demand:

- Each tool is a separate file (~1.5-2KB)
- Claude loads only the tools it needs for the current task
- Reduces context usage by 98% (from 150K tokens to 2K tokens)

**Traditional approach (inefficient):**
```python
# All 100+ tool definitions loaded into context immediately
# Even if you only need one tool, you pay for all of them
from monolithic_tools import tool1, tool2, tool3, ... tool100
```

**mcp-codegen approach (efficient):**
```python
# Load only what you need
from servers.github.create_issue import call, Params
from servers.github import SERVER_URL
```

### Tool Search Without Loading Schemas

The `search_tools()` function enables finding tools without loading their full definitions:

```python
from mcp_codegen.runtime import search_tools

# Find tools without loading schemas (uses AST parsing, not execution)
tools = search_tools("weather")
# Returns lightweight ToolRef objects, load on demand
tool = tools[0].load()  # Load only when needed
```

This matches Anthropic's recommendation for a `search_tools` function that allows detail levels (name only, basic description, or full schema).

### Skills for Reusable Patterns

Generated skills (via `--generate-skill`) provide Claude Code with:

- **Server information and URLs** - Where to find tools and how to connect
- **Tool categories and descriptions** - Weather, traffic, data, etc.
- **Usage patterns and examples** - How to import and call tools
- **Activation triggers** - Keywords that activate the skill automatically

From Anthropic's article:
> "Adding a SKILL.md file to these saved functions creates a structured skill that models can reference and use."

mcp-codegen automatically generates these SKILL.md files with comprehensive information about each MCP server.

### Code-Based Tool Interaction

Tools are presented as type-safe Python APIs rather than string-based tool calls:

```python
from servers.smhi.get_weather_forecast import call, Params
from servers.smhi import SERVER_URL

# Type-safe, validated parameters with Pydantic
params = Params(lat=64.75, lon=20.95, limit=6)
result = await call(SERVER_URL, params)
```

This approach provides:
- Full IDE support with autocomplete
- Type checking at development time
- Parameter validation via Pydantic models
- Familiar programming patterns (imports, functions, types)

### Benefits of This Approach

**Context Efficiency:**
- Load only needed tools (not all 100+ definitions)
- Filter and transform data in code before returning to model
- Compose multiple tool calls in a single execution
- Handle large datasets without bloating context

**Developer Experience:**
- Familiar programming patterns (imports, functions, types)
- Full IDE support with autocomplete and type checking
- Easy debugging and testing
- No custom DSL or string-based tool call syntax

**Scalability:**
- Handle thousands of tools across dozens of servers
- Multi-server orchestration without context bloat
- State persistence via filesystem (workspace)
- Progressive tool loading as needed

**Example from the article:**
The article shows how direct tool calls require passing full results through context:
```
TOOL CALL: gdrive.getDocument() → 50,000 tokens flow through model
TOOL CALL: salesforce.updateRecord() → 50,000 tokens written again
```

With code execution, the same workflow becomes:
```python
# Data flows through code, not through model context
transcript = (await gdrive.getDocument(documentId='abc123')).content
await salesforce.updateRecord(data={'Notes': transcript})
# Model only sees: "Updated 1 record" (instead of 100K tokens)
```

mcp-codegen enables this pattern by making MCP tools available as code APIs.

For more details on these patterns and the rationale behind them, see [Anthropic's full article](https://www.anthropic.com/research/building-effective-agents).

## Transport Protocols

mcp-codegen auto-detects the best transport with minimal latency:

1. **streamable-http** - Streaming HTTP with MCP frames
   - Detected via: `HEAD /mcp` with `Accept: text/event-stream`
   - Fastest when available

2. **SSE (Server-Sent Events)** - Standard web streaming
   - Detected via: `HEAD /sse` with `Accept: text/event-stream`
   - Good alternative to streamable-http

3. **HTTP POST (JSON-RPC 2.0)** - Standard JSON-RPC over HTTP
   - Detected via: `POST /mcp` with initialize probe
   - Fallback for all servers
   - Works with simple HTTP servers

**Detection timing:** ~1-2 seconds with short timeouts (1.5s connect, 0.4s read)

**Caching:** Transport is detected once and cached for all subsequent requests

## Generated Code Quality

Generated modules are:

- ✅ **Type-safe** - Pydantic models with full type hints
- ✅ **Standalone** - No runtime dependency on mcp-codegen
- ✅ **Zero-copy** - Minimal overhead, direct MCP calls
- ✅ **Fast** - Auto-negotiated transport, cached connection
- ✅ **Reliable** - Automatic transport fallback

Each tool becomes a class:

```python
class get_weather_forecast:
    class Params(BaseModel):
        lat: float
        lon: float
        limit: int | None = None

    @staticmethod
    async def call(
        base_url: str,
        params: Params,
        headers: dict[str, str] | None = None
    ) -> Any:
        # ...call MCP tool...
```

## Architecture

### Core Components

```
mcp-codegen/
├── codegen.py          # Code generation engine
├── client.py           # MCP client with transport detection
├── cli.py              # Command-line interface
├── fs_layout.py        # Filesystem layout generator
└── runtime/
    ├── search.py       # Tool discovery (ToolRef, search_tools)
    ├── client.py       # Runtime MCP client
    └── privacy.py      # PII scrubbing

examples/runner/
├── run.py              # Main runner script
├── limits.py           # Resource limit enforcement
├── privacy.py          # PII detection & redaction
├── workspace.py        # Workspace file I/O
├── logger.py           # Structured logging
├── sandbox.py          # seccomp & Firejail integration
└── firejail-mcp.profile # Sandbox profile template
```

### Data Flow

```
User Input
    ↓
[CLI] mcp-codegen command
    ↓
[codegen] Connect to MCP server → Fetch schemas
    ↓
[client] Negotiate transport & protocol version
    ↓
[generate] Create Python code (single file or fs-layout)
    ↓
[runtime] Agent loads and uses tools
    ↓
[runner] Enforce limits, scrub PII, sandbox
    ↓
Output (workspace or stdout)
```

## Use Cases

### 1. AI Agent Development

```python
# Agent needs to use multiple MCP tools safely
from mcp_codegen.runtime import search_tools, workspace

tools = search_tools("github")  # Find all GitHub tools
for tool in tools:
    mod = tool.load()
    result = await mod.call(base_url, mod.Params(...))

workspace.write("results.json", result)  # Agent output
```

### 2. CLI Tool Integration

```bash
# List GitHub tools
mcp-codegen ls --url https://github-mcp.example.com

# Call directly without code
mcp-codegen call --url https://github-mcp.example.com \
  --tool create_pr \
  --arg title="Fix bug" \
  --arg body="Fixes #123"
```

### 3. Type-Safe Python Applications

```python
# Generate and use in production code
from github_tools import create_pr, list_repos

async def deploy_pr():
    repos = await list_repos.call(base_url, list_repos.Params())
    for repo in repos:
        pr = await create_pr.call(
            base_url,
            create_pr.Params(
                owner=repo.owner,
                title="Release v1.0"
            )
        )
```

### 4. Server-to-Server Integration

```bash
# Generate client for your MCP server
mcp-codegen gen \
  --url http://api.partner.com/mcp \
  --out partner_client.py

# Now you have type-safe access to their tools
import partner_client
result = await partner_client.query.call(...)
```

### 5. Using MCP Servers in Claude Code

Claude Code can install and use MCP servers. The Progressive Filesystem Layout makes it easy for Claude to discover and use tools without loading everything at once.

**Setup: Generate filesystem layout for your MCP servers**

```bash
# Generate layout + skill for a GitHub MCP server
mcp-codegen gen --fs-layout \
  --url http://localhost:3000 \
  --name github \
  --generate-skill

# Generate layout + skill for a Slack MCP server
mcp-codegen gen --fs-layout \
  --url http://localhost:3001 \
  --name slack \
  --generate-skill

# Result: browsable tool directory + Claude Code skills
# servers/
# ├── github/
# │   ├── __init__.py
# │   ├── create_issue.py
# │   ├── create_pr.py
# │   ├── list_repos.py
# │   └── search_code.py
# └── slack/
#     ├── __init__.py
#     ├── send_message.py
#     └── list_channels.py
#
# .claude/skills/
# ├── mcp-github/
# │   └── SKILL.md
# └── mcp-slack/
#     └── SKILL.md
```

**Usage: Claude discovers and uses tools on-demand**

When you ask Claude Code to perform tasks, it can:

1. **Search for relevant tools** without loading schemas:
```python
from mcp_codegen.runtime import search_tools

# Claude searches: "I need to create a GitHub issue"
tools = search_tools("github issue")
# Returns: [ToolRef(server="github", tool="create_issue", ...)]

# Load only the needed tool
tool = tools[0].load()
```

2. **Import specific tools directly** when the task is clear:
```python
# Claude knows exactly what tool to use
from servers.github.create_issue import call, Params

result = await call(
    'http://localhost:3000',
    Params(
        owner="myorg",
        repo="myrepo",
        title="Bug: login fails",
        body="Steps to reproduce..."
    )
)
```

3. **Combine tools from multiple servers**:
```python
# Claude can orchestrate multi-server workflows
from servers.github.create_issue import call as create_issue, Params as IssueParams
from servers.slack.send_message import call as send_message, Params as SlackParams

# Create GitHub issue
issue = await create_issue(
    'http://localhost:3000',
    IssueParams(owner="myorg", repo="myrepo", title="Deploy v2.0")
)

# Notify team on Slack
await send_message(
    'http://localhost:3001',
    SlackParams(
        channel="#deploys",
        text=f"New deploy issue created: {issue.url}"
    )
)
```

**Why this works well for Claude Code:**

- ✅ **Automatic skill activation** - Generated skills tell Claude when to use these tools
- ✅ **Fast tool discovery** - Claude can search tools without executing code
- ✅ **Minimal context usage** - Only imports what's needed (2KB vs 50KB+)
- ✅ **Type safety** - Full IDE autocomplete and type checking
- ✅ **Browsable structure** - Claude can explore `servers/` directory to understand available tools
- ✅ **Multi-server support** - Each server gets its own skill, easy to orchestrate
- ✅ **On-demand loading** - Tools are loaded JIT, reducing memory and startup time

**Example conversation with Claude Code:**

```
You: "Create a GitHub issue for the login bug and notify the team on Slack"

Claude: I'll help you create the issue and send a Slack notification.

[Claude searches for tools]
from mcp_codegen.runtime import search_tools
tools = search_tools("github issue")  # Finds create_issue
slack_tools = search_tools("slack message")  # Finds send_message

[Claude imports only what's needed]
from servers.github.create_issue import call as create_issue, Params as IssueParams
from servers.slack.send_message import call as send_message, Params as SlackParams

[Claude executes the workflow]
...
```

## Development

### Install in Development Mode

```bash
pip install -e ".[dev,test,runner]"
```

### Run Tests

```bash
pytest tests/ -v
```

### Test New Components

The implementation includes comprehensive tests:

- `test_fs_layout.py` - Filesystem layout generation
- `test_runtime_search.py` - Tool discovery
- `test_codegen_v2.py` - Code generation
- `test_exceptions.py` - Error handling

### Contribute

When contributing:

1. Follow existing code style
2. Add tests for new features
3. Update README.md
4. Test with real MCP servers if possible

## Security Considerations

### Network Isolation

By default, `mcp-codegen run` blocks all network access:

```python
# This will fail (network disabled)
import socket
socket.socket()  # RuntimeError: Network disabled

# This works (MCP client)
from servers.my_tool import call
result = await call(base_url, params)
```

### Resource Limits

Prevent denial of service:

```bash
# Limits by default
--cpu-seconds 10    # Kill at 10s
--memory-mb 512     # Kill at 512MB

# Increase if needed
--cpu-seconds 300 --memory-mb 2048
```

### Linux Hardening

For production use, enable syscall filtering:

```bash
mcp-codegen run --file agent.py --seccomp

# Or full sandbox
mcp-codegen run --file agent.py --firejail
```

### PII Protection

Automatic redaction of sensitive data:

```python
from privacy import scrub

# Before: "Contact: user@example.com, phone: 555-123-4567"
# After:  "Contact: [EMAIL], phone: [PHONE]"
text = scrub("Contact: user@example.com, phone: 555-123-4567")
```

## Troubleshooting

### Connection Issues

```bash
# Test with verbose output
mcp-codegen ls --url http://localhost:8000 --verbose

# Force specific transport
mcp-codegen ls --url http://localhost:8000 --transport sse
```

### Import Errors

```bash
# Make sure installed
pip install -e .

# Check Python path
python -c "from mcp_codegen import codegen; print('OK')"
```

### Runner Issues

```bash
# Check resource limits on Linux
ulimit -a

# Run with more memory
mcp-codegen run --file agent.py --memory-mb 2048

# Disable sandbox if issues
mcp-codegen run --file agent.py  # No --seccomp flag
```

## License

See repository for license information.

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests
4. Submit a pull request

---
