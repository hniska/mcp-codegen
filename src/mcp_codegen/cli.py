"""Command-line interface for mcp-codegen.

This module provides commands:
- ls: List available tools from an MCP server
- gen: Generate static Python modules from MCP server schemas
- call: Invoke MCP tools directly without code generation
- search: Search for tools across generated servers
- run: Execute agent code with resource limits
"""
from __future__ import annotations
import argparse, asyncio, json, sys, uuid, subprocess
from typing import Any, Dict, List, Optional
try:
    from typing import Literal  # py>=3.8 ok, but py<3.11 needs typing_extensions
except ImportError:
    from typing_extensions import Literal
from .codegen import fetch_schema, render_module, generate_fs_layout_wrapper
from .constants import __version__, MCP_PROTOCOL_VERSION, CLIENT_NAME
from .utils import read_first_sse_event, ensure_accept_headers
import httpx
from urllib.parse import urlparse
import ipaddress
from pathlib import Path


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

async def _gen(url: str, out: str, module_name: str, fs_layout: bool = False, output_dir: str = "servers", generate_skill: bool = False, skill_dir: str = ".claude/skills"):
    """Generate a static Python module from an MCP server's tool definitions.

    Args:
        url: MCP server URL
        out: Output file path for generated module
        module_name: Name for the generated module
        fs_layout: Whether to generate filesystem layout (multiple files)
        output_dir: Output directory for fs_layout (default: "servers")
        generate_skill: Whether to generate a Claude Code skill
        skill_dir: Directory for skill files (default: .claude/skills)
    """
    tools = await fetch_schema(url)

    if fs_layout:
        generate_fs_layout_wrapper(url, module_name, tools, output_dir)
    else:
        code = render_module(module_name, tools)
        with open(out, "w", encoding="utf-8") as f:
            f.write(code)
        print(f"Wrote stub → {out}")

    # Generate skill if requested
    if generate_skill:
        from .skill_generator import generate_skill
        skill_path = generate_skill(module_name, url, tools, output_dir=skill_dir)
        print(f"✓ Generated skill → {skill_path}/")


def _search(query: str, servers_dir: str = "servers", detail: str = "basic"):
    """Search for tools across generated servers.

    Args:
        query: Search query (matches server name, tool name, or summary)
        servers_dir: Directory containing generated servers
        detail: Detail level ("name", "basic", "full")
    """
    try:
        from .runtime.search import search_tools
        tools = search_tools(query, servers_dir, detail)
        if not tools:
            print(f"No tools found matching: {query}")
            return

        print(f"Found {len(tools)} tool(s) matching '{query}':\n")
        for tool in tools:
            print(f"  {tool.server}/{tool.tool}")
            if tool.summary:
                print(f"    {tool.summary}")
        print()

        if detail == "full":
            print("To use a tool:")
            if tools:
                print(f"  from servers.{tools[0].server}.{tools[0].tool} import call, Params")
                print(f"  # See documentation at: {tools[0].module_path}")

    except Exception as e:
        print(f"✗ Search failed: {e}", file=sys.stderr)
        sys.exit(1)


