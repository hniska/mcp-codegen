"""Code generation for MCP client stubs.

This module provides functions to:
- Connect to MCP servers and fetch tool schemas
- Generate standalone Python modules with Pydantic models
- Support multiple transport protocols (streamable-http, SSE, HTTP POST)
"""
from __future__ import annotations
from typing import Dict, List, Any
from textwrap import indent
import anyio
import httpx
import json
import uuid
import keyword  # For reserved keyword checking
try:
    from typing import Literal  # py>=3.8 ok, but py<3.11 needs typing_extensions
except ImportError:
    from typing_extensions import Literal

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.sse import sse_client
from .constants import __version__, MCP_PROTOCOL_VERSION, CLIENT_NAME, DEFAULT_WRITE_TIMEOUT, DEFAULT_POOL_TIMEOUT
from .utils import read_first_sse_event, ensure_accept_headers



def detect_transport(base_url: str, timeout_connect: float = 1.5, timeout_read: float = 0.4, verbose: bool = False) -> str:
    """Detect which MCP transport a server supports.

    Uses fast probing to determine the best transport without waiting for timeouts.
    Based on MCP spec where servers expose /mcp for POST and optionally GET with SSE.

    Args:
        base_url: MCP server base URL
        timeout_connect: Connection timeout in seconds
        timeout_read: Read timeout in seconds
        verbose: Whether to print debug information about detection attempts

    Returns:
        One of: "streamable-http", "sse", "http-post", or "unknown"
    """
    base = base_url.rstrip("/")
    mcp = base if base.endswith("/mcp") else f"{base}/mcp"
    sse = base if base.endswith("/sse") else f"{base}/sse"
    t = httpx.Timeout(
        connect=timeout_connect, 
        read=timeout_read, 
        write=DEFAULT_WRITE_TIMEOUT, 
        pool=DEFAULT_POOL_TIMEOUT
    )

    # 1) Streamable HTTP: HEAD /mcp with Accept: text/event-stream
    # Some servers don't support HEAD, so try POST as fallback with minimal probe
    try:
        with httpx.Client(timeout=t) as client:
            r = client.request("HEAD", mcp, headers={"Accept": "text/event-stream"})
            ct = r.headers.get("content-type", "")
            if r.status_code == 200 and "text/event-stream" in ct.lower():
                if verbose:
                    print(f"Trying streamable-http: HEAD {mcp} -> {r.status_code} {ct}")
                return "streamable-http"
            # If HEAD not supported (405), try POST with initialize probe
            if r.status_code == 405:
                # Need proper initialize params for some servers
                probe = {
                    "jsonrpc": "2.0",
                    "id": "probe",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": f"{CLIENT_NAME}-probe", "version": __version__}
                    }
                }
                try:
                    # Use longer timeout for POST (needs time to process initialize)
                    post_timeout = httpx.Timeout(connect=timeout_connect, read=1.5, write=timeout_read, pool=timeout_connect)
                    # Some servers require both Accept headers
                    with httpx.Client(timeout=post_timeout) as post_client:
                        with post_client.stream("POST", mcp, json=probe, headers=ensure_accept_headers()) as stream:
                            ct = stream.headers.get("content-type", "")
                            if stream.status_code == 200 and "text/event-stream" in ct.lower():
                                return "streamable-http"
                except httpx.HTTPError:
                    pass
    except httpx.HTTPError:
        pass

    # 2) Legacy SSE: HEAD /sse with Accept: text/event-stream
    # Use HEAD instead of streaming GET to avoid hanging on open connections
    try:
        with httpx.Client(timeout=t) as client:
            r = client.head(sse, headers={"Accept": "text/event-stream"})
            ct = r.headers.get("content-type", "")
            if r.status_code == 200 and "text/event-stream" in ct.lower():
                if verbose:
                    print(f"Trying SSE: HEAD {sse} -> {r.status_code} {ct}")
                return "sse"
            # If HEAD not supported (405/501), fall back to short GET
            if r.status_code in (405, 501):
                if verbose:
                    print(f"HEAD not supported ({r.status_code}), trying GET for SSE")
                try:
                    with httpx.Client(timeout=httpx.Timeout(connect=timeout_connect, read=0.5, write=DEFAULT_WRITE_TIMEOUT, pool=DEFAULT_POOL_TIMEOUT)) as get_client:
                        with get_client.stream("GET", sse, headers={"Accept": "text/event-stream"}) as stream:
                            ct = stream.headers.get("content-type", "")
                            if stream.status_code == 200 and "text/event-stream" in ct.lower():
                                if verbose:
                                    print(f"Trying SSE: GET {sse} -> {stream.status_code} {ct}")
                                return "sse"
                except httpx.HTTPError:
                    pass
    except httpx.HTTPError:
        pass

    # 3) Plain HTTP POST (JSON-RPC 2.0) at /mcp — cheap POST probe
    probe = {"jsonrpc": "2.0", "id": "probe", "method": "initialize", "params": {}}
    headers = ensure_accept_headers()
    try:
        r = httpx.post(mcp, json=probe, headers=headers, timeout=t)
        # Any of these indicate a reachable POST endpoint that likely speaks MCP:
        if r.status_code in (200, 400, 401, 403, 415, 422):
            if verbose:
                print(f"Trying http-post: POST {mcp} -> {r.status_code}")
            return "http-post"
    except httpx.HTTPError:
        pass

    # Couldn't confirm any known transport
    return "unknown"

