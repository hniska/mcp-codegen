"""Runtime utilities for mcp-codegen v2.

This module provides:
- search_tools(): Progressive tool discovery
- workspace: File I/O utilities for agent code
- logger: Structured logging with PII scrubbing
- scrub: Manual PII scrubbing function
- Client: Async HTTP client for MCP tool calls
"""
from __future__ import annotations

from .search import search_tools
from ..client import Client
from ..runner import workspace, logger, scrub

__all__ = ["search_tools", "workspace", "logger", "scrub", "Client"]
