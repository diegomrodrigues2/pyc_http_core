"""
Network stream interface for c_http_core.

This module defines the NetworkStream interface that all network stream
implementations must follow for consistent behavior across the library.
"""

from abc import ABC, abstractmethod
from typing import Optional, Union
import asyncio


class NetworkStream(ABC):
    """
    Interface for network streams with async I/O operations.
    
    This interface defines the contract that all network stream implementations
    must follow. It provides methods for reading, writing, and managing
    network connections in an asynchronous manner.
    """
    
    @abstractmethod
    async def read(self, max_bytes: Optional[int] = None) -> bytes:
        """
        Read data from the stream.
        
        Args:
            max_bytes: Maximum number of bytes to read. If None, reads
                      until the stream is closed or no more data is available.
        
        Returns:
            The data read from the stream.
        
        Raises:
            RuntimeError: If the stream is closed.
            OSError: If a network error occurs.
        """
        pass
    
    @abstractmethod
    async def write(self, data: bytes) -> None:
        """
        Write data to the stream.
        
        Args:
            data: The data to write to the stream.
        
        Raises:
            RuntimeError: If the stream is closed.
            OSError: If a network error occurs.
        """
        pass
    
    @abstractmethod
    async def aclose(self) -> None:
        """
        Close the stream and cleanup resources.
        
        This method should be called when the stream is no longer needed
        to ensure proper cleanup of system resources.
        """
        pass
    
    @abstractmethod
    def get_extra_info(self, name: str) -> Optional[Union[str, int, bool]]:
        """
        Get extra information about the stream.
        
        Args:
            name: The name of the information to retrieve. Common values include:
                 - "socket": The underlying socket file descriptor
                 - "peername": The remote endpoint address
                 - "sockname": The local endpoint address
                 - "ssl_object": Whether the stream is SSL/TLS encrypted
        
        Returns:
            The requested information or None if not available.
        """
        pass
    
    @property
    @abstractmethod
    def is_closed(self) -> bool:
        """
        Check if the stream is closed.
        
        Returns:
            True if the stream is closed, False otherwise.
        """
        pass 