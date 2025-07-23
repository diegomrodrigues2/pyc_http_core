"""
Streaming framework for c_http_core.

This module provides streaming abstractions for HTTP request and response bodies.
It implements backpressure natural where consumption drives reading from the network.
"""

from abc import ABC, abstractmethod
from typing import (
    AsyncIterable, 
    Optional, 
    Union, 
    List, 
    Dict, 
    Any,
    TYPE_CHECKING,
)
import asyncio

from .exceptions import StreamError

if TYPE_CHECKING:
    from .http11 import HTTP11Connection  # Forward reference


class StreamInterface(ABC):
    """
    Base interface for all streams.
    
    All streams must implement this interface to ensure
    consistent behavior across the library.
    """
    
    @abstractmethod
    def __aiter__(self) -> "StreamInterface":
        """Return self as async iterator."""
        pass
    
    @abstractmethod
    async def __anext__(self) -> bytes:
        """Get next chunk of data."""
        pass
    
    @abstractmethod
    async def aclose(self) -> None:
        """Close the stream and cleanup resources."""
        pass
    
    @abstractmethod
    async def aread(self) -> bytes:
        """Read entire stream and return as bytes."""
        pass


class RequestStream(StreamInterface):
    """
    Stream for HTTP request bodies.
    
    Handles streaming of request body data with proper
    content-length and chunked transfer encoding support.
    """
    
    def __init__(
        self,
        data: Union[bytes, List[bytes], AsyncIterable[bytes]],
        content_length: Optional[int] = None,
        chunked: bool = False,
    ) -> None:
        """
        Initialize RequestStream.
        
        Args:
            data: The data to stream. Can be bytes, list of bytes, or async iterable
            content_length: Optional content length for validation
            chunked: Whether to use chunked transfer encoding
        """
        self._data = data
        self._content_length = content_length
        self._chunked = chunked
        self._closed = False
        self._iterator: Optional[AsyncIterable[bytes]] = None
        
        # Validate content_length if provided
        if content_length is not None and content_length < 0:
            raise ValueError("content_length must be non-negative")
        
        # Calculate actual content length for validation
        self._actual_length = self._calculate_actual_length()
        
        # Validate against provided content_length
        if content_length is not None and self._actual_length != content_length:
            raise ValueError(
                f"Actual content length ({self._actual_length}) "
                f"does not match provided content_length ({content_length})"
            )
    
    def _calculate_actual_length(self) -> int:
        """Calculate the actual content length of the data."""
        if isinstance(self._data, bytes):
            return len(self._data)
        elif isinstance(self._data, list):
            return sum(len(chunk) for chunk in self._data)
        else:
            # For async iterables, we can't calculate length upfront
            return -1
    
    def _get_iterator(self) -> AsyncIterable[bytes]:
        """Get the appropriate iterator for the data."""
        if isinstance(self._data, bytes):
            # Convert single bytes to list for consistent iteration
            return self._iter_bytes(self._data)
        elif isinstance(self._data, list):
            return self._iter_list(self._data)
        else:
            return self._data
    
    def _iter_bytes(self, data: bytes) -> AsyncIterable[bytes]:
        """Iterate over bytes in chunks."""
        async def _iter():
            if data:
                yield data
        return _iter()
    
    def _iter_list(self, data: List[bytes]) -> AsyncIterable[bytes]:
        """Iterate over list of bytes."""
        async def _iter():
            for chunk in data:
                if chunk:  # Skip empty chunks
                    yield chunk
        return _iter()
    
    def __aiter__(self) -> "RequestStream":
        """Return self as async iterator."""
        if self._closed:
            raise StreamError("Cannot iterate over closed stream")
        
        self._iterator = self._get_iterator()
        return self
    
    async def __anext__(self) -> bytes:
        """Get next chunk of data."""
        if self._closed:
            raise StreamError("Cannot read from closed stream")
        
        if self._iterator is None:
            raise RuntimeError("Stream not initialized for iteration")
        
        try:
            # Get the async iterator from the iterator
            if not hasattr(self._iterator, '__aiter__'):
                # If it's not an async iterator, make it one
                self._iterator = self._iterator.__aiter__()
            
            return await self._iterator.__anext__()
        except StopAsyncIteration:
            raise
        except Exception as e:
            raise StreamError(f"Error reading from stream: {e}") from e
    
    async def aread(self) -> bytes:
        """Read entire stream and return as bytes."""
        if self._closed:
            raise StreamError("Cannot read from closed stream")
        
        chunks = []
        async for chunk in self:
            chunks.append(chunk)
        
        return b"".join(chunks)
    
    async def aclose(self) -> None:
        """Close the stream and cleanup resources."""
        self._closed = True
        self._iterator = None
    
    @property
    def content_length(self) -> Optional[int]:
        """Get the content length of the stream."""
        return self._content_length
    
    @property
    def chunked(self) -> bool:
        """Get whether the stream uses chunked transfer encoding."""
        return self._chunked
    
    @property
    def closed(self) -> bool:
        """Get whether the stream is closed."""
        return self._closed


