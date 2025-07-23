"""
Mock network implementations for testing.

This module provides mock implementations of NetworkStream and NetworkBackend
that can be used for unit testing without requiring actual network connections.
"""

import asyncio
from typing import Optional, Union, Dict, Any, List, Tuple
from .stream import NetworkStream
from .backend import NetworkBackend


class MockNetworkStream(NetworkStream):
    """
    Mock network stream for testing.
    
    This implementation simulates a network stream in memory,
    allowing tests to verify network behavior without actual I/O.
    """
    
    def __init__(self, data: bytes = b""):
        """
        Initialize the mock stream.
        
        Args:
            data: Initial data to be available for reading.
        """
        self._data = data
        self._position = 0
        self._closed = False
        self._extra_info: Dict[str, Any] = {}
        self._write_buffer: List[bytes] = []
    
    async def read(self, max_bytes: Optional[int] = None) -> bytes:
        """
        Read data from the mock stream.
        
        Args:
            max_bytes: Maximum number of bytes to read.
        
        Returns:
            The data read from the stream.
        
        Raises:
            RuntimeError: If the stream is closed.
        """
        if self._closed:
            raise RuntimeError("Stream is closed")
        
        if self._position >= len(self._data):
            return b""
        
        if max_bytes is None:
            result = self._data[self._position:]
            self._position = len(self._data)
        else:
            end = min(self._position + max_bytes, len(self._data))
            result = self._data[self._position:end]
            self._position = end
        
        return result
    
    async def write(self, data: bytes) -> None:
        """
        Write data to the mock stream.
        
        Args:
            data: The data to write.
        
        Raises:
            RuntimeError: If the stream is closed.
        """
        if self._closed:
            raise RuntimeError("Stream is closed")
        
        self._write_buffer.append(data)
    
    async def aclose(self) -> None:
        """Close the mock stream."""
        self._closed = True
    
    def get_extra_info(self, name: str) -> Optional[Union[str, int, bool]]:
        """
        Get extra information about the mock stream.
        
        Args:
            name: The name of the information to retrieve.
        
        Returns:
            The requested information or None if not available.
        """
        return self._extra_info.get(name)
    
    @property
    def is_closed(self) -> bool:
        """Check if the mock stream is closed."""
        return self._closed
    
    @property
    def written_data(self) -> bytes:
        """Get all data that was written to the stream."""
        return b"".join(self._write_buffer)
    
    def set_extra_info(self, name: str, value: Any) -> None:
        """
        Set extra information for the mock stream.
        
        Args:
            name: The name of the information.
            value: The value to set.
        """
        self._extra_info[name] = value
    
    def add_data(self, data: bytes) -> None:
        """
        Add data to be available for reading.
        
        Args:
            data: The data to add.
        """
        self._data += data


class MockNetworkBackend(NetworkBackend):
    """
    Mock network backend for testing.
    
    This implementation provides mock network connections that can be
    used for testing without requiring actual network I/O.
    """
    
    def __init__(self):
        """Initialize the mock backend."""
        self._connections: Dict[Tuple[str, int], MockNetworkStream] = {}
        self._tls_connections: Dict[Tuple[str, int], MockNetworkStream] = {}
        self._connection_count = 0
    
    async def connect_tcp(
        self, 
        host: str, 
        port: int, 
        timeout: Optional[float] = None
    ) -> MockNetworkStream:
        """
        Create a mock TCP connection.
        
        Args:
            host: The hostname to connect to.
            port: The port number to connect to.
            timeout: Ignored in mock implementation.
        
        Returns:
            A MockNetworkStream representing the connection.
        """
        key = (host, port)
        
        if key not in self._connections:
            stream = MockNetworkStream()
            stream.set_extra_info("socket", self._connection_count)
            stream.set_extra_info("peername", (host, port))
            stream.set_extra_info("sockname", ("127.0.0.1", 12345))
            self._connections[key] = stream
            self._connection_count += 1
        
        return self._connections[key]
    
    async def connect_tls(
        self,
        stream: MockNetworkStream,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        alpn_protocols: Optional[List[str]] = None,
    ) -> MockNetworkStream:
        """
        Create a mock TLS connection.
        
        Args:
            stream: The existing TCP stream to upgrade.
            host: The hostname for TLS verification.
            port: The port number.
            timeout: Ignored in mock implementation.
            alpn_protocols: ALPN protocols to negotiate.
        
        Returns:
            A MockNetworkStream representing the TLS connection.
        """
        # Create a new stream for TLS
        tls_stream = MockNetworkStream()
        
        # Copy extra info from the original stream
        for key, value in stream._extra_info.items():
            tls_stream.set_extra_info(key, value)
        
        # Add TLS-specific info
        tls_stream.set_extra_info("ssl_object", True)
        tls_stream.set_extra_info("selected_alpn_protocol", 
                                 alpn_protocols[0] if alpn_protocols else "http/1.1")
        
        # Store the TLS connection
        key = (host, port)
        self._tls_connections[key] = tls_stream
        
        return tls_stream
    
    async def start_tls(
        self,
        stream: MockNetworkStream,
        host: str,
        alpn_protocols: Optional[List[str]] = None,
    ) -> MockNetworkStream:
        """
        Start TLS on an existing mock stream.
        
        Args:
            stream: The existing stream to upgrade.
            host: The hostname for TLS verification.
            alpn_protocols: ALPN protocols to negotiate.
        
        Returns:
            A MockNetworkStream representing the TLS connection.
        """
        # Add TLS info to the existing stream
        stream.set_extra_info("ssl_object", True)
        stream.set_extra_info("selected_alpn_protocol", 
                             alpn_protocols[0] if alpn_protocols else "http/1.1")
        
        return stream
    
    def get_connection(self, host: str, port: int) -> Optional[MockNetworkStream]:
        """
        Get a mock connection for testing.
        
        Args:
            host: The hostname.
            port: The port number.
        
        Returns:
            The mock connection if it exists, None otherwise.
        """
        key = (host, port)
        return self._connections.get(key)
    
    def get_tls_connection(self, host: str, port: int) -> Optional[MockNetworkStream]:
        """
        Get a mock TLS connection for testing.
        
        Args:
            host: The hostname.
            port: The port number.
        
        Returns:
            The mock TLS connection if it exists, None otherwise.
        """
        key = (host, port)
        return self._tls_connections.get(key)
    
    def add_connection_data(self, host: str, port: int, data: bytes) -> None:
        """
        Add data to a mock connection for testing.
        
        Args:
            host: The hostname.
            port: The port number.
            data: The data to add.
        """
        connection = self.get_connection(host, port)
        if connection:
            connection.add_data(data)
    
    def reset(self) -> None:
        """Reset all mock connections."""
        self._connections.clear()
        self._tls_connections.clear()
        self._connection_count = 0 