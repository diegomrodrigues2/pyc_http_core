"""
Basic tests for HTTP/1.1 connection implementation.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from c_http_core.http11 import HTTP11Connection, ConnectionState
from c_http_core.http_primitives import Request, Response
from c_http_core.network.mock import MockNetworkStream
from c_http_core.streams import create_request_stream


class TestHTTP11Connection:
    """Test HTTP/1.1 connection functionality."""
    
    @pytest.fixture
    def mock_stream(self):
        """Create a mock network stream."""
        return MockNetworkStream()
    
    @pytest.fixture
    def connection(self, mock_stream):
        """Create an HTTP/1.1 connection."""
        return HTTP11Connection(mock_stream)
    
    @pytest.mark.asyncio
    async def test_connection_initialization(self, connection):
        """Test connection initialization."""
        assert connection._state == ConnectionState.NEW
        assert connection._h11_connection is not None
        assert connection._request_count == 0
        assert connection._bytes_sent == 0
        assert connection._bytes_received == 0
    
    @pytest.mark.asyncio
    async def test_connection_properties(self, connection):
        """Test connection properties."""
        assert not connection.is_closed
        assert not connection.is_idle
        
        # Test expired check
        assert not connection.has_expired(30.0)  # Should not expire immediately
    
    @pytest.mark.asyncio
    async def test_connection_close(self, connection, mock_stream):
        """Test connection close."""
        await connection.close()
        assert connection.is_closed
        assert mock_stream.closed
    
    @pytest.mark.asyncio
    async def test_acquire_connection(self, connection):
        """Test connection acquisition."""
        await connection._acquire_connection()
        assert connection._state == ConnectionState.ACTIVE
    
    @pytest.mark.asyncio
    async def test_acquire_closed_connection(self, connection):
        """Test acquiring a closed connection."""
        await connection.close()
        
        with pytest.raises(Exception):  # Should raise ConnectionError
            await connection._acquire_connection()
    
    @pytest.mark.asyncio
    async def test_acquire_busy_connection(self, connection):
        """Test acquiring a busy connection."""
        await connection._acquire_connection()
        
        with pytest.raises(Exception):  # Should raise ConnectionError
            await connection._acquire_connection()
    
    @pytest.mark.asyncio
    async def test_send_event(self, connection, mock_stream):
        """Test sending h11 events."""
        # Mock h11 connection to return some data
        connection._h11_connection.send = MagicMock(return_value=b"test data")
        
        # Create a mock h11 event
        mock_event = MagicMock()
        
        await connection._send_event(mock_event)
        
        # Verify data was written
        assert b"test data" in mock_stream.written_data
        assert connection._bytes_sent == 9  # len("test data")
    
    @pytest.mark.asyncio
    async def test_get_content_length(self, connection):
        """Test content length extraction."""
        headers = [
            (b"Content-Length", b"123"),
            (b"Host", b"example.com")
        ]
        
        length = connection._get_content_length(headers)
        assert length == 123
    
    @pytest.mark.asyncio
    async def test_get_content_length_invalid(self, connection):
        """Test content length extraction with invalid value."""
        headers = [
            (b"Content-Length", b"invalid"),
            (b"Host", b"example.com")
        ]
        
        length = connection._get_content_length(headers)
        assert length is None
    
    @pytest.mark.asyncio
    async def test_is_chunked(self, connection):
        """Test chunked transfer encoding detection."""
        headers = [
            (b"Transfer-Encoding", b"chunked"),
            (b"Host", b"example.com")
        ]
        
        assert connection._is_chunked(headers) is True
    
    @pytest.mark.asyncio
    async def test_is_not_chunked(self, connection):
        """Test non-chunked transfer encoding detection."""
        headers = [
            (b"Content-Length", b"123"),
            (b"Host", b"example.com")
        ]
        
        assert connection._is_chunked(headers) is False 