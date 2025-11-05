# mcp-codegen

> ⚡ This code has been vibe coded

Generate Python client code from MCP (Model Context Protocol) servers.

## Features

- **List Tools**: Discover available tools from any MCP server
- **Generate Stubs**: Create standalone Python modules with full type hints
- **Direct Calls**: Invoke MCP tools directly from the command line
- **Auto Transport**: Automatically negotiates the best transport protocol (streamable-http, SSE, or HTTP POST)

## Installation

```bash
pip install -e .
```

## Quick Start

### List Available Tools

```bash
mcp-codegen ls --url https://your-mcp-server.com
```

### Call a Tool Directly

```bash
mcp-codegen call \
  --url https://smhi-mcp.hakan-3a6.workers.dev \
  --tool get_weather_forecast \
  --arg lat=64.75 \
  --arg lon=20.95 \
  --arg limit=1
```

### Generate a Python Module

```bash
mcp-codegen gen \
  --url https://your-mcp-server.com \
  --out mcp_tools.py
```

Then use it in your Python code:

```python
import asyncio
from mcp_tools import get_weather_forecast

async def main():
    params = get_weather_forecast.Params(lat=64.75, lon=20.95, limit=1)
    result = await get_weather_forecast.call(
        'https://smhi-mcp.hakan-3a6.workers.dev',
        params
    )
    print(result)

asyncio.run(main())
```

## Commands

### `mcp-codegen ls`

List all available tools from an MCP server.

**Options:**
- `--url URL` - MCP server URL (required)
- `--transport {auto,streamable-http,sse}` - Transport protocol (default: auto)

**Example:**
```bash
mcp-codegen ls --url http://localhost:8000
```

### `mcp-codegen gen`

Generate a static Python module from an MCP server's tool definitions.

**Options:**
- `--url URL` - MCP server URL (required)
- `--out FILE` - Output file path (required)
- `--name NAME` - Module name (default: mcp_stub)

**Example:**
```bash
mcp-codegen gen --url http://localhost:8000 --out my_tools.py --name my_tools
```

### `mcp-codegen call`

Call an MCP tool directly without generating code.

**Options:**
- `--url URL` - MCP server URL (required)
- `--tool TOOL` - Tool name to invoke (required)
- `--arg KEY=VALUE` - Tool argument (can be repeated multiple times)

Arguments are automatically parsed as JSON if possible, otherwise treated as strings.

**Examples:**

Simple arguments:
```bash
mcp-codegen call --url http://localhost:8000 --tool greet --arg name=World
```

JSON arguments:
```bash
mcp-codegen call --url http://localhost:8000 --tool search --arg limit=10 --arg filters='{"type":"active"}'
```

## Transport Protocols

mcp-codegen uses fast probing to detect which transport a server supports:

1. **streamable-http** - HEAD request to `/mcp` with `Accept: text/event-stream`
2. **SSE (Server-Sent Events)** - HEAD request to `/sse` with `Accept: text/event-stream`
3. **HTTP POST (JSON-RPC 2.0)** - POST probe to `/mcp` with JSON-RPC initialize

Detection happens in ~1-2 seconds with short timeouts (1.5s connect, 0.4s read), avoiding long waits. The detected transport is cached and used for all subsequent requests.

## Protocol Version Negotiation

mcp-codegen implements proper MCP protocol version negotiation:

- **Client version**: Starts with `2025-06-18` (latest MCP spec)
- **Server negotiation**: Calls `initialize` to discover server's version
- **Automatic adaptation**: Uses server's version for all subsequent requests
- **Version caching**: Negotiated version is cached per client instance

This ensures maximum compatibility - working with both new servers (2025-06-18) and older servers (2024-11-05, 2025-03-26).

## Generated Code

Generated modules are standalone and include:

- **Pydantic models** for type-safe parameters
- **Automatic transport negotiation** with fallback
- **No runtime dependency** on mcp-codegen (only on `mcp`, `pydantic`, `httpx`, and `anyio`)

Each tool becomes a class with:
- `Params` - Pydantic model for parameters
- `call()` - Static method to invoke the tool

## Development

Install in development mode:

```bash
pip install -e .
```

## License

See repository for license information.
