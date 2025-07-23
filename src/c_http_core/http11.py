"""
HTTP/1.1 connection implementation for c_http_core.

This module implements the HTTP11Connection class that manages
HTTP/1.1 protocol communication over a NetworkStream.
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any
from enum import Enum

import h11

from .http_primitives import Request, Response
from .streams import ResponseStream
from .network.stream import NetworkStream
from .exceptions import (
    HTTPCoreError,
    ConnectionError,
    ProtocolError,
    StreamError,
)

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """States of an HTTP/1.1 connection."""
    NEW = "new"           # Connection created, not yet used
    ACTIVE = "active"     # Connection handling a request
    IDLE = "idle"         # Connection available for reuse
    CLOSED = "closed"     # Connection closed, cannot be reused


class HTTP11Connection:
    """
    HTTP/1.1 connection manager.
    
    This class manages a single HTTP/1.1 connection over a NetworkStream,
    handling request/response cycles with proper state management and
    keep-alive support.
    """
    
    # Default configuration
    DEFAULT_READ_TIMEOUT = 30.0  # 30 seconds
    DEFAULT_WRITE_TIMEOUT = 30.0  # 30 seconds
    DEFAULT_KEEP_ALIVE_TIMEOUT = 300.0  # 5 minutes
    DEFAULT_MAX_REQUESTS = 100  # Maximum requests per connection
    
    def __init__(
        self, 
        stream: NetworkStream,
        read_timeout: Optional[float] = None,
        write_timeout: Optional[float] = None,
        keep_alive_timeout: Optional[float] = None,
        max_requests: Optional[int] = None,
    ):
        """
        Initialize HTTP/1.1 connection.
        
        Args:
            stream: The NetworkStream to use for communication
            read_timeout: Timeout for read operations in seconds
            write_timeout: Timeout for write operations in seconds
            keep_alive_timeout: Timeout for keep-alive connections in seconds
            max_requests: Maximum number of requests per connection
        """
        self._stream = stream
        self._h11_connection = h11.Connection(h11.CLIENT)
        self._state = ConnectionState.NEW
        self._state_lock = asyncio.Lock()
        self._idle_since: Optional[float] = None
        
        # Configuration
        self._read_timeout = read_timeout or self.DEFAULT_READ_TIMEOUT
        self._write_timeout = write_timeout or self.DEFAULT_WRITE_TIMEOUT
        self._keep_alive_timeout = keep_alive_timeout or self.DEFAULT_KEEP_ALIVE_TIMEOUT
        self._max_requests = max_requests or self.DEFAULT_MAX_REQUESTS
        
        # Metrics
        self._request_count = 0
        self._bytes_sent = 0
        self._bytes_received = 0
        self._total_request_time = 0.0
        self._errors_count = 0
        self._last_request_time: Optional[float] = None
        
        logger.debug("HTTP/1.1 connection initialized")
    
    async def handle_request(
        self, 
        request: Request, 
        timeout: Optional[float] = None
    ) -> Response:
        """
        Handle a complete HTTP request/response cycle.
        
        Args:
            request: The HTTP request to send
            timeout: Optional timeout override for this request
            
        Returns:
            The HTTP response received
            
        Raises:
            ConnectionError: If connection is not available
            ProtocolError: If HTTP protocol error occurs
            asyncio.TimeoutError: If request times out
        """
        start_time = time.time()
        self._request_count += 1
        self._last_request_time = start_time
        
        # Check if connection has exceeded max requests
        if self._request_count > self._max_requests:
            await self.close()
            raise ConnectionError(f"Connection exceeded max requests ({self._max_requests})")
        
        try:
            # Acquire connection
            await self._acquire_connection()
            
            # Send request
            await self._send_request(request, timeout)
            
            # Receive response
            response = await self._receive_response(timeout)
            
            duration = time.time() - start_time
            self._total_request_time += duration
            
            logger.debug(
                f"Request {self._request_count}: {request.method} {request.path} "
                f"-> {response.status_code} ({duration:.3f}s)"
            )
            
            return response
            
        except asyncio.TimeoutError:
            duration = time.time() - start_time
            self._errors_count += 1
            logger.error(
                f"Request {self._request_count} timed out after {duration:.3f}s"
            )
            # Mark connection as closed on timeout
            async with self._state_lock:
                self._state = ConnectionState.CLOSED
            await self._stream.aclose()
            raise
            
        except Exception as e:
            duration = time.time() - start_time
            self._errors_count += 1
            logger.error(
                f"Request {self._request_count} failed: {e} ({duration:.3f}s)"
            )
            # Mark connection as closed on any error
            async with self._state_lock:
                self._state = ConnectionState.CLOSED
            await self._stream.aclose()
            raise
    
    async def _send_request(self, request: Request, timeout: Optional[float] = None) -> None:
        """
        Send HTTP request using h11.
        
        Args:
            request: The request to send
            timeout: Optional timeout override
        """
        write_timeout = timeout or self._write_timeout
        
        # Create h11 Request event
        h11_request = h11.Request(
            method=request.method,
            target=request.path,
            headers=request.headers
        )
        
        # Send request headers
        await asyncio.wait_for(
            self._send_event(h11_request),
            timeout=write_timeout
        )
        
        # Send request body if present
        if request.stream:
            async for chunk in request.stream:
                h11_data = h11.Data(data=chunk)
                await asyncio.wait_for(
                    self._send_event(h11_data),
                    timeout=write_timeout
                )
        
        # Send end of message
        await asyncio.wait_for(
            self._send_event(h11.EndOfMessage()),
            timeout=write_timeout
        )
    
    async def _send_event(self, event: h11.Event) -> None:
        """
        Send an h11 event to the network stream.
        
        Args:
            event: The h11 event to send
        """
        data = self._h11_connection.send(event)
        if data:
            await self._stream.write(data)
            self._bytes_sent += len(data)
    
    async def _receive_response(self, timeout: Optional[float] = None) -> Response:
        """
        Receive HTTP response using h11.
        
        Args:
            timeout: Optional timeout override
            
        Returns:
            The HTTP response with streaming body
        """
        read_timeout = timeout or self._read_timeout
        
        # Read response headers
        while True:
            event = self._h11_connection.next_event()
            
            if event is h11.NEED_DATA:
                data = await asyncio.wait_for(
                    self._stream.read(65536),  # 64KB chunks
                    timeout=read_timeout
                )
                if not data:
                    raise ProtocolError("Connection closed unexpectedly")
                self._h11_connection.receive_data(data)
                self._bytes_received += len(data)
                continue
                
            if isinstance(event, h11.Response):
                # Create response with streaming body
                response_stream = ResponseStream(
                    connection=self,
                    content_length=self._get_content_length(event.headers),
                    chunked=self._is_chunked(event.headers)
                )
                
                return Response.create(
                    status_code=event.status_code,
                    headers=event.headers,
                    stream=response_stream
                )
                
            if isinstance(event, h11.ConnectionClosed):
                raise ProtocolError("Connection closed by server")
    
    async def _receive_body_chunk(self, timeout: Optional[float] = None) -> Optional[bytes]:
        """
        Receive a chunk of response body.
        
        Args:
            timeout: Optional timeout override
            
        Returns:
            Chunk of data or None if end of body
        """
        read_timeout = timeout or self._read_timeout
        
        while True:
            event = self._h11_connection.next_event()
            
            if event is h11.NEED_DATA:
                data = await asyncio.wait_for(
                    self._stream.read(65536),
                    timeout=read_timeout
                )
                if not data:
                    raise ProtocolError("Connection closed unexpectedly")
                self._h11_connection.receive_data(data)
                self._bytes_received += len(data)
                continue
                
            if isinstance(event, h11.Data):
                return event.data
                
            if isinstance(event, h11.EndOfMessage):
                return None
                
            if isinstance(event, h11.ConnectionClosed):
                raise ProtocolError("Connection closed by server")
    
    def _get_content_length(self, headers: list) -> Optional[int]:
        """
        Extract Content-Length from headers.
        
        Args:
            headers: List of (name, value) header tuples
            
        Returns:
            Content-Length value or None if not present
        """
        for name, value in headers:
            if name.lower() == b"content-length":
                try:
                    return int(value)
                except ValueError:
                    return None
        return None
    
    def _is_chunked(self, headers: list) -> bool:
        """
        Check if response uses chunked transfer encoding.
        
        Args:
            headers: List of (name, value) header tuples
            
        Returns:
            True if chunked transfer encoding is used
        """
        for name, value in headers:
            if name.lower() == b"transfer-encoding" and value.lower() == b"chunked":
                return True
        return False
    
    async def _acquire_connection(self) -> None:
        """
        Acquire connection for use.
        
        Raises:
            ConnectionError: If connection is not available
        """
        async with self._state_lock:
            if self._state == ConnectionState.CLOSED:
                raise ConnectionError("Connection is closed")
            
            if self._state == ConnectionState.ACTIVE:
                raise ConnectionError("Connection is busy")
            
            self._state = ConnectionState.ACTIVE
    
    async def _release_connection(self) -> None:
        """
        Release connection after use.
        """
        async with self._state_lock:
            if self._state == ConnectionState.ACTIVE:
                # Check if connection can be reused
                if self._can_reuse_connection():
                    self._state = ConnectionState.IDLE
                    self._idle_since = asyncio.get_event_loop().time()
                    self._h11_connection.start_next_cycle()
                else:
                    self._state = ConnectionState.CLOSED
                    await self._stream.aclose()
    
    def _can_reuse_connection(self) -> bool:
        """
        Check if connection can be reused for keep-alive.
        
        Returns:
            True if connection can be reused
        """
        # Check h11 connection state
        if self._h11_connection.their_state != h11.DONE:
            return False
        
        # Check if server indicated connection close
        if hasattr(self._h11_connection, 'they_closed'):
            return not self._h11_connection.they_closed
        
        return True
    
    async def _response_closed(self) -> None:
        """
        Called when response body is fully consumed.
        """
        await self._release_connection()
    
    async def close(self) -> None:
        """
        Close the connection and cleanup resources.
        """
        async with self._state_lock:
            if self._state != ConnectionState.CLOSED:
                self._state = ConnectionState.CLOSED
                await self._stream.aclose()
        
        logger.debug(f"Connection closed after {self._request_count} requests")
    
    @property
    def is_closed(self) -> bool:
        """Check if connection is closed."""
        return self._state == ConnectionState.CLOSED
    
    @property
    def is_idle(self) -> bool:
        """Check if connection is idle and available for reuse."""
        return self._state == ConnectionState.IDLE
    
    def has_expired(self, timeout: Optional[float] = None) -> bool:
        """
        Check if idle connection has expired.
        
        Args:
            timeout: Idle timeout in seconds (uses keep_alive_timeout if None)
            
        Returns:
            True if connection has expired
        """
        if self._state != ConnectionState.IDLE or self._idle_since is None:
            return False
        
        check_timeout = timeout or self._keep_alive_timeout
        return (asyncio.get_event_loop().time() - self._idle_since) > check_timeout
    
    @property
    def metrics(self) -> Dict[str, Any]:
        """
        Get connection metrics.
        
        Returns:
            Dictionary with connection metrics
        """
        return {
            "request_count": self._request_count,
            "bytes_sent": self._bytes_sent,
            "bytes_received": self._bytes_received,
            "total_request_time": self._total_request_time,
            "errors_count": self._errors_count,
            "last_request_time": self._last_request_time,
            "average_request_time": (
                self._total_request_time / self._request_count 
                if self._request_count > 0 else 0.0
            ),
            "error_rate": (
                self._errors_count / self._request_count 
                if self._request_count > 0 else 0.0
            ),
            "state": self._state.value,
            "idle_since": self._idle_since,
        }
    
    def reset_metrics(self) -> None:
        """Reset connection metrics."""
        self._request_count = 0
        self._bytes_sent = 0
        self._bytes_received = 0
        self._total_request_time = 0.0
        self._errors_count = 0
        self._last_request_time = None 