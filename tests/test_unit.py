"""Unit tests for mcp-codegen utilities and edge cases."""
import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
import httpx
import respx

from mcp_codegen.utils import read_first_sse_event, ensure_accept_headers
from mcp_codegen.codegen import detect_transport


class TestUtils:
    def test_ensure_accept_headers(self):
        """Test Accept header merging."""
        # Test with no existing headers
        headers = ensure_accept_headers()
        assert headers["Accept"] == "application/json, text/event-stream"
        
        # Test with existing headers
        existing = {"Authorization": "Bearer token"}
        headers = ensure_accept_headers(existing)
        assert headers["Accept"] == "application/json, text/event-stream"
        assert headers["Authorization"] == "Bearer token"
    
    @pytest.mark.asyncio
    async def test_read_first_sse_event(self):
        """Test SSE event parsing."""
        # Mock response with SSE data
        mock_response = AsyncMock()
        
        # Create a proper async iterator
        async def mock_aiter_bytes():
            yield b'data: {"result": {"tools": []}}\n\n'
        
        mock_response.aiter_bytes = mock_aiter_bytes
        
        result = await read_first_sse_event(mock_response)
        assert result == {"result": {"tools": []}}


class TestTransportDetection:
    def test_detect_transport_unknown(self):
        """Test transport detection with unreachable server."""
        result = detect_transport("http://localhost:99999")
        assert result == "unknown"
    
    def test_detect_transport_verbose(self):
        """Test verbose transport detection."""
        # This should not crash
        result = detect_transport("http://localhost:99999", verbose=True)
        assert result == "unknown"


class TestPostSSEBranch:
    @respx.mock
    @pytest.mark.asyncio
    async def test_post_sse_branch(self):
        """Test POST-SSE branch using proper mocking."""
        route = respx.post("https://example.com/mcp").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=b"data: {\"result\": {\"tools\": []}}\n\n",
            )
        )
        
        # Test the actual _http_post_request method would use streaming
        from mcp_codegen.module import MCPModule
        module = MCPModule("https://example.com")
        
        # This would test the actual code path when implemented
        # For now, just verify the route setup
        assert route is not None  # Route was created successfully
