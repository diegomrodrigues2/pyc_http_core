"""
Tests for network interfaces and mock implementations.

This module contains comprehensive tests for the NetworkStream and NetworkBackend
interfaces, as well as their mock implementations.
"""

import pytest
import asyncio
from typing import Optional

from c_http_core.network import (
    NetworkStream,
    NetworkBackend,
    MockNetworkStream,
    MockNetworkBackend,
)


class TestMockNetworkStream:
    """Test cases for MockNetworkStream."""
    
    @pytest.mark.asyncio
    async def test_read_write_basic(self):
        """Test basic read and write operations."""
        stream = MockNetworkStream()
        
        # Test write
        await stream.write(b"hello world")
        assert stream.written_data == b"hello world"

        # Add data manually for reading
        stream.add_data(b"hello world")

        # Test read
        data = await stream.read(5)
        assert data == b"hello"

        data = await stream.read()
        assert data == b" world"
    
    @pytest.mark.asyncio
    async def test_read_empty_stream(self):
        """Test reading from an empty stream."""
        stream = MockNetworkStream()
        
        data = await stream.read()
        assert data == b""
        
        data = await stream.read(10)
        assert data == b""
    
    @pytest.mark.asyncio
    async def test_read_with_initial_data(self):
        """Test reading from a stream with initial data."""
        stream = MockNetworkStream(b"initial data")
        
        data = await stream.read(7)
        assert data == b"initial"
        
        data = await stream.read()
        assert data == b" data"
    
    @pytest.mark.asyncio
    async def test_read_max_bytes(self):
        """Test reading with max_bytes parameter."""
        stream = MockNetworkStream(b"hello world")
        
        data = await stream.read(3)
        assert data == b"hel"
        
        data = await stream.read(20)  # More than available
        assert data == b"lo world"
    
    @pytest.mark.asyncio
    async def test_write_multiple_chunks(self):
        """Test writing multiple chunks of data."""
        stream = MockNetworkStream()
        
        await stream.write(b"hello")
        await stream.write(b" ")
        await stream.write(b"world")
        
        assert stream.written_data == b"hello world"
    
    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing the stream."""
        stream = MockNetworkStream()
        assert not stream.is_closed
        
        await stream.aclose()
        assert stream.is_closed
    
    @pytest.mark.asyncio
    async def test_read_after_close(self):
        """Test reading from a closed stream raises error."""
        stream = MockNetworkStream(b"data")
        await stream.aclose()
        
        with pytest.raises(RuntimeError, match="Stream is closed"):
            await stream.read()
    
    @pytest.mark.asyncio
    async def test_write_after_close(self):
        """Test writing to a closed stream raises error."""
        stream = MockNetworkStream()
        await stream.aclose()
        
        with pytest.raises(RuntimeError, match="Stream is closed"):
            await stream.write(b"data")
    
    def test_get_extra_info(self):
        """Test getting extra information from the stream."""
        stream = MockNetworkStream()
        
        # Test default values
        assert stream.get_extra_info("socket") is None
        assert stream.get_extra_info("peername") is None
        
        # Test setting and getting values
        stream.set_extra_info("socket", 123)
        stream.set_extra_info("peername", ("127.0.0.1", 8080))
        
        assert stream.get_extra_info("socket") == 123
        assert stream.get_extra_info("peername") == ("127.0.0.1", 8080)
    
    def test_add_data(self):
        """Test adding data to the stream."""
        stream = MockNetworkStream(b"initial")
        
        stream.add_data(b" more")
        stream.add_data(b" data")
        
        assert stream._data == b"initial more data"
    
    def test_is_closed_property(self):
        """Test the is_closed property."""
        stream = MockNetworkStream()
        assert not stream.is_closed
        
        stream._closed = True
        assert stream.is_closed


class TestMockNetworkBackend:
    """Test cases for MockNetworkBackend."""
    
    @pytest.mark.asyncio
    async def test_connect_tcp_basic(self):
        """Test basic TCP connection."""
        backend = MockNetworkBackend()
        stream = await backend.connect_tcp("example.com", 80)
        
        assert isinstance(stream, MockNetworkStream)
        assert not stream.is_closed
        assert stream.get_extra_info("peername") == ("example.com", 80)
        assert stream.get_extra_info("sockname") == ("127.0.0.1", 12345)
    
    @pytest.mark.asyncio
    async def test_connect_tcp_reuse_connection(self):
        """Test that TCP connections are reused for the same host/port."""
        backend = MockNetworkBackend()
        
        stream1 = await backend.connect_tcp("example.com", 80)
        stream2 = await backend.connect_tcp("example.com", 80)
        
        assert stream1 is stream2  # Same connection object
    
    @pytest.mark.asyncio
    async def test_connect_tcp_different_hosts(self):
        """Test that different hosts get different connections."""
        backend = MockNetworkBackend()
        
        stream1 = await backend.connect_tcp("example.com", 80)
        stream2 = await backend.connect_tcp("google.com", 80)
        
        assert stream1 is not stream2  # Different connection objects
    
    @pytest.mark.asyncio
    async def test_connect_tls_basic(self):
        """Test basic TLS connection."""
        backend = MockNetworkBackend()
        tcp_stream = await backend.connect_tcp("example.com", 443)
        tls_stream = await backend.connect_tls(tcp_stream, "example.com", 443)
        
        assert isinstance(tls_stream, MockNetworkStream)
        assert tls_stream.get_extra_info("ssl_object") is True
        assert tls_stream.get_extra_info("selected_alpn_protocol") == "http/1.1"
    
    @pytest.mark.asyncio
    async def test_connect_tls_with_alpn(self):
        """Test TLS connection with ALPN protocols."""
        backend = MockNetworkBackend()
        tcp_stream = await backend.connect_tcp("example.com", 443)
        tls_stream = await backend.connect_tls(
            tcp_stream, 
            "example.com", 
            443, 
            alpn_protocols=["h2", "http/1.1"]
        )
        
        assert tls_stream.get_extra_info("selected_alpn_protocol") == "h2"
    
    @pytest.mark.asyncio
    async def test_start_tls(self):
        """Test starting TLS on an existing stream."""
        backend = MockNetworkBackend()
        stream = await backend.connect_tcp("example.com", 80)
        
        tls_stream = await backend.start_tls(stream, "example.com")
        
        assert tls_stream is stream  # Same stream object
        assert stream.get_extra_info("ssl_object") is True
        assert stream.get_extra_info("selected_alpn_protocol") == "http/1.1"
    
    @pytest.mark.asyncio
    async def test_start_tls_with_alpn(self):
        """Test starting TLS with ALPN protocols."""
        backend = MockNetworkBackend()
        stream = await backend.connect_tcp("example.com", 80)
        
        tls_stream = await backend.start_tls(
            stream, 
            "example.com", 
            alpn_protocols=["h2"]
        )
        
        assert tls_stream.get_extra_info("selected_alpn_protocol") == "h2"
    
    def test_get_connection(self):
        """Test getting a connection by host and port."""
        backend = MockNetworkBackend()
        
        # No connection exists yet
        assert backend.get_connection("example.com", 80) is None
        
        # Create connection
        asyncio.run(backend.connect_tcp("example.com", 80))
        
        # Now connection exists
        connection = backend.get_connection("example.com", 80)
        assert connection is not None
        assert isinstance(connection, MockNetworkStream)
    
    def test_get_tls_connection(self):
        """Test getting a TLS connection by host and port."""
        backend = MockNetworkBackend()
        
        # No TLS connection exists yet
        assert backend.get_tls_connection("example.com", 443) is None
        
        # Create TLS connection
        async def create_tls():
            tcp_stream = await backend.connect_tcp("example.com", 443)
            await backend.connect_tls(tcp_stream, "example.com", 443)
        
        asyncio.run(create_tls())
        
        # Now TLS connection exists
        connection = backend.get_tls_connection("example.com", 443)
        assert connection is not None
        assert isinstance(connection, MockNetworkStream)
        assert connection.get_extra_info("ssl_object") is True
    
    def test_add_connection_data(self):
        """Test adding data to a connection."""
        backend = MockNetworkBackend()
        
        # Create connection
        asyncio.run(backend.connect_tcp("example.com", 80))
        
        # Add data
        backend.add_connection_data("example.com", 80, b"test data")
        
        # Verify data was added
        connection = backend.get_connection("example.com", 80)
        assert connection._data == b"test data"
    
    def test_reset(self):
        """Test resetting all connections."""
        backend = MockNetworkBackend()
        
        # Create some connections
        async def create_connections():
            await backend.connect_tcp("example.com", 80)
            tcp_stream = await backend.connect_tcp("google.com", 443)
            await backend.connect_tls(tcp_stream, "google.com", 443)
        
        asyncio.run(create_connections())
        
        # Verify connections exist
        assert backend.get_connection("example.com", 80) is not None
        assert backend.get_tls_connection("google.com", 443) is not None
        
        # Reset
        backend.reset()
        
        # Verify connections are gone
        assert backend.get_connection("example.com", 80) is None
        assert backend.get_tls_connection("google.com", 443) is None
        assert backend._connection_count == 0


class TestNetworkInterfaces:
    """Test cases for the abstract interfaces."""
    
    def test_network_stream_interface(self):
        """Test that NetworkStream is an abstract base class."""
        with pytest.raises(TypeError):
            NetworkStream()
    
    def test_network_backend_interface(self):
        """Test that NetworkBackend is an abstract base class."""
        with pytest.raises(TypeError):
            NetworkBackend()
    
    def test_mock_implements_network_stream(self):
        """Test that MockNetworkStream implements NetworkStream interface."""
        stream = MockNetworkStream()
        assert isinstance(stream, NetworkStream)
    
    def test_mock_implements_network_backend(self):
        """Test that MockNetworkBackend implements NetworkBackend interface."""
        backend = MockNetworkBackend()
        assert isinstance(backend, NetworkBackend)


class TestNetworkIntegration:
    """Integration tests for network components."""
    
    @pytest.mark.asyncio
    async def test_tcp_to_tls_upgrade(self):
        """Test upgrading a TCP connection to TLS."""
        backend = MockNetworkBackend()
        
        # Create TCP connection
        tcp_stream = await backend.connect_tcp("example.com", 443)
        assert not tcp_stream.get_extra_info("ssl_object")
        
        # Upgrade to TLS
        tls_stream = await backend.connect_tls(tcp_stream, "example.com", 443)
        assert tls_stream.get_extra_info("ssl_object") is True
        assert tls_stream.get_extra_info("selected_alpn_protocol") == "http/1.1"
    
    @pytest.mark.asyncio
    async def test_multiple_connections(self):
        """Test managing multiple connections."""
        backend = MockNetworkBackend()
        
        # Create multiple connections
        conn1 = await backend.connect_tcp("example.com", 80)
        conn2 = await backend.connect_tcp("google.com", 80)
        conn3 = await backend.connect_tcp("example.com", 443)
        
        # Verify they are different
        assert conn1 is not conn2
        assert conn1 is not conn3
        assert conn2 is not conn3
        
        # Verify connection reuse
        conn1_reused = await backend.connect_tcp("example.com", 80)
        assert conn1 is conn1_reused
    
    @pytest.mark.asyncio
    async def test_stream_data_flow(self):
        """Test complete data flow through a stream."""
        backend = MockNetworkBackend()
        stream = await backend.connect_tcp("example.com", 80)
        
        # Add data to the stream
        backend.add_connection_data("example.com", 80, b"HTTP/1.1 200 OK\r\n\r\nHello")
        
        # Read the data
        data = await stream.read()
        assert data == b"HTTP/1.1 200 OK\r\n\r\nHello"
        
        # Write data back
        await stream.write(b"GET / HTTP/1.1\r\n\r\n")
        assert stream.written_data == b"GET / HTTP/1.1\r\n\r\n" 