async def _session_streamable(url: str, headers: Dict[str, str] | None):
    # Ensure required Accept header is present for streamable-http transport
    merged_headers = ensure_accept_headers(headers)
    async with streamablehttp_client(url, headers=merged_headers) as (r, w, _):
        s = ClientSession(r, w)
        await s.initialize()
        return s

async def _session_sse(url: str, headers: Dict[str, str] | None):
    # Ensure required Accept header is present for SSE transport
    merged_headers = ensure_accept_headers(headers)
    async with sse_client(url, headers=merged_headers) as (r, w):
        s = ClientSession(r, w)
        await s.initialize()
        return s


async def _fetch_http_post(base_url: str, headers: Dict[str, str] | None = None, timeout_seconds: float = 7.0):
    """Fetch schema using HTTP POST transport with protocol version negotiation.

    Note: Some servers (like deepwiki) require Accept: application/json, text/event-stream
    and respond with SSE. We handle this by reading the first SSE event."""
    url = base_url if base_url.endswith('/mcp') else f"{base_url}/mcp"
    # Start with our preferred version
    client_version = MCP_PROTOCOL_VERSION
    # Use ensure_accept_headers to ensure both Accept types are present
    base_headers = ensure_accept_headers(headers)
    http_headers = {"mcp-protocol-version": client_version, **base_headers}

    async with httpx.AsyncClient(headers=http_headers, timeout=timeout_seconds) as client:
        # Initialize and negotiate protocol version (no session ID for initialize)
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
        async with client.stream("POST", url, json=init_payload) as response:
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

        server_version = init_data.get("result", {}).get("protocolVersion", client_version)

        # Use server's version for subsequent requests (protocol negotiation)
        if server_version != client_version:
            http_headers["mcp-protocol-version"] = server_version

        # Add session ID if we got one, otherwise generate one
        if not session_id:
            session_id = str(uuid.uuid4())
        http_headers["Mcp-Session-Id"] = session_id

        # List tools using negotiated version and session ID
        tools_payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        # Use streaming for tools/list too
        async with client.stream("POST", url, json=tools_payload, headers=http_headers) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")

            if "text/event-stream" in content_type.lower():
                # Server responds with SSE - read first event only
                data = await read_first_sse_event(response)
            else:
                # Server responds with JSON
                body = await response.aread()
                data = json.loads(body.decode('utf-8'))

        return data.get("result", {}).get("tools", [])

