"""Client re-export for generated code compatibility.

This module re-exports the Client class from the parent module
to support the import pattern used in fs-layout generated code:

    from mcp_codegen.runtime.client import Client
"""
from __future__ import annotations

from ..client import Client

__all__ = ["Client"]
