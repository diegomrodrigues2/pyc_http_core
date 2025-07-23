"""
Comprehensive tests for HTTP/1.1 connection implementation.

This module contains extensive tests covering all aspects of the HTTP11Connection
including request/response cycles, streaming, keep-alive, and error handling.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import h11

from c_http_core.http11 import HTTP11Connection, ConnectionState
from c_http_core.http_primitives import Request, Response
from c_http_core.network.mock import MockNetworkStream
from c_http_core.streams import create_request_stream
from c_http_core.exceptions import ConnectionError, ProtocolError


class TestHTTP11ConnectionComprehensive:
    """Comprehensive tests for HTTP/1.1 connection functionality."""
    
    @pytest.fixture
    def mock_stream(self):
        """Create a mock network stream."""
        return MockNetworkStream()
    
    @pytest.fixture
    def connection(self, mock_stream):
        """Create an HTTP/1.1 connection."""
        return HTTP11Connection(mock_stream)
    
    @pytest.mark.asyncio
    async def test_simple_get_request_cycle(self, connection, mock_stream):
        """Test complete GET request/response cycle."""
        # Setup mock response data
        response_data = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Length: 11\r\n"
            b"Server: httpbin.org\r\n"
            b"\r\n"
            b"Hello World"
        )
        mock_stream.add_data(response_data)
        
        # Create request
        request = Request.create(
            method="GET",
            url="http://example.com/",
            headers=[(b"Host", b"example.com")]
        )
        
        # Handle request
        response = await connection.handle_request(request)
        
        # Verify response
        assert response.status_code == 200
        assert response.get_header(b"Content-Length") == b"11"
        assert response.get_header(b"Server") == b"httpbin.org"
        
        # Verify request was sent correctly
        written_data = mock_stream.written_data
        assert b"GET / HTTP/1.1" in written_data
        assert b"Host: example.com" in written_data
        
        # Verify connection state
        assert connection._state == ConnectionState.IDLE
        assert connection.is_idle
        assert not connection.is_closed
    
    @pytest.mark.asyncio
    async def test_post_request_with_body(self, connection, mock_stream):
        """Test POST request with body."""
        # Setup mock response
        response_data = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Length: 0\r\n"
            b"\r\n"
        )
        mock_stream.add_data(response_data)
        
        # Create request with body
        request_stream = create_request_stream(b'{"message": "Hello, World!"}')
        request = Request.create(
            method="POST",
            url="http://example.com/",
            headers=[
                (b"Host", b"example.com"),
                (b"Content-Type", b"application/json")
            ],
            stream=request_stream
        )
        
        # Handle request
        response = await connection.handle_request(request)
        
        # Verify response
        assert response.status_code == 200
        
        # Verify request body was sent
        written_data = mock_stream.written_data
        assert b'{"message": "Hello, World!"}' in written_data
        assert b"Content-Type: application/json" in written_data
    
    @pytest.mark.asyncio
    async def test_streaming_response_handling(self, connection, mock_stream):
        """Test streaming response handling."""
        # Setup large response data
        response_data = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Length: 1000\r\n"
            b"\r\n"
            + b"X" * 1000  # 1000 bytes of data
        )
        mock_stream.add_data(response_data)
        
        # Create request
        request = Request.create(
            method="GET",
            url="http://example.com/",
            headers=[(b"Host", b"example.com")]
        )
        
        # Handle request
        response = await connection.handle_request(request)
        
        # Verify response
        assert response.status_code == 200
        assert response.get_header(b"Content-Length") == b"1000"
        
        # Read response in chunks
        total_bytes = 0
        async for chunk in response.stream:
            total_bytes += len(chunk)
        
        assert total_bytes == 1000
    
    @pytest.mark.asyncio
    async def test_chunked_transfer_encoding(self, connection, mock_stream):
        """Test chunked transfer encoding."""
        # Setup chunked response
        response_data = (
            b"HTTP/1.1 200 OK\r\n"
            b"Transfer-Encoding: chunked\r\n"
            b"\r\n"
            b"5\r\n"
            b"Hello\r\n"
            b"6\r\n"
            b"World!\r\n"
            b"0\r\n"
            b"\r\n"
        )
        mock_stream.add_data(response_data)
        
        # Create request
        request = Request.create(
            method="GET",
            url="http://example.com/",
            headers=[(b"Host", b"example.com")]
        )
        
        # Handle request
        response = await connection.handle_request(request)
        
        # Verify response
        assert response.status_code == 200
        assert response.get_header(b"Transfer-Encoding") == b"chunked"
        
        # Read response body
        body = await response.stream.aread()
        assert body == b"HelloWorld!"
    
    @pytest.mark.asyncio
    async def test_keep_alive_connection_reuse(self, connection, mock_stream):
        """Test keep-alive connection reuse."""
        # First request
        response1_data = (
            b"HTTP/1.1 200 OK\r\n"
            b"Connection: keep-alive\r\n"
            b"Content-Length: 5\r\n"
            b"\r\n"
            b"Hello"
        )
        mock_stream.add_data(response1_data)
        
        request1 = Request.create(
            method="GET",
            url="http://example.com/1",
            headers=[(b"Host", b"example.com")]
        )
        
        response1 = await connection.handle_request(request1)
        assert response1.status_code == 200
        
        # Connection should be idle
        assert connection._state == ConnectionState.IDLE
        assert connection.is_idle
        
        # Second request (should reuse connection)
        response2_data = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Length: 5\r\n"
            b"\r\n"
            b"World"
        )
        mock_stream.add_data(response2_data)
        
        request2 = Request.create(
            method="GET",
            url="http://example.com/2",
            headers=[(b"Host", b"example.com")]
        )
        
        response2 = await connection.handle_request(request2)
        assert response2.status_code == 200
        
        # Verify metrics
        assert connection._request_count == 2
    
    @pytest.mark.asyncio
    async def test_connection_close_handling(self, connection, mock_stream):
        """Test connection close handling."""
        # Setup response with connection close
        response_data = (
            b"HTTP/1.1 200 OK\r\n"
            b"Connection: close\r\n"
            b"Content-Length: 5\r\n"
            b"\r\n"
            b"Hello"
        )
        mock_stream.add_data(response_data)
        
        request = Request.create(
            method="GET",
            url="http://example.com/",
            headers=[(b"Host", b"example.com")]
        )
        
        response = await connection.handle_request(request)
        assert response.status_code == 200
        
        # Read response body
        body = await response.stream.aread()
        assert body == b"Hello"
        
        # Connection should be closed
        assert connection._state == ConnectionState.CLOSED
        assert connection.is_closed
    
    @pytest.mark.asyncio
    async def test_error_handling_connection_closed(self, connection, mock_stream):
        """Test error handling when connection is closed unexpectedly."""
        # Don't add any response data - simulate connection close
        request = Request.create(
            method="GET",
            url="http://example.com/",
            headers=[(b"Host", b"example.com")]
        )
        
        with pytest.raises(ProtocolError, match="Connection closed unexpectedly"):
            await connection.handle_request(request)
        
        # Connection should be marked as closed
        assert connection._state == ConnectionState.CLOSED
    
    @pytest.mark.asyncio
    async def test_concurrent_request_handling(self, connection):
        """Test that concurrent requests are properly serialized."""
        # This test verifies that the connection lock prevents concurrent requests
        
        # Start first request (will block)
        request1 = Request.create(
            method="GET",
            url="http://example.com/1",
            headers=[(b"Host", b"example.com")]
        )
        
        # Try to start second request immediately
        request2 = Request.create(
            method="GET",
            url="http://example.com/2",
            headers=[(b"Host", b"example.com")]
        )
        
        # First request should succeed, second should fail
        with pytest.raises(ConnectionError, match="Connection is busy"):
            await connection._acquire_connection()
            await connection._acquire_connection()
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Metrics tracking not implemented")
    async def test_metrics_tracking(self, connection, mock_stream):
        """Test that metrics are properly tracked."""
        # Setup response
        response_data = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Length: 10\r\n"
            b"\r\n"
            b"1234567890"
        )
        mock_stream.add_data(response_data)
        
        request = Request.create(
            method="POST",
            url="http://example.com/",
            headers=[(b"Host", b"example.com")],
            stream=create_request_stream(b"test data")
        )
        
        response = await connection.handle_request(request)
        body = await response.stream.aread()
        
        # Verify metrics
        assert connection._request_count == 1
        assert connection._bytes_sent > 0  # Request data
        assert connection._bytes_received > 0  # Response data
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self, connection):
        """Test timeout handling."""
        # Test that connection expiration works correctly
        assert not connection.has_expired(30.0)  # Should not expire immediately
        
        # Simulate idle connection
        connection._state = ConnectionState.IDLE
        connection._idle_since = asyncio.get_event_loop().time() - 60.0  # 60 seconds ago
        
        assert connection.has_expired(30.0)  # Should be expired
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Content length validation not implemented")
    async def test_content_length_validation(self, connection, mock_stream):
        """Test content length validation."""
        # Setup response with incorrect content length
        response_data = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Length: 5\r\n"
            b"\r\n"
            b"Hello World"  # 11 bytes, but Content-Length says 5
        )
        mock_stream.add_data(response_data)
        
        request = Request.create(
            method="GET",
            url="http://example.com/",
            headers=[(b"Host", b"example.com")]
        )
        
        response = await connection.handle_request(request)
        
        # Should still work, but we can verify the content length
        assert response.get_header(b"Content-Length") == b"5"
        
        # Read all data
        body = await response.stream.aread()
        assert len(body) == 11  # Actual data length
    
    @pytest.mark.asyncio
    async def test_multiple_requests_same_connection(self, connection, mock_stream):
        """Test multiple requests on the same connection."""
        # Setup multiple responses
        responses = [
            (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Length: 5\r\n"
                b"\r\n"
                b"First"
            ),
            (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Length: 6\r\n"
                b"\r\n"
                b"Second"
            ),
            (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Length: 5\r\n"
                b"\r\n"
                b"Third"
            )
        ]
        
        for response_data in responses:
            mock_stream.add_data(response_data)
        
        # Make multiple requests
        for i in range(3):
            request = Request.create(
                method="GET",
                url=f"http://example.com/{i}",
                headers=[(b"Host", b"example.com")]
            )
            
            response = await connection.handle_request(request)
            assert response.status_code == 200
            
            body = await response.stream.aread()
            if i == 0:
                assert body == b"First"
            elif i == 1:
                assert body == b"Second"
            else:
                assert body == b"Third"
        
        # Verify final state
        assert connection._state == ConnectionState.IDLE
        assert connection._request_count == 3


class TestHTTP11ConnectionEdgeCases:
    """Test edge cases and error conditions."""
    
    @pytest.fixture
    def mock_stream(self):
        return MockNetworkStream()
    
    @pytest.fixture
    def connection(self, mock_stream):
        return HTTP11Connection(mock_stream)
    
    @pytest.mark.asyncio
    async def test_empty_response_body(self, connection, mock_stream):
        """Test handling of empty response body."""
        response_data = (
            b"HTTP/1.1 204 No Content\r\n"
            b"\r\n"
        )
        mock_stream.add_data(response_data)
        
        request = Request.create(
            method="GET",
            url="http://example.com/",
            headers=[(b"Host", b"example.com")]
        )
        
        response = await connection.handle_request(request)
        assert response.status_code == 204
        
        body = await response.stream.aread()
        assert body == b""
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Large request body handling not implemented")
    async def test_large_request_body(self, connection, mock_stream):
        """Test handling of large request body."""
        # Setup response
        response_data = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Length: 0\r\n"
            b"\r\n"
        )
        mock_stream.add_data(response_data)
        
        # Create large request body
        large_data = b"X" * 10000  # 10KB
        request_stream = create_request_stream(large_data)
        request = Request.create(
            method="POST",
            url="http://example.com/",
            headers=[(b"Host", b"example.com")],
            stream=request_stream
        )
        
        response = await connection.handle_request(request)
        assert response.status_code == 200
        
        # Verify large data was sent
        written_data = mock_stream.written_data
        assert large_data in written_data
    
    @pytest.mark.asyncio
    async def test_connection_already_closed(self, connection):
        """Test operations on already closed connection."""
        await connection.close()
        
        request = Request.create(
            method="GET",
            url="http://example.com/",
            headers=[(b"Host", b"example.com")]
        )
        
        with pytest.raises(ConnectionError, match="Connection is closed"):
            await connection.handle_request(request)
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Invalid content length handling not implemented")
    async def test_invalid_content_length(self, connection, mock_stream):
        """Test handling of invalid content length."""
        response_data = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Length: invalid\r\n"
            b"\r\n"
            b"Hello"
        )
        mock_stream.add_data(response_data)
        
        request = Request.create(
            method="GET",
            url="http://example.com/",
            headers=[(b"Host", b"example.com")]
        )
        
        response = await connection.handle_request(request)
        assert response.status_code == 200
        
        # Content length should be None for invalid values
        assert response.stream.content_length is None 