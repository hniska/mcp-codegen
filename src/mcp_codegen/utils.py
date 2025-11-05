"""Shared utility functions for mcp-codegen."""
from __future__ import annotations
import json
from typing import Dict


async def read_first_sse_event(response) -> dict:
    """Read the first SSE event from a streaming response and parse it.

    Args:
        response: httpx streaming response object

    Returns:
        Parsed JSON data from first SSE event, or empty dict if none found
    """
    buffer = ""
    async for chunk in response.aiter_bytes():
        buffer += chunk.decode('utf-8')
        # SSE events are separated by double newlines
        if '\n\n' in buffer:
            # Extract first event
            event = buffer.split('\n\n')[0]
            # Parse the event
            for line in event.split('\n'):
                if line.startswith('data: '):
                    data_str = line[6:]  # Remove 'data: ' prefix
                    return json.loads(data_str)
            break
    return {}


def ensure_accept_headers(headers: Dict[str, str] | None = None) -> Dict[str, str]:
    """Ensure Accept header includes both JSON and event-stream.

    MCP servers may respond with either application/json or text/event-stream,
    so we must accept both in our requests.

    Args:
        headers: Existing headers dict or None

    Returns:
        Headers dict with proper Accept header
    """
    merged = dict(headers or {})
    accept_values = [v.strip().lower() for v in merged.get("Accept", "").split(",") if v.strip()]

    # Ensure both required types are present
    if "application/json" not in accept_values or "text/event-stream" not in accept_values:
        merged["Accept"] = "application/json, text/event-stream"

    return merged
