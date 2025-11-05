"""Command-line interface for mcp-codegen.

This module provides three commands:
- ls: List available tools from an MCP server
- gen: Generate static Python modules from MCP server schemas
- call: Invoke MCP tools directly without code generation
"""
from __future__ import annotations
import argparse, asyncio, json, sys, uuid
from typing import Any, Dict, List, Optional
try:
    from typing import Literal  # py>=3.8 ok, but py<3.11 needs typing_extensions
except ImportError:
    from typing_extensions import Literal
from .codegen import fetch_schema, render_module
from .constants import __version__, MCP_PROTOCOL_VERSION, CLIENT_NAME
from .utils import read_first_sse_event, ensure_accept_headers
import httpx
from urllib.parse import urlparse
import ipaddress


def _validate_url(url: str, allow_local: bool = False, explicit_transport: bool = False) -> None:
    """Validate URL scheme for security.
    
    Args:
        url: URL to validate
        allow_local: Whether to allow local-only schemes
        explicit_transport: Whether transport was explicitly set (developer ergonomics)
        
    Raises:
        SystemExit: If URL scheme is not allowed
    """
    parsed = urlparse(url)
    allowed_schemes = {"http", "https"}
    
    if not allow_local:
        # Reject local-only schemes
        if parsed.scheme in {"file", "ftp"}:
            raise SystemExit(f"URL scheme '{parsed.scheme}' not allowed. Use --allow-local to override.")
        
        # Check for private IPs using ipaddress module
        host = parsed.hostname or ""
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private and not (allow_local or explicit_transport):
                raise SystemExit("Private IP not allowed. Use --allow-local.")
        except ValueError:
            pass  # not an IP; domain—OK to proceed
        
        # Reject localhost/private IPs (basic check) - but allow when transport is explicitly set
        if parsed.hostname in {"localhost", "127.0.0.1", "::1"} and not explicit_transport:
            raise SystemExit(f"Local URLs not allowed. Use --allow-local to override.")
    
    if parsed.scheme not in allowed_schemes:
        raise SystemExit(f"URL scheme '{parsed.scheme}' not supported. Use http:// or https://")



async def _ls(url: str, transport: str, verbose: bool = False):
    """List all available tools from an MCP server.

    Args:
        url: MCP server URL
        transport: Transport protocol (auto, streamable-http, or sse)
        verbose: Whether to show additional debugging information
    """
    if verbose:
        print(f"Connecting to: {url}")
        print(f"Transport: {transport}")
    
    # Pass transport and verbose to fetch_schema for proper transport detection
    tools = await fetch_schema(url, transport=transport, verbose=verbose)
    
    if verbose:
        print(f"Server protocol version: {getattr(tools[0], 'protocol_version', 'unknown')}")
    
    print("Tools:")
    for t in tools:
        desc = getattr(t, 'description', '') or ''
        schema = getattr(t, 'input_schema', None)
        if schema and hasattr(schema, 'properties'):
            params = list(schema.properties.keys())
            print(f" - {t.name}: {desc} (params: {', '.join(params)})")
        else:
            print(f" - {t.name}: {desc}")

async def _gen(url: str, out: str, module_name: str):
    """Generate a static Python module from an MCP server's tool definitions.

    Args:
        url: MCP server URL
        out: Output file path for generated module
        module_name: Name for the generated module
    """
    tools = await fetch_schema(url)
    code = render_module(module_name, tools)
    with open(out, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"Wrote stub → {out}")