class ResponseStream(StreamInterface):
    """
    Stream for HTTP response bodies.
    
    Handles streaming of response body data with proper
    content-length, chunked transfer encoding, and connection
    state management.
    """
    
    def __init__(
        self,
        connection: "HTTP11Connection",
        content_length: Optional[int] = None,
        chunked: bool = False,
        encoding: Optional[str] = None,
    ) -> None:
        """
        Initialize ResponseStream.
        
        Args:
            connection: The HTTP11Connection that owns this stream
            content_length: Optional content length for validation
            chunked: Whether response uses chunked transfer encoding
            encoding: Optional content encoding (gzip, deflate, etc.)
        """
        self._connection = connection
        self._content_length = content_length
        self._chunked = chunked
        self._encoding = encoding
        self._closed = False
        self._bytes_read = 0
        self._iterator: Optional[AsyncIterable[bytes]] = None
        self._iterator_coro = None
        
        # Validate content_length if provided
        if content_length is not None and content_length < 0:
            raise ValueError("content_length must be non-negative")
    
    async def _get_iterator(self) -> AsyncIterable[bytes]:
        """Get the iterator that reads from the connection."""
        return await self._connection._receive_body_chunk()
    
    def __aiter__(self) -> "ResponseStream":
        """Return self as async iterator."""
        if self._closed:
            raise StreamError("Cannot iterate over closed stream")
        
        # Store the coroutine to await it in __anext__
        self._iterator_coro = self._get_iterator()
        self._iterator = None
        return self
    
    async def __anext__(self) -> bytes:
        """Get next chunk of data."""
        if self._closed:
            raise StreamError("Cannot read from closed stream")
        
        # Initialize iterator on first call
        if self._iterator is None:
            if self._iterator_coro is None:
                raise RuntimeError("Stream not initialized for iteration")
            self._iterator = await self._iterator_coro
            self._iterator_coro = None
        
        try:
            # Handle both regular iterators and async iterators
            if hasattr(self._iterator, '__aiter__'):
                # It's an async iterator
                if not hasattr(self._iterator, '__anext__'):
                    # Get the actual async iterator
                    self._iterator = self._iterator.__aiter__()
                chunk = await self._iterator.__anext__()
            else:
                # It's a regular iterator, convert to async
                try:
                    chunk = next(self._iterator)
                except StopIteration:
                    raise StopAsyncIteration
            
            self._bytes_read += len(chunk)
            
            # Check content_length if provided
            if (self._content_length is not None and 
                self._bytes_read > self._content_length):
                raise StreamError(
                    f"Read more bytes ({self._bytes_read}) than "
                    f"content_length ({self._content_length})"
                )
            
            return chunk
            
        except StopAsyncIteration:
            # Stream ended, notify connection
            await self._connection._response_closed()
            raise
        except Exception as e:
            # Error occurred, close connection
            await self._connection._response_closed()
            raise StreamError(f"Error reading from stream: {e}") from e
    
    async def aread(self) -> bytes:
        """Read entire stream and return as bytes."""
        if self._closed:
            raise StreamError("Cannot read from closed stream")
        
        chunks = []
        async for chunk in self:
            chunks.append(chunk)
        
        return b"".join(chunks)
    
    async def aclose(self) -> None:
        """Close the stream and cleanup resources."""
        if not self._closed:
            self._closed = True
            # Notify connection that we're closing early
            await self._connection._response_closed()
    
    @property
    def content_length(self) -> Optional[int]:
        """Get the content length of the stream."""
        return self._content_length
    
    @property
    def chunked(self) -> bool:
        """Get whether the stream uses chunked transfer encoding."""
        return self._chunked
    
    @property
    def encoding(self) -> Optional[str]:
        """Get the content encoding of the stream."""
        return self._encoding
    
    @property
    def closed(self) -> bool:
        """Get whether the stream is closed."""
        return self._closed
    
    @property
    def bytes_read(self) -> int:
        """Get the number of bytes read so far."""
        return self._bytes_read


