"""
HTTP/1.1 connection pool implementation.

This module provides a connection pool for managing multiple HTTP/1.1
connections efficiently, with automatic cleanup and load balancing.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

from .http11 import HTTP11Connection, ConnectionState
from .network import NetworkBackend
from .exceptions import ConnectionError

logger = logging.getLogger(__name__)


class ConnectionPool:
    """
    HTTP/1.1 connection pool.
    
    This class manages a pool of HTTP/1.1 connections, providing
    efficient connection reuse and automatic cleanup.
    """
    
    def __init__(
        self,
        backend: NetworkBackend,
        max_connections: int = 10,
        max_connections_per_host: int = 5,
        keep_alive_timeout: float = 300.0,
        max_requests_per_connection: int = 100,
        cleanup_interval: float = 60.0,
    ):
        """
        Initialize connection pool.
        
        Args:
            backend: Network backend to use for connections
            max_connections: Maximum total connections in pool
            max_connections_per_host: Maximum connections per host
            keep_alive_timeout: Keep-alive timeout in seconds
            max_requests_per_connection: Max requests per connection
            cleanup_interval: Cleanup interval in seconds
        """
        self._backend = backend
        self._max_connections = max_connections
        self._max_connections_per_host = max_connections_per_host
        self._keep_alive_timeout = keep_alive_timeout
        self._max_requests_per_connection = max_requests_per_connection
        self._cleanup_interval = cleanup_interval
        
        # Connection storage: {host:port -> [connections]}
        self._connections: Dict[str, List[HTTP11Connection]] = defaultdict(list)
        self._lock = asyncio.Lock()
        
        # Metrics
        self._total_connections_created = 0
        self._total_connections_closed = 0
        self._total_requests_handled = 0
        
        # Cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._closed = False
        
        logger.debug(f"Connection pool initialized: max={max_connections}, per_host={max_connections_per_host}")
    
    async def start(self) -> None:
        """Start the connection pool and cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.debug("Connection pool cleanup task started")
    
    async def stop(self) -> None:
        """Stop the connection pool and cleanup all connections."""
        self._closed = True
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Close all connections
        async with self._lock:
            for host_connections in self._connections.values():
                for connection in host_connections:
                    try:
                        await connection.close()
                        self._total_connections_closed += 1
                    except Exception as e:
                        logger.warning(f"Error closing connection: {e}")
            
            self._connections.clear()
        
        logger.debug(f"Connection pool stopped. Closed {self._total_connections_closed} connections")
    
    async def get_connection(self, host: str, port: int) -> HTTP11Connection:
        """
        Get a connection for the specified host and port.
        
        Args:
            host: Target host
            port: Target port
            
        Returns:
            An HTTP/1.1 connection
            
        Raises:
            ConnectionError: If no connection is available
        """
        if self._closed:
            raise ConnectionError("Connection pool is closed")
        
        host_key = f"{host}:{port}"
        
        async with self._lock:
            # Try to find an available connection
            connections = self._connections[host_key]
            
            # Remove expired connections
            connections[:] = [
                conn for conn in connections 
                if not conn.has_expired(self._keep_alive_timeout)
            ]
            
            # Find an idle connection
            for connection in connections:
                if connection.is_idle:
                    logger.debug(f"Reusing connection to {host_key}")
                    return connection
            
            # Check if we can create a new connection
            if len(connections) >= self._max_connections_per_host:
                raise ConnectionError(
                    f"Maximum connections per host reached for {host_key}"
                )
            
            if self._get_total_connections() >= self._max_connections:
                # Try to close expired connections from other hosts
                await self._cleanup_expired_connections()
                
                if self._get_total_connections() >= self._max_connections:
                    raise ConnectionError("Maximum total connections reached")
            
            # Create new connection
            try:
                stream = await self._backend.connect_tcp(host, port)
                connection = HTTP11Connection(
                    stream=stream,
                    keep_alive_timeout=self._keep_alive_timeout,
                    max_requests=self._max_requests_per_connection,
                )
                
                connections.append(connection)
                self._total_connections_created += 1
                
                logger.debug(f"Created new connection to {host_key}")
                return connection
                
            except Exception as e:
                logger.error(f"Failed to create connection to {host_key}: {e}")
                raise ConnectionError(f"Failed to create connection: {e}")
    
    async def return_connection(self, connection: HTTP11Connection, host: str, port: int) -> None:
        """
        Return a connection to the pool.
        
        Args:
            connection: The connection to return
            host: Host the connection was used for
            port: Port the connection was used for
        """
        if self._closed:
            return
        
        host_key = f"{host}:{port}"
        
        async with self._lock:
            connections = self._connections[host_key]
            
            # Remove connection if it's closed or can't be reused
            if connection.is_closed or not connection.is_idle:
                if connection in connections:
                    connections.remove(connection)
                self._total_connections_closed += 1
                logger.debug(f"Removed closed connection to {host_key}")
            else:
                # Connection is still good, keep it in pool
                logger.debug(f"Returned connection to pool for {host_key}")
    
    def _get_total_connections(self) -> int:
        """Get total number of connections in pool."""
        return sum(len(connections) for connections in self._connections.values())
    
    async def _cleanup_expired_connections(self) -> None:
        """Clean up expired connections from all hosts."""
        for host_key, connections in self._connections.items():
            # Remove expired connections
            expired = [
                conn for conn in connections 
                if conn.has_expired(self._keep_alive_timeout)
            ]
            
            for connection in expired:
                connections.remove(connection)
                try:
                    await connection.close()
                    self._total_connections_closed += 1
                except Exception as e:
                    logger.warning(f"Error closing expired connection: {e}")
            
            if expired:
                logger.debug(f"Cleaned up {len(expired)} expired connections for {host_key}")
    
    async def _cleanup_loop(self) -> None:
        """Background cleanup loop."""
        while not self._closed:
            try:
                await asyncio.sleep(self._cleanup_interval)
                
                if not self._closed:
                    async with self._lock:
                        await self._cleanup_expired_connections()
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
    
    @property
    def metrics(self) -> Dict[str, Any]:
        """
        Get pool metrics.
        
        Returns:
            Dictionary with pool metrics
        """
        total_connections = self._get_total_connections()
        
        return {
            "total_connections": total_connections,
            "total_connections_created": self._total_connections_created,
            "total_connections_closed": self._total_connections_closed,
            "total_requests_handled": self._total_requests_handled,
            "connections_per_host": {
                host: len(connections) 
                for host, connections in self._connections.items()
            },
            "max_connections": self._max_connections,
            "max_connections_per_host": self._max_connections_per_host,
            "keep_alive_timeout": self._keep_alive_timeout,
            "cleanup_interval": self._cleanup_interval,
        }
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()