def _run(file: str, code: str, servers_dir: str = "servers", workspace: str = ".workspace",
         cpu_seconds: int = 10, memory_mb: int = 512, disable_network: bool = False,
         seccomp: bool = False, firejail: bool = False):
    """Execute agent code with resource limits.

    Args:
        file: Python file to execute
        code: Python code to execute (alternative to file)
        servers_dir: Directory containing generated servers
        workspace: Workspace directory for agent output
        cpu_seconds: CPU time limit in seconds
        memory_mb: Memory limit in MB
        disable_network: Whether to disable network access (allowed by default)
        seccomp: Whether to enable seccomp filtering (Linux only)
        firejail: Whether to use Firejail sandbox (Linux only)
    """
    try:
        # Build runner command
        # Path: src/mcp_codegen/cli.py -> runner is in same package
        runner_path = Path(__file__).parent / "runner" / "run.py"

        if not runner_path.exists():
            print(f"✗ Runner not found: {runner_path}", file=sys.stderr)
            sys.exit(1)

        # Build arguments
        runner_args = [sys.executable, str(runner_path)]

        if code:
            runner_args.extend(["--code", code])
        elif file:
            runner_args.extend(["--file", file])
        else:
            print("Error: Either --code or --file must be provided", file=sys.stderr)
            sys.exit(1)

        runner_args.extend([
            "--servers-dir", servers_dir,
            "--workspace", workspace,
            "--cpu-seconds", str(cpu_seconds),
            "--memory-mb", str(memory_mb),
        ])

        if disable_network:
            runner_args.append("--disable-network")
        if seccomp:
            runner_args.append("--seccomp")
        if firejail:
            runner_args.append("--firejail")

        # Execute runner
        result = subprocess.run(runner_args, text=True)
        sys.exit(result.returncode)

    except Exception as e:
        print(f"✗ Run failed: {e}", file=sys.stderr)
        sys.exit(1)


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
    s_gen.add_argument("--out", required=False, help="Output file path (required unless --fs-layout is used)")
    s_gen.add_argument("--name", default="mcp_stub", help="Module name")
    s_gen.add_argument("--fs-layout", action="store_true", help="Generate per-tool files in servers/<name>/ layout")
    s_gen.add_argument("--output-dir", default="servers", help="Output directory for fs-layout (default: servers)")
    s_gen.add_argument("--generate-skill", action="store_true", help="Generate Claude Code skill for this server")
    s_gen.add_argument("--skill-dir", default=".claude/skills", help="Skill directory (default: .claude/skills)")
    s_gen.add_argument("--allow-local", action="store_true", help="Allow local URLs (security risk)")

    s_search = sub.add_parser("search", help="Search for tools across servers")
    s_search.add_argument("query", help="Search query")
    s_search.add_argument("--servers-dir", default="servers", help="Servers directory to search in")
    s_search.add_argument("--detail", choices=["name", "basic", "full"], default="basic", help="Detail level")

    s_run = sub.add_parser("run", help="Run agent code with resource limits")
    s_run.add_argument("--file", help="Python file to execute")
    s_run.add_argument("--code", help="Python code to execute (alternative to --file)")
    s_run.add_argument("--servers-dir", default="servers", help="Servers directory (default: servers)")
    s_run.add_argument("--workspace", default=".workspace", help="Workspace directory (default: .workspace)")
    s_run.add_argument("--cpu-seconds", type=int, default=10, help="CPU time limit (default: 10)")
    s_run.add_argument("--memory-mb", type=int, default=512, help="Memory limit in MB (default: 512)")
    s_run.add_argument("--disable-network", action="store_true", help="Disable network access (enabled by default for MCP tool calls)")
    s_run.add_argument("--seccomp", action="store_true", help="Enable seccomp syscall filtering (Linux only)")
    s_run.add_argument("--firejail", action="store_true", help="Run with Firejail sandbox (Linux only)")

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
        # Validate that --out is provided when not using --fs-layout
        if not args.fs_layout and not args.out:
            print("Error: --out is required when not using --fs-layout", file=sys.stderr)
            sys.exit(1)
        asyncio.run(_gen(args.url, args.out, args.name, fs_layout=args.fs_layout, output_dir=args.output_dir, generate_skill=args.generate_skill, skill_dir=args.skill_dir))
    elif args.cmd == "search":
        _search(args.query, servers_dir=args.servers_dir, detail=args.detail)
    elif args.cmd == "run":
        _run(file=args.file, code=args.code, servers_dir=args.servers_dir, workspace=args.workspace,
             cpu_seconds=args.cpu_seconds, memory_mb=args.memory_mb, disable_network=args.disable_network,
             seccomp=args.seccomp, firejail=args.firejail)
    elif args.cmd == "call":
        _validate_url(args.url, allow_local=args.allow_local, explicit_transport=False)
        asyncio.run(_call(args.url, args.tool, args.args, timeout=args.timeout, json_output=args.json, verbose=args.verbose))
