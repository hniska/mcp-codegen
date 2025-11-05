from __future__ import annotations
from types import SimpleNamespace
from typing import Any, Callable, Dict, Optional
import anyio
import httpx
import json
try:
    from typing import Literal  # py>=3.8 ok, but py<3.11 needs typing_extensions
except ImportError:
    from typing_extensions import Literal

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client  # preferred
from mcp.client.sse import sse_client  # fallback
from mcp.types import JSONRPCMessage
from .constants import __version__, MCP_PROTOCOL_VERSION, CLIENT_NAME, DEFAULT_TIMEOUT, DEFAULT_DETECTION_TIMEOUT

class MCPModule:
    def __init__(
        self,
        base_url: str,
        transport: str = "auto",   # "auto" | "streamable-http" | "sse" | "http-post"
        session_headers: Optional[Dict[str, str]] = None,
        timeout_seconds: float = DEFAULT_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self._headers = session_headers or {}
        self._session: Optional[ClientSession] = None
        self._tool_funcs = SimpleNamespace()
        self._resources = {}
        self._prompts = {}
        self._timeout = timeout_seconds
        self._http_client: Optional[httpx.AsyncClient] = None
        self._http_post_mode = False
        self._next_id = 1
        self._protocol_version: Optional[str] = None
        self._server_name: Optional[str] = None

    async def __aenter__(self) -> "MCPModule":
        await self.init()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._session:
            await self._session.close()
        if self._http_client:
            await self._http_client.aclose()

    async def _connect_streamable(self):
        url = self.base_url if self.base_url.endswith("/mcp") else f"{self.base_url}/mcp"
        return streamablehttp_client(url, headers=self._headers)

    async def _connect_sse(self):
        url = self.base_url if self.base_url.endswith("/sse") else f"{self.base_url}/sse"
        return sse_client(url, headers=self._headers)

    async def _init_http_post(self):
        """Initialize using HTTP POST transport with version negotiation."""
        url = self.base_url if self.base_url.endswith("/mcp") else f"{self.base_url}/mcp"
        self._http_client = httpx.AsyncClient(headers=self._headers, timeout=self._timeout)
        self._http_post_mode = True

        # Try current version first
        try:
            response = await self._http_post_request("initialize", {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": CLIENT_NAME, "version": __version__}
            })
            return response
        except RuntimeError as e:
            # If invalidProtocolVersion, parse server's supported versions from error data
            if "invalidProtocolVersion" in str(e):
                # Parse error data to get supported versions
                try:
                    err_payload = json.loads(str(e))
                    data = err_payload.get("error", {}).get("data") or {}
                    candidates = data.get("supportedProtocolVersions") or [data.get("serverProtocolVersion")]
                    candidates = [v for v in candidates if v]
                    
                    for v in candidates:
                        try:
                            response = await self._http_post_request("initialize", {
                                "protocolVersion": v,
                                "capabilities": {},
                                "clientInfo": {"name": CLIENT_NAME, "version": __version__}
                            })
                            return response
                        except RuntimeError:
                            pass
                    raise RuntimeError("Protocol version negotiation failed")
                except (json.JSONDecodeError, KeyError):
                    # Fallback to hardcoded version if error parsing fails
                    try:
                        response = await self._http_post_request("initialize", {
                            "protocolVersion": "2024-11-05",  # Fallback to older version
                            "capabilities": {},
                            "clientInfo": {"name": CLIENT_NAME, "version": __version__}
                        })
                        return response
                    except RuntimeError:
                        raise RuntimeError(f"Protocol version negotiation failed: {e}")
            raise

    async def _http_post_request(self, method: str, params: Any) -> Any:
        """Make an HTTP POST JSON-RPC request."""
        if not self._http_client:
            raise RuntimeError("HTTP client not initialized")

        url = self.base_url if self.base_url.endswith("/mcp") else f"{self.base_url}/mcp"
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": method,
            "params": params
        }
        self._next_id += 1

        # Use streaming POST when you might receive SSE
        async with self._http_client.stream("POST", url, json=payload, headers=self._headers) as resp:
            resp.raise_for_status()
            ct = (resp.headers.get("content-type") or "").lower()
            if "text/event-stream" in ct:
                from .utils import read_first_sse_event
                data = await read_first_sse_event(resp)   # resp is a streaming Response
            else:
                data = json.loads((await resp.aread()).decode("utf-8"))

            if "error" in data:
                raise RuntimeError(json.dumps(data["error"], ensure_ascii=False))

            return data.get("result")

    def _setup_http_post_tools(self, tools_data: list) -> None:
        """Register tools for HTTP POST mode.

        Creates callable wrappers for each tool that use HTTP POST transport.

        Args:
            tools_data: List of tool dictionaries from tools/list response
        """
        for tool_data in tools_data:
            name = tool_data["name"]

            def make_http_caller(tool_name: str) -> Callable[..., Any]:
                async def _call(**kwargs):
                    result = await self._http_post_request("tools/call", {
                        "name": tool_name,
                        "arguments": kwargs
                    })
                    if result and "content" in result:
                        block = result["content"][0]
                        return block.get("text", block.get("data", block))
                    return result
                return _call

            setattr(self._tool_funcs, name, make_http_caller(name))

    async def _connect(self):
        if self.transport == "http-post":
            return None  # HTTP POST doesn't use streaming connection
        if self.transport == "streamable-http":
            return await self._connect_streamable()
        if self.transport == "sse":
            return await self._connect_sse()
        # Auto mode: try streamable-http first with short timeout
        try:
            async with anyio.move_on_after(DEFAULT_DETECTION_TIMEOUT):
                return await self._connect_streamable()
        except Exception:
            pass
        # Try SSE with short timeout
        try:
            async with anyio.move_on_after(DEFAULT_DETECTION_TIMEOUT):
                return await self._connect_sse()
        except Exception:
            pass
        return None  # Fall back to HTTP POST

    async def init(self) -> None:
        if self._session or self._http_post_mode:
            return

        try:
            connection = await self._connect()

            # HTTP POST mode
            if connection is None:
                response = await self._init_http_post()
                # Store protocol version and server info for verbose logging
                init = response  # JSON-RPC result
                self._protocol_version = init.get("protocolVersion") or init.get("serverProtocolVersion")
                si = init.get("serverInfo") or {}
                self._server_name = si.get("name") or si.get("label") or "unknown"
                
                tools_result = await self._http_post_request("tools/list", {})
                tools = tools_result.get("tools", [])
                self._setup_http_post_tools(tools)
                return

            # Streaming mode (streamable-http or SSE)
            async with connection as (read_stream, write_stream, _):
                self._session = ClientSession(read_stream, write_stream)
                with anyio.move_on_after(self._timeout) as scope:
                    await self._session.initialize()
                if scope.cancel_called:
                    if self.transport in ("auto", "streamable-http"):
                        try:
                            async with (await self._connect_sse()) as (r2, w2, _2):
                                self._session = ClientSession(r2, w2)
                                await self._session.initialize()
                        except Exception:
                            # Fall back to HTTP POST
                            self._session = None
                            await self._init_http_post()
                            tools_result = await self._http_post_request("tools/list", {})
                            tools = tools_result.get("tools", [])
                            self._setup_http_post_tools(tools)
                            return
                    else:
                        raise TimeoutError("Timed out initializing MCP session")

                tools = (await self._session.list_tools()).tools or []
                resources = (await self._session.list_resources()).resources or []
                prompts = (await self._session.list_prompts()).prompts or []

                for tool in tools:
                    name = tool.name

                    def make_caller(tool_name: str) -> Callable[..., Any]:
                        async def _call(**kwargs):
                            if self._session is None:
                                raise RuntimeError(
                                    "Session not initialized. This should not happen - "
                                    "call init() before using tools."
                                )
                            result = await self._session.call_tool(tool_name, arguments=kwargs)
                            if result.content:
                                block = result.content[0]
                                return getattr(block, "text", getattr(block, "data", block))
                            return result
                        return _call

                    setattr(self._tool_funcs, name, make_caller(name))

                self._resources = {r.uri: r for r in resources}
                self._prompts = {p.name: p for p in prompts}
        except Exception:
            # Ensure cleanup on any exception
            if self._http_client:
                await self._http_client.aclose()
                self._http_client = None
            if self._session:
                await self._session.close()
                self._session = None
            # Reset HTTP POST mode on failure so subsequent retries don't assume POST mode
            self._http_post_mode = False
            raise

    @property
    def tools(self) -> SimpleNamespace:
        return self._tool_funcs

    async def read_resource(self, uri: str) -> Any:
        if self._session is None:
            raise RuntimeError("Session not initialized. Call init() first.")
        res = await self._session.read_resource(uri)
        return getattr(res, "text", res)

    async def render_prompt(self, name: str, **kwargs) -> str:
        if self._session is None:
            raise RuntimeError("Session not initialized. Call init() first.")
        rp = await self._session.render_prompt(name, arguments=kwargs)
        return rp.prompt or ""