# Factory functions for creating streams
def create_request_stream(
    data: Union[bytes, str, List[bytes], AsyncIterable[bytes]],
    content_length: Optional[int] = None,
    chunked: bool = False,
) -> RequestStream:
    """
    Factory function to create RequestStream from various data types.
    
    Args:
        data: The data to stream. Can be bytes, string, list of bytes, or async iterable
        content_length: Optional content length for validation
        chunked: Whether to use chunked transfer encoding
        
    Returns:
        RequestStream instance
    """
    # Convert string to bytes if needed
    if isinstance(data, str):
        data = data.encode('utf-8')
    
    return RequestStream(
        data=data,
        content_length=content_length,
        chunked=chunked,
    )


def create_response_stream(
    connection: "HTTP11Connection",
    content_length: Optional[int] = None,
    chunked: bool = False,
    encoding: Optional[str] = None,
) -> ResponseStream:
    """
    Factory function to create ResponseStream.
    
    Args:
        connection: The HTTP11Connection that owns this stream
        content_length: Optional content length for validation
        chunked: Whether response uses chunked transfer encoding
        encoding: Optional content encoding
        
    Returns:
        ResponseStream instance
    """
    return ResponseStream(
        connection=connection,
        content_length=content_length,
        chunked=chunked,
        encoding=encoding,
    )


# Utility functions for working with streams
async def read_stream_to_bytes(stream: AsyncIterable[bytes]) -> bytes:
    """
    Read entire stream and return as bytes.
    
    Args:
        stream: Async iterable of bytes
        
    Returns:
        All bytes from the stream concatenated
    """
    chunks = []
    async for chunk in stream:
        chunks.append(chunk)
    return b"".join(chunks)


async def stream_to_list(stream: AsyncIterable[bytes]) -> List[bytes]:
    """
    Convert stream to list of chunks.
    
    Args:
        stream: Async iterable of bytes
        
    Returns:
        List of byte chunks
    """
    chunks = []
    async for chunk in stream:
        chunks.append(chunk)
    return chunks


def calculate_content_length(data: Union[bytes, List[bytes]]) -> int:
    """
    Calculate content length for data.
    
    Args:
        data: Bytes or list of bytes
        
    Returns:
        Total length in bytes
    """
    if isinstance(data, bytes):
        return len(data)
    elif isinstance(data, list):
        return sum(len(chunk) for chunk in data)
    else:
        raise ValueError("data must be bytes or list of bytes")


def is_stream_empty(data: Union[bytes, List[bytes], AsyncIterable[bytes]]) -> bool:
    """
    Check if a stream is empty.
    
    Args:
        data: The data to check
        
    Returns:
        True if empty, False otherwise
    """
    if isinstance(data, bytes):
        return len(data) == 0
    elif isinstance(data, list):
        return all(len(chunk) == 0 for chunk in data)
    else:
        # For async iterables, we can't determine emptiness without iteration
        return False 