async def fetch_schema(base_url: str, headers: Dict[str, str] | None = None, timeout_seconds: float = 7.0, transport: str = "auto", verbose: bool = False):
    """Fetch tool schema from an MCP server with automatic transport detection.

    Uses fast probing to detect the best transport, then connects.

    Args:
        base_url: MCP server base URL
        headers: Optional HTTP headers to include
        timeout_seconds: Timeout for connection attempts
        transport: Transport protocol (auto, streamable-http, sse, http-post)
        verbose: Whether to show debugging information

    Returns:
        List of tool definitions from the server
    """
    base = base_url.rstrip('/')
    http = base if base.endswith('/mcp') else f"{base}/mcp"
    sse = base if base.endswith('/sse') else f"{base}/sse"

    # Detect which transport the server supports
    if transport == "auto":
        detected_transport = detect_transport(base, verbose=verbose)
    else:
        detected_transport = transport

    # If we detected http-post, use it directly (don't try streaming transports)
    if detected_transport == "http-post":
        tools_data = await _fetch_http_post(base, headers, timeout_seconds)
    else:
        # Try streaming transports before falling back to HTTP POST
        preferred_transports: List[str] = []
        if detected_transport in {"streamable-http", "sse"}:
            preferred_transports.append(detected_transport)
        else:
            # Unknown transport - try both streaming options
            preferred_transports.extend(["streamable-http", "sse"])

        tried: set[str] = set()
        for candidate in preferred_transports:
            if candidate in tried:
                continue
            tried.add(candidate)
            try:
                # Add timeout to prevent hanging on incompatible servers
                with anyio.fail_after(timeout_seconds):
                    if candidate == "streamable-http":
                        s = await _session_streamable(http, headers)
                    else:  # candidate == "sse"
                        s = await _session_sse(sse, headers)
                    tools = (await s.list_tools()).tools or []
                    return tools
            except Exception:
                continue

        # All streaming transports failed - use HTTP POST as fallback
        tools_data = await _fetch_http_post(base, headers, timeout_seconds)

    # Convert dict tools to object-like tools
    tools = []
    for t in tools_data:
        schema_dict = t.get('inputSchema', {})
        schema_obj = type('Schema', (), {
            'properties': schema_dict.get('properties', {}),
            'required': schema_dict.get('required', []),
            'type': schema_dict.get('type', 'object')
        })()

        tool_obj = type('Tool', (), {
            'name': t['name'],
            'description': t.get('description', ''),
            'input_schema': schema_obj
        })()
        tools.append(tool_obj)

    return tools

def _pydantic_model_for_params(tool) -> str:
    props: Dict[str, Any] = getattr(tool.input_schema, 'properties', {}) or {}
    required: List[str] = getattr(tool.input_schema, 'required', []) or []
    
    lines = [f"class Params(BaseModel):"]
    if not props:
        lines.append("    pass")
    else:
        # Add docstring with tool description
        desc = getattr(tool, 'description', '') or ''
        if desc:
            lines.append(f'    """{desc}"""')
        
        for key, spec in props.items():
            pykey = _py_name(key)
            # Handle leading digits and reserved keywords
            if pykey and pykey[0].isdigit():
                pykey = f"param_{pykey}"
            if keyword.iskeyword(pykey):
                pykey = f"{pykey}_"
            
            typ = getattr(spec, 'type', None) or (spec.get('type') if isinstance(spec, dict) else 'string')
            
            # Handle enums and arrays properly
            if isinstance(spec, dict) and 'enum' in spec:
                # Generate Literal type for enums - FIXED: proper bracket syntax
                enum_values = spec['enum']
                vals = ", ".join(repr(v) for v in enum_values)
                pytype = f"Literal[{vals}]"
            elif typ == "array":
                # Handle array with items to generate list[InnerType]
                items = spec.get('items', {}) if isinstance(spec, dict) else {}
                if isinstance(items, dict) and 'type' in items:
                    inner_type = {
                        "string": "str", 
                        "number": "float", 
                        "integer": "int", 
                        "boolean": "bool", 
                        "object": "dict"
                    }.get(items['type'], "Any")
                    pytype = f"list[{inner_type}]"
                elif isinstance(items, dict) and ('anyOf' in items or '$ref' in items):
                    # Handle complex array items with anyOf or $ref
                    pytype = "list[Any]  # TODO: Complex array items not fully supported"
                else:
                    pytype = "list[Any]"
            else:
                pytype = {
                    "string": "str", 
                    "number": "float", 
                    "integer": "int", 
                    "boolean": "bool", 
                    "object": "dict"
                }.get(typ, "Any")
            
            # Handle optional fields
            opt = "" if key in required else " | None = None"
            
            # Add field description if available
            field_desc = ""
            if isinstance(spec, dict) and 'description' in spec:
                field_desc = f'  # {spec["description"]}'
            
            lines.append(f"    {pykey}: {pytype}{opt}{field_desc}")
    
    return "\n".join(lines)

def _py_name(name: str) -> str:
    """Convert parameter name to valid Python identifier."""
    s = name.replace("-", "_")
    if s and s[0].isdigit():
        s = f"param_{s}"
    if keyword.iskeyword(s):
        s = f"{s}_"
    return s

def _generate_tools_hash(tools) -> str:
    """Generate hash of tool definitions for change detection."""
    import hashlib
    content = ""
    for tool in tools:
        content += f"{tool.name}:{getattr(tool, 'description', '')}\n"
    return hashlib.sha256(content.encode()).hexdigest()[:16]

