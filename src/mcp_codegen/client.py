"""Centralized HTTP client for MCP operations.

This module provides a single Client class that handles:
- Transport detection and caching (streamable-http → SSE → POST)
- Protocol version negotiation and caching
- HTTP client lifecycle management
- JSON-RPC request/response handling
- Retry logic with exponential backoff

The Client class eliminates code duplication by centralizing all HTTP
logic that was previously scattered across codegen.py and cli.py.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal, Optional
import anyio
import httpx
import uuid
import json
import asyncio

from .exceptions import (
    TransportProbeError,
    VersionNegotiationError,
    JSONRPCError,
    ToolCallError,
)
from .constants import MCP_PROTOCOL_VERSION, CLIENT_NAME, __version__
from .utils import read_first_sse_event, ensure_accept_headers

__all__ = ["Client", "Transport"]

# Type alias for transport protocols
Transport = Literal["streamable-http", "sse", "post"]


@dataclass(slots=True)
class InitializeCache:
    """Caches initialization data from the MCP server.

    Attributes:
        protocol_version: The negotiated MCP protocol version
        server_info: Server information from the initialize response
    """
    protocol_version: str
    server_info: dict[str, Any]


class Client:
    """Centralized async client for MCP operations.

    Owns a single httpx.AsyncClient with shared timeouts, retries,
    transport probing, and protocol version negotiation. This class
    eliminates code duplication and provides structured error handling.

    Example:
        async with Client("https://api.example.com/mcp") as client:
            await client.ensure_ready()
            result = await client.call_tool("get_data", {"query": "test"})
    """

    def __init__(
        self,
        base_url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        timeout: float = 10.0,
        retries: int = 2
    ):
        """Initialize MCP client.

        Args:
            base_url: MCP server base URL
            headers: Optional HTTP headers to include in all requests
            timeout: Request timeout in seconds
            retries: Number of retry attempts on transient errors
        """
        self.base_url = base_url.rstrip('/')
        self.headers = headers or {}
        self._timeout = httpx.Timeout(timeout)
        self._retries = retries
        self._http: Optional[httpx.AsyncClient] = None
        self._transport: Optional[Transport] = None
        self._init: Optional[InitializeCache] = None

    async def __aenter__(self) -> Client:
        """Async context manager entry.

        Returns:
            Self for use in async with statements
        """
        return self

    async def __aexit__(self, *exc) -> None:
        """Async context manager exit.

        Cleans up the HTTP client and any pending connections.
        """
        await self.aclose()

    async def aclose(self) -> None:
        """Close the HTTP client and release resources.

        This method should be called when the client is no longer needed
        to properly clean up the underlying httpx.AsyncClient.
        """
        if self._http:
            await self._http.aclose()
            self._http = None

    async def ensure_ready(
        self,
        *,
        transport_hint: Literal["auto"] | Transport = "auto"
    ) -> None:
        """Ensure client is ready by probing transport and initializing.

        This method must be called before using the client for tool calls.
        It performs two key operations:

        1. Probes for a working transport protocol
        2. Initializes the MCP connection and negotiates protocol version

        Both operations are cached, so calling this method multiple times
        is efficient.

        Args:
            transport_hint: Preferred transport ("auto" or specific)

        Raises:
            TransportProbeError: If no working transport found
            VersionNegotiationError: If initialization fails
        """
        if self._transport is None:
            self._transport = await self._probe_transport(transport_hint)
        if self._init is None:
            self._init = await self._initialize()

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client.

        Returns:
            The cached or newly created httpx.AsyncClient instance
        """
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._timeout)
        return self._http

    async def _probe_transport(
        self,
        hint: Literal["auto"] | Transport
    ) -> Transport:
        """Probe for working transport in preferred order.

        This method attempts to detect which transport protocol the
        server supports by trying them in order of preference.
        Results are cached in self._transport.

        Args:
            hint: Transport preference ("auto" or specific)

        Returns:
            Working transport protocol

        Raises:
            TransportProbeError: If no transport works
        """
        # Import here to avoid circular dependency
        from .codegen import detect_transport

        if hint == "auto":
            detected = detect_transport(self.base_url)
            if detected == "unknown":
                raise TransportProbeError(
                    f"No working transport found for {self.base_url}"
                )
            # Map internal names to our standardized names
            transport_map = {
                "streamable-http": "streamable-http",
                "sse": "sse",
                "http-post": "post"
            }
            return transport_map.get(detected, "post")

        # For specific hints, we'll validate the transport works
        # TODO: Implement validation for explicit hints
        # For now, just return the hint (validation happens during initialize)
        return hint

    async def _initialize(self) -> InitializeCache:
        """Initialize connection and negotiate protocol version.

        Performs the MCP initialization handshake, negotiating the protocol
        version with the server and caching the session information.
        Results are cached in self._init.

        Returns:
            Cached initialization data

        Raises:
            VersionNegotiationError: If initialization fails
        """
        http = await self._get_http_client()
        api_url = self.base_url if self.base_url.endswith('/mcp') else f"{self.base_url}/mcp"

        # Build initialization payload according to MCP spec
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": CLIENT_NAME,
                    "version": __version__
                }
            }
        }

        # Ensure proper headers for initialization
        headers = ensure_accept_headers({
            "mcp-protocol-version": MCP_PROTOCOL_VERSION,
            **self.headers
        })

        try:
            async with http.stream("POST", api_url, json=init_payload, headers=headers) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")

                # Extract session ID if present (some servers use this)
                session_id = response.headers.get("mcp-session-id") or response.headers.get("Mcp-Session-Id")

                # Handle both SSE and JSON responses
                if "text/event-stream" in content_type.lower():
                    init_data = await read_first_sse_event(response)
                else:
                    body = await response.aread()
                    init_data = json.loads(body.decode('utf-8'))

                # Check for initialization errors
                if "error" in init_data:
                    err = init_data["error"]
                    raise VersionNegotiationError(
                        f"Initialize failed: {err.get('message', 'unknown error')}"
                    )

                result = init_data.get("result") or {}
                server_version = result.get("protocolVersion", MCP_PROTOCOL_VERSION)

                # Update headers with negotiated version
                headers["mcp-protocol-version"] = server_version

                # Store session ID if available
                if session_id:
                    headers["Mcp-Session-Id"] = session_id
                else:
                    headers["Mcp-Session-Id"] = str(uuid.uuid4())

                # Store the headers for subsequent requests
                self._headers = headers

                # Return cached initialization data
                return InitializeCache(
                    protocol_version=str(server_version),
                    server_info=dict(result.get("serverInfo", {}))
                )

        except httpx.HTTPError as e:
            raise VersionNegotiationError(f"HTTP error during initialize: {e}") from e

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any]
    ) -> Any:
        """Call an MCP tool.

        This is the main method for invoking tools on the MCP server.
        It automatically handles:
        - Ensuring the client is ready (transport + initialization)
        - Building the JSON-RPC request
        - Retrying on transient errors
        - Extracting the result from the response

        Args:
            name: Tool name to invoke
            arguments: Tool arguments dictionary

        Returns:
            Tool result content (extracted from the MCP response)

        Raises:
            JSONRPCError: If the tool call returns a JSON-RPC error
            ToolCallError: If the call fails after all retries
        """
        await self.ensure_ready()

        http = await self._get_http_client()
        api_url = self.base_url if self.base_url.endswith('/mcp') else f"{self.base_url}/mcp"

        # Build JSON-RPC tool call payload
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments}
        }

        # Get headers (ensure_ready updates these with negotiated values)
        headers = ensure_accept_headers(self.headers)
        if self._init:
            headers["mcp-protocol-version"] = self._init.protocol_version

        # Retry logic for transient errors
        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                async with http.stream("POST", api_url, json=payload, headers=headers) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "")

                    # Handle both SSE and JSON responses
                    if "text/event-stream" in content_type.lower():
                        data = await read_first_sse_event(response)
                    else:
                        body = await response.aread()
                        data = json.loads(body.decode('utf-8'))

                    # Check for JSON-RPC errors in response
                    if "error" in data:
                        err = data["error"]
                        raise JSONRPCError(
                            code=err.get("code", -32000),
                            message=err.get("message", "unknown error"),
                            data=err.get("data")
                        )

                    # Return the result
                    return data.get("result")

            except (httpx.TransportError, httpx.ReadError) as e:
                last_error = e
                if attempt < self._retries:
                    # Exponential backoff: 0.3s, 0.6s, 1.2s, etc.
                    wait_time = 0.3 * (2 ** attempt)
                    await asyncio.sleep(wait_time)
                continue
            except JSONRPCError:
                # Don't retry JSON-RPC errors (they're not transient)
                raise

        # If we get here, all retries failed
        raise ToolCallError(
            f"Tool call failed after {self._retries + 1} attempts. "
            f"Last error: {last_error}"
        ) from last_error
