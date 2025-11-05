"""Test custom exception hierarchy."""
import pytest
from mcp_codegen.exceptions import (
    MCPError,
    TransportProbeError,
    VersionNegotiationError,
    JSONRPCError,
    ToolCallError
)


def test_mcp_error_base():
    """Test base MCPError is a standard Exception."""
    with pytest.raises(Exception):
        raise MCPError("test")


def test_transport_probe_error():
    """Test TransportProbeError."""
    with pytest.raises(MCPError):
        raise TransportProbeError("No transport found")


def test_version_negotiation_error():
    """Test VersionNegotiationError."""
    with pytest.raises(MCPError):
        raise VersionNegotiationError("Version mismatch")


def test_jsonrpc_error():
    """Test JSONRPCError with code, message, and data."""
    error = JSONRPCError(code=-32602, message="Invalid params", data={"missing": ["id"]})

    assert error.code == -32602
    assert error.message == "Invalid params"
    assert error.data == {"missing": ["id"]}
    assert "JSON-RPC error -32602: Invalid params" in str(error)


def test_jsonrpc_error_without_data():
    """Test JSONRPCError without optional data."""
    error = JSONRPCError(code=-32600, message="Invalid Request")

    assert error.code == -32600
    assert error.message == "Invalid Request"
    assert error.data is None


def test_jsonrpc_error_str_with_data():
    """Test JSONRPCError __str__ includes data."""
    error = JSONRPCError(code=-32602, message="Invalid params", data={"missing": ["id"]})
    error_str = str(error)

    assert "JSON-RPC error -32602: Invalid params" in error_str
    assert "missing" in error_str


def test_tool_call_error():
    """Test ToolCallError."""
    with pytest.raises(MCPError):
        raise ToolCallError("Tool not found")