async def _call(url: str, tool: str, args_list: list, timeout: float = None, json_output: bool = False, verbose: bool = False):
    """Call an MCP tool directly without generating code.

    Args:
        url: MCP server URL
        tool: Name of the tool to invoke
        args_list: List of arguments in key=value format
        timeout: Request timeout in seconds
        json_output: Whether to output raw JSON-RPC result
        verbose: Whether to show additional debugging information

    Arguments are automatically parsed as JSON if possible, otherwise treated as strings.
    """
    if timeout is None:
        from .constants import DEFAULT_TIMEOUT
        timeout = DEFAULT_TIMEOUT
    # Parse arguments from --arg key=value format
    arguments = {}
    for arg in args_list:
        if "=" not in arg:
            raise SystemExit(f"--arg must be key=value, got {arg!r}")
        k, v = arg.split("=", 1)
        try:
            v = json.loads(v)  # numbers/objects/arrays/bools/null
        except json.JSONDecodeError:
            pass               # fall back to raw string
        arguments[k] = v

    # Call using HTTP POST JSON-RPC with version negotiation
    api_url = url if url.endswith('/mcp') else f"{url.rstrip('/')}/mcp"
    client_version = MCP_PROTOCOL_VERSION
    # Don't include session ID in initial headers (initialize must not have it)
    headers = ensure_accept_headers({
        "mcp-protocol-version": client_version,
    })

    async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
        # Initialize to negotiate protocol version (no session ID for initialize)
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": client_version,
                "capabilities": {},
                "clientInfo": {"name": CLIENT_NAME, "version": __version__}
            }
        }
        # Use streaming to handle both JSON and SSE responses
        async with client.stream("POST", api_url, json=init_payload) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            # Extract session ID from response headers if present
            session_id = response.headers.get("mcp-session-id") or response.headers.get("Mcp-Session-Id")

            if "text/event-stream" in content_type.lower():
                # Server responds with SSE - read first event only
                init_data = await read_first_sse_event(response)
            else:
                # Server responds with JSON
                body = await response.aread()
                init_data = json.loads(body.decode('utf-8'))

        # Get server's protocol version
        server_version = init_data.get("result", {}).get("protocolVersion", client_version)

        # Update headers with negotiated version
        client._headers["mcp-protocol-version"] = server_version

        # Add session ID if we got one, otherwise generate one
        if not session_id:
            session_id = str(uuid.uuid4())
        client._headers["Mcp-Session-Id"] = session_id

        # Call the tool using negotiated version and session ID
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments}
        }
        # Use streaming for tools/call too
        async with client.stream("POST", api_url, json=payload) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")

            if "text/event-stream" in content_type.lower():
                # Server responds with SSE - read first event only
                data = await read_first_sse_event(response)
            else:
                # Server responds with JSON
                body = await response.aread()
                data = json.loads(body.decode('utf-8'))

        if "error" in data:
            print(f"Error: {data['error']}", file=sys.stderr)
            sys.exit(1)

        result = data.get("result", {})
        
        if json_output:
            print(json.dumps(result, indent=2))
        else:
            content = result.get("content", [])
            if isinstance(content, list) and content:
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        print(block["text"])
                    else:
                        print(json.dumps(block, indent=2))
            else:
                print(json.dumps(result, indent=2))

def main():
    p = argparse.ArgumentParser(prog="mcp-codegen", description="MCP client and code generator")
    sub = p.add_subparsers(dest="cmd", required=True)

    s_ls = sub.add_parser("ls", help="List tools for a server")
    s_ls.add_argument("--url", required=True, help="MCP server URL")
    s_ls.add_argument("--transport", choices=["auto","streamable-http","sse"], default="auto")
    s_ls.add_argument("--verbose", action="store_true", help="Show additional debugging information")
    s_ls.add_argument("--allow-local", action="store_true", help="Allow local URLs (security risk)")

    s_gen = sub.add_parser("gen", help="Generate a static stub module")
    s_gen.add_argument("--url", required=True, help="MCP server URL")
    s_gen.add_argument("--out", required=True, help="Output file path")
    s_gen.add_argument("--name", default="mcp_stub", help="Module name")
    s_gen.add_argument("--allow-local", action="store_true", help="Allow local URLs (security risk)")

    s_call = sub.add_parser("call", help="Call a tool directly")
    s_call.add_argument("--url", required=True, help="MCP server URL")
    s_call.add_argument("--tool", required=True, help="Tool name to call")
    s_call.add_argument("--arg", action="append", default=[], dest="args", help="Tool argument as key=value (can be repeated)")
    from .constants import DEFAULT_TIMEOUT
    s_call.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                       help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT}, override with MCP_TIMEOUT env var)")
    s_call.add_argument("--json", action="store_true", help="Output raw JSON-RPC result")
    s_call.add_argument("--verbose", action="store_true", help="Show additional debugging information")
    s_call.add_argument("--allow-local", action="store_true", help="Allow local URLs (security risk)")

    args = p.parse_args()
    if args.cmd == "ls":
        _validate_url(args.url, allow_local=args.allow_local, explicit_transport=(args.transport != "auto"))
        asyncio.run(_ls(args.url, args.transport, verbose=args.verbose))
    elif args.cmd == "gen":
        _validate_url(args.url, allow_local=args.allow_local, explicit_transport=False)
        asyncio.run(_gen(args.url, args.out, args.name))
    elif args.cmd == "call":
        _validate_url(args.url, allow_local=args.allow_local, explicit_transport=False)
        asyncio.run(_call(args.url, args.tool, args.args, timeout=args.timeout, json_output=args.json, verbose=args.verbose))