def render_module(module_name: str, tools) -> str:
    """Generate Python module code from MCP tool definitions.

    Creates a standalone module with:
    - Pydantic models for type-safe parameters
    - Transport negotiation with automatic fallback
    - HTTP POST support for maximum compatibility

    Args:
        module_name: Name for the generated module (currently unused, reserved for future)
        tools: List of tool definitions from MCP server

    Returns:
        Complete Python module source code as a string

    Raises:
        ValueError: If tools list is empty
    """
    if not tools:
        raise ValueError(
            "Cannot generate module: no tools found in schema. "
            "Verify the MCP server is running and exposing tools."
        )

    # Use actual current values for generated code
    generated_protocol_version = MCP_PROTOCOL_VERSION
    generated_version = __version__

    out = [
        '"""Auto-generated MCP stub."""',
        'from __future__ import annotations',
        'from typing import Any, Dict',
        'from pydantic import BaseModel',
        'import asyncio',
        'import httpx',
        'from mcp import ClientSession',
        'from mcp.client.streamable_http import streamablehttp_client',
        'from mcp.client.sse import sse_client',
        'import anyio',
        '',
        f"__all__ = [{', '.join([repr(_py_name(t.name)) for t in tools])}]",
        '',
        'def _detect_transport(base_url: str, timeout_connect: float = 1.5, timeout_read: float = 0.4) -> str:',
        '    """Detect which MCP transport a server supports using fast probing."""',
        '    base = base_url.rstrip("/")',
        '    mcp = base if base.endswith("/mcp") else f"{base}/mcp"',
        '    sse_url = base if base.endswith("/sse") else f"{base}/sse"',
        '    t = httpx.Timeout(connect=timeout_connect, read=timeout_read, write=timeout_read, pool=timeout_connect)',
        '    ',
        '    # Try streamable HTTP: HEAD /mcp with Accept: text/event-stream',
        '    try:',
        '        with httpx.Client(timeout=t) as client:',
        '            r = client.request("HEAD", mcp, headers={"Accept": "text/event-stream"})',
        '            ct = r.headers.get("content-type", "")',
        '            if r.status_code == 200 and "text/event-stream" in ct.lower():',
        '                return "streamable-http"',
        '    except httpx.HTTPError:',
        '        pass',
        '    ',
        '    # Try legacy SSE: HEAD /sse with Accept: text/event-stream',
        '    try:',
        '        with httpx.Client(timeout=t) as client:',
        '            r = client.request("HEAD", sse_url, headers={"Accept": "text/event-stream"})',
        '            ct = r.headers.get("content-type", "")',
        '            if r.status_code == 200 and "text/event-stream" in ct.lower():',
        '                return "sse"',
        '    except httpx.HTTPError:',
        '        pass',
        '    ',
        '    # Try HTTP POST: probe with initialize',
        '    probe = {"jsonrpc": "2.0", "id": "probe", "method": "initialize", "params": {}}',
        '    try:',
        '        r = httpx.post(mcp, json=probe, headers={"Accept": "application/json"}, timeout=t)',
        '        if r.status_code in (200, 400, 401, 403, 415, 422):',
        '            return "http-post"',
        '    except httpx.HTTPError:',
        '        pass',
        '    ',
        '    return "unknown"',
        '',
        'class _Client:',
        '    def __init__(self, base_url: str, headers: Dict[str, str] | None = None, timeout_seconds: float = 7.0):',
        '        self.base_url = base_url.rstrip(\'/\')',
        '        self.headers = headers or {}',
        '        self.timeout = timeout_seconds',
        '        self._transport = None  # Cache detected transport',
        '        self._protocol_version = None  # Cache negotiated protocol version',
        '',
        '    async def _session_streamable(self):',
        '        url = self.base_url if self.base_url.endswith(\'/mcp\') else f"{self.base_url}/mcp"',
        '        async with streamablehttp_client(url, headers=self.headers) as (r, w, _):',
        '            s = ClientSession(r, w)',
        '            await s.initialize()',
        '            return s',
        '',
        '    async def _session_sse(self):',
        '        url = self.base_url if self.base_url.endswith(\'/sse\') else f"{self.base_url}/sse"',
        '        async with sse_client(url, headers=self.headers) as (r, w, _):',
        '            s = ClientSession(r, w)',
        '            await s.initialize()',
        '            return s',
        '',
        '    async def _negotiate_version(self, client: httpx.AsyncClient, url: str):',
        '        """Negotiate protocol version with server if not already cached."""',
        '        if self._protocol_version is not None:',
        '            return self._protocol_version',
        '        ',
        '        # Initialize to negotiate version',
        f'        client_version = "{generated_protocol_version}"',
        '        init_payload = {',
        '            "jsonrpc": "2.0",',
        '            "id": "init",',
        '            "method": "initialize",',
        '            "params": {',
        '                "protocolVersion": client_version,',
        '                "capabilities": {},',
        f'                "clientInfo": {{"name": "mcp-codegen-generated", "version": "{generated_version}"}}',
        '            }',
        '        }',
        '        response = await client.post(url, json=init_payload)',
        '        response.raise_for_status()',
        '        init_data = response.json()',
        '        self._protocol_version = init_data.get("result", {}).get("protocolVersion", client_version)',
        '        return self._protocol_version',
        '    ',
        '    async def _call_http_post(self, tool_name: str, arguments: Dict[str, Any]):',
        '        """Call tool using HTTP POST JSON-RPC 2.0 with protocol version negotiation."""',
        '        url = self.base_url if self.base_url.endswith(\'/mcp\') else f"{self.base_url}/mcp"',
        f'        client_version = "{generated_protocol_version}"',
        '        headers = {"mcp-protocol-version": client_version, **self.headers}',
        '        ',
        '        async with httpx.AsyncClient(headers=headers, timeout=self.timeout) as client:',
        '            # Negotiate protocol version',
        '            server_version = await self._negotiate_version(client, url)',
        '            client._headers["mcp-protocol-version"] = server_version',
        '            ',
        '            # Call tool using negotiated version',
        '            payload = {',
        '                "jsonrpc": "2.0",',
        '                "id": 1,',
        '                "method": "tools/call",',
        '                "params": {"name": tool_name, "arguments": arguments}',
        '            }',
        '            response = await client.post(url, json=payload)',
        '            response.raise_for_status()',
        '            data = response.json()',
        '            result = data.get("result", {})',
        '            content = result.get("content", [])',
        '            if content:',
        '                block = content[0]',
        '                if "text" in block:',
        '                    return block["text"]',
        '                elif "data" in block:',
        '                    return block["data"]',
        '            return result',
        '',
        '    async def _session(self):',
        '        """Detect transport and establish a session, or return None for HTTP POST."""',
        '        # Detect transport once and cache',
        '        if self._transport is None:',
        '            self._transport = _detect_transport(self.base_url)',
        '        ',
        '        # Try the detected transport',
        '        if self._transport == "streamable-http":',
        '            try:',
        '                return await self._session_streamable()',
        '            except Exception:',
        '                pass  # Fall through',
        '        ',
        '        if self._transport == "sse":',
        '            try:',
        '                return await self._session_sse()',
        '            except Exception:',
        '                pass  # Fall through',
        '        ',
        '        # Use HTTP POST (either detected or as fallback)',
        '        return None',
        '',
    ]
    for tool in tools:
        tname = _py_name(tool.name)
        original_name = tool.name
        out.append(f"class {tname}:")
        out.append(indent(_pydantic_model_for_params(tool), '    '))
        out.append('    @staticmethod')
        out.append('    async def call(base_url: str, params: \'Params\', headers: Dict[str, str] | None = None, timeout_seconds: float = 7.0):')
        out.append('        c = _Client(base_url, headers, timeout_seconds)')
        out.append('        s = await c._session()')
        out.append('        arguments = params.model_dump(exclude_none=True)')
        out.append('        ')
        out.append('        # Use HTTP POST if session-based connection failed')
        out.append('        if s is None:')
        out.append(f'            return await c._call_http_post({original_name!r}, arguments)')
        out.append('        ')
        out.append('        # Use session-based call')
        out.append(f'        res = await s.call_tool({original_name!r}, arguments=arguments)')
        out.append('        if res.content:')
        out.append('            block = res.content[0]')
        out.append("            return getattr(block, 'text', getattr(block, 'data', block))")
        out.append('        return res')
        out.append('')
    return "\n".join(out)

def generate_fs_layout_wrapper(
    base_url: str,
    module_name: str,
    tools,
    output_dir: str = "servers"
) -> None:
    """Generate filesystem layout (wrapper for fs_layout module)."""
    from .fs_layout import generate_fs_layout as _generate
    _generate(base_url, module_name, tools, output_dir)
