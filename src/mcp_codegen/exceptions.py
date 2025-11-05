"""Custom exceptions for MCP client operations.

This module provides a structured exception hierarchy for better error handling
and more actionable error messages.
"""
from __future__ import annotations

__all__ = [
    "MCPError",
    "TransportProbeError",
    "VersionNegotiationError",
    "JSONRPCError",
    "ToolCallError",
]


class MCPError(Exception):
    """Base exception for all MCP-related errors.

    All custom exceptions in this library inherit from this class,
    making it easy to catch all MCP-specific errors.
    """
    pass


class TransportProbeError(MCPError):
    """Raised when no working transport protocol is found.

    This error occurs during the transport detection phase when
    none of the supported protocols (streamable-http, SSE, POST)
    are available or working.

    Example:
        Trying to connect to a server that doesn't support any
        known MCP transport protocol.
    """
    pass


class VersionNegotiationError(MCPError):
    """Raised when protocol version negotiation fails.

    This error occurs during initialization when the client and server
    cannot agree on a protocol version, or when the server returns
    an error during initialization.

    Example:
        Server doesn't support the client's protocol version
        and no compatible version is available.
    """
    pass


class JSONRPCError(MCPError):
    """Raised when a JSON-RPC call fails.

    This exception wraps the standard JSON-RPC error response,
    providing structured access to the error code, message, and
    optional data.

    Attributes:
        code: The JSON-RPC error code (e.g., -32602 for invalid params)
        message: Human-readable error message
        data: Optional additional error data from the server

    Example:
        A tool call with invalid parameters returns:
        {
            "code": -32602,
            "message": "Invalid params",
            "data": {"missing": ["required_field"]}
        }
    """

    def __init__(
        self,
        code: int,
        message: str,
        data: dict | None = None
    ):
        """Initialize JSONRPCError.

        Args:
            code: The JSON-RPC error code
            message: Human-readable error message
            data: Optional additional error data from the server
        """
        super().__init__(f"JSON-RPC error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data

    def __str__(self) -> str:
        """Return formatted error string with data if available."""
        if self.data:
            return f"{super().__str__()} — {self.data}"
        return super().__str__()


class ToolCallError(MCPError):
    """Raised when a tool call fails.

    This error is raised when a tool invocation fails after all
    retry attempts have been exhausted, or when the tool call
    cannot be completed for reasons other than JSON-RPC protocol errors.

    Example:
        Network errors during tool call, or repeated server errors
        after configured retry attempts.
    """
    pass
