"""Constants and configuration values for mcp-codegen.

Environment Variables:
    MCP_TIMEOUT: Default timeout for MCP requests in seconds (default: 7.0)
    MCP_CONNECT_TIMEOUT: Connection timeout for transport detection (default: 1.5)
    MCP_READ_TIMEOUT: Read timeout for transport detection (default: 0.4)
    MCP_DETECTION_TIMEOUT: Timeout for auto-detection of transports (default: 2.0)

Examples:
    # Use longer timeouts for slow servers:
    $ MCP_TIMEOUT=30 mcp-codegen call --url http://slow-server --tool get_data

    # Use shorter timeouts for fast local servers:
    $ MCP_CONNECT_TIMEOUT=0.5 MCP_READ_TIMEOUT=0.2 mcp-codegen ls --url http://localhost:8000
"""
from __future__ import annotations
import importlib.metadata
import os

# Package version - try to get from metadata, fallback to hardcoded
try:
    __version__ = importlib.metadata.version("mcp-codegen")
except Exception:
    __version__ = "0.1.3"  # Fallback for development

# MCP Protocol version
MCP_PROTOCOL_VERSION = "2025-06-18"

# Client identification
CLIENT_NAME = "mcp-codegen"

# Timeout defaults (can be overridden by environment variables)
DEFAULT_TIMEOUT = float(os.getenv("MCP_TIMEOUT", "7.0"))
DEFAULT_CONNECT_TIMEOUT = float(os.getenv("MCP_CONNECT_TIMEOUT", "1.5"))
DEFAULT_READ_TIMEOUT = float(os.getenv("MCP_READ_TIMEOUT", "0.4"))
DEFAULT_WRITE_TIMEOUT = float(os.getenv("MCP_WRITE_TIMEOUT", "0.4"))
DEFAULT_POOL_TIMEOUT = float(os.getenv("MCP_POOL_TIMEOUT", "1.5"))
DEFAULT_DETECTION_TIMEOUT = float(os.getenv("MCP_DETECTION_TIMEOUT", "2.0"))

# Transport detection order (can be overridden by environment variable)
DEFAULT_TRANSPORT_ORDER = os.getenv("MCP_TRANSPORT_ORDER", "streamable-http,sse,http-post").split(",")
