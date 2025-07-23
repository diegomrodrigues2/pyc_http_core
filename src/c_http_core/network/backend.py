"""
Network backend interface for c_http_core.

This module defines the NetworkBackend interface that provides
abstractions for creating and managing network connections.
"""

from abc import ABC, abstractmethod
from typing import Optional, List
from .stream import NetworkStream


class NetworkBackend(ABC):
    """
    Interface for network backend implementations.
    
    This interface defines the contract that all network backend implementations
    must follow. It provides methods for creating TCP and TLS connections
    in an asynchronous manner.
    """
    
    @abstractmethod
    async def connect_tcp(
        self, 
        host: str, 
        port: int, 
        timeout: Optional[float] = None
    ) -> NetworkStream:
        """
        Connect to a TCP endpoint.
        
        Args:
            host: The hostname or IP address to connect to.
            port: The port number to connect to.
            timeout: Optional timeout in seconds for the connection.
        
        Returns:
            A NetworkStream representing the TCP connection.
        
        Raises:
            OSError: If the connection fails.
            TimeoutError: If the connection times out.
        """
        pass
    
    @abstractmethod
    async def connect_tls(
        self,
        stream: NetworkStream,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        alpn_protocols: Optional[List[str]] = None,
    ) -> NetworkStream:
        """
        Upgrade a TCP stream to TLS.
        
        Args:
            stream: The existing TCP NetworkStream to upgrade.
            host: The hostname for TLS certificate verification.
            port: The port number (used for logging/debugging).
            timeout: Optional timeout in seconds for the TLS handshake.
            alpn_protocols: Optional list of ALPN protocols to negotiate.
                           Common values: ['h2', 'http/1.1']
        
        Returns:
            A NetworkStream representing the TLS connection.
        
        Raises:
            OSError: If the TLS handshake fails.
            TimeoutError: If the TLS handshake times out.
        """
        pass
    
    @abstractmethod
    async def start_tls(
        self,
        stream: NetworkStream,
        host: str,
        alpn_protocols: Optional[List[str]] = None,
    ) -> NetworkStream:
        """
        Start TLS on an existing stream (for protocol upgrades).
        
        This method is used for upgrading existing connections to TLS,
        such as when implementing STARTTLS or upgrading HTTP to HTTPS.
        
        Args:
            stream: The existing NetworkStream to upgrade.
            host: The hostname for TLS certificate verification.
            alpn_protocols: Optional list of ALPN protocols to negotiate.
                           Common values: ['h2', 'http/1.1']
        
        Returns:
            A NetworkStream representing the TLS connection.
        
        Raises:
            OSError: If the TLS handshake fails.
        """
        pass 