class PooledHTTPClient:
    """
    HTTP client that uses a connection pool.
    
    This class provides a high-level interface for making HTTP requests
    using a connection pool for efficient connection reuse.
    """
    
    def __init__(
        self,
        backend: NetworkBackend,
        max_connections: int = 10,
        max_connections_per_host: int = 5,
        keep_alive_timeout: float = 300.0,
        max_requests_per_connection: int = 100,
    ):
        """
        Initialize pooled HTTP client.
        
        Args:
            backend: Network backend to use
            max_connections: Maximum total connections
            max_connections_per_host: Maximum connections per host
            keep_alive_timeout: Keep-alive timeout in seconds
            max_requests_per_connection: Max requests per connection
        """
        self._pool = ConnectionPool(
            backend=backend,
            max_connections=max_connections,
            max_connections_per_host=max_connections_per_host,
            keep_alive_timeout=keep_alive_timeout,
            max_requests_per_connection=max_requests_per_connection,
        )
        self._started = False
    
    async def start(self) -> None:
        """Start the client and connection pool."""
        if not self._started:
            await self._pool.start()
            self._started = True
    
    async def stop(self) -> None:
        """Stop the client and connection pool."""
        if self._started:
            await self._pool.stop()
            self._started = False
    
    async def request(self, request) -> "Response":
        """
        Make an HTTP request using the connection pool.
        
        Args:
            request: The HTTP request to make
            
        Returns:
            The HTTP response
        """
        if not self._started:
            await self.start()
        
        # Extract host and port from request URL
        from urllib.parse import urlparse
        parsed = urlparse(request.url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        
        connection = None
        try:
            # Get connection from pool
            connection = await self._pool.get_connection(host, port)
            
            # Make request
            response = await connection.handle_request(request)
            self._pool._total_requests_handled += 1
            
            return response
            
        finally:
            # Return connection to pool
            if connection:
                await self._pool.return_connection(connection, host, port)
    
    @property
    def metrics(self) -> Dict[str, Any]:
        """Get client metrics."""
        return self._pool.metrics
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop() 