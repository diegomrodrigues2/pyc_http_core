# cython: language_level=3
# distutils: language=c

"""
High-performance event loop implementation using epoll.

This module provides a Cython-based event loop implementation that uses
the Linux epoll system call for efficient I/O multiplexing.
"""

import asyncio
import socket
import ssl
import os
from typing import Optional, Dict, Set, Callable, Any, List
from cpython cimport PyObject
from libc.stdlib cimport malloc, free
from libc.string cimport memcpy
from libc.errno cimport errno, EINTR, EAGAIN, EWOULDBLOCK

# epoll constants
cdef extern from "sys/epoll.h":
    cdef int EPOLLIN
    cdef int EPOLLOUT
    cdef int EPOLLERR
    cdef int EPOLLHUP
    cdef int EPOLLET
    cdef int EPOLLONESHOT
    cdef int EPOLL_CTL_ADD
    cdef int EPOLL_CTL_MOD
    cdef int EPOLL_CTL_DEL
    
    cdef int epoll_create(int size)
    cdef int epoll_ctl(int epfd, int op, int fd, void* event)
    cdef int epoll_wait(int epfd, void* events, int maxevents, int timeout)
    
    ctypedef struct epoll_event:
        unsigned int events
        void* data

# Socket constants
cdef extern from "sys/socket.h":
    cdef int MSG_NOSIGNAL

# Error handling
cdef extern from "errno.h":
    cdef int errno

# Type definitions
ctypedef struct CallbackInfo:
    int fd
    object callback
    bint is_reader
    bint is_writer

cdef class EpollEventLoop:
    """
    High-performance event loop using epoll.
    
    This class provides an efficient event loop implementation that uses
    the Linux epoll system call for I/O multiplexing.
    """
    
    cdef int epoll_fd
    cdef dict callbacks
    cdef set active_fds
    cdef bint running
    cdef object loop
    cdef dict fd_to_callback
    
    def __init__(self):
        """Initialize the epoll event loop."""
        self.epoll_fd = epoll_create(1024)
        if self.epoll_fd == -1:
            raise OSError(f"Failed to create epoll instance: {os.strerror(errno)}")
        
        self.callbacks = {}
        self.active_fds = set()
        self.running = False
        self.loop = asyncio.get_event_loop()
        self.fd_to_callback = {}
    
    def __dealloc__(self):
        """Cleanup epoll file descriptor."""
        if self.epoll_fd != -1:
            os.close(self.epoll_fd)
    
    def add_reader(self, int fd, callback: Callable):
        """
        Add a file descriptor for reading.
        
        Args:
            fd: File descriptor to monitor for read events
            callback: Async callback function to call when data is available
        """
        cdef epoll_event event
        event.events = EPOLLIN | EPOLLET
        event.data = <void*>fd
        
        if epoll_ctl(self.epoll_fd, EPOLL_CTL_ADD, fd, &event) == -1:
            if errno != 17:  # File exists
                raise OSError(f"Failed to add reader for fd {fd}: {os.strerror(errno)}")
        
        self.callbacks[fd] = callback
        self.active_fds.add(fd)
        self.fd_to_callback[fd] = {"type": "reader", "callback": callback}
    
    def add_writer(self, int fd, callback: Callable):
        """
        Add a file descriptor for writing.
        
        Args:
            fd: File descriptor to monitor for write events
            callback: Async callback function to call when write is possible
        """
        cdef epoll_event event
        event.events = EPOLLOUT | EPOLLET
        event.data = <void*>fd
        
        if epoll_ctl(self.epoll_fd, EPOLL_CTL_ADD, fd, &event) == -1:
            if errno != 17:  # File exists
                raise OSError(f"Failed to add writer for fd {fd}: {os.strerror(errno)}")
        
        self.callbacks[fd] = callback
        self.active_fds.add(fd)
        self.fd_to_callback[fd] = {"type": "writer", "callback": callback}
    
    def remove_reader(self, int fd):
        """
        Remove a file descriptor from reading.
        
        Args:
            fd: File descriptor to remove
        """
        if epoll_ctl(self.epoll_fd, EPOLL_CTL_DEL, fd, NULL) == -1:
            if errno != 2:  # No such file or directory
                raise OSError(f"Failed to remove reader for fd {fd}: {os.strerror(errno)}")
        
        self.callbacks.pop(fd, None)
        self.active_fds.discard(fd)
        self.fd_to_callback.pop(fd, None)
    
    def remove_writer(self, int fd):
        """
        Remove a file descriptor from writing.
        
        Args:
            fd: File descriptor to remove
        """
        if epoll_ctl(self.epoll_fd, EPOLL_CTL_DEL, fd, NULL) == -1:
            if errno != 2:  # No such file or directory
                raise OSError(f"Failed to remove writer for fd {fd}: {os.strerror(errno)}")
        
        self.callbacks.pop(fd, None)
        self.active_fds.discard(fd)
        self.fd_to_callback.pop(fd, None)
    
    def modify_events(self, int fd, bint read_events, bint write_events):
        """
        Modify events for a file descriptor.
        
        Args:
            fd: File descriptor to modify
            read_events: Whether to monitor for read events
            write_events: Whether to monitor for write events
        """
        cdef epoll_event event
        event.events = 0
        
        if read_events:
            event.events |= EPOLLIN
        if write_events:
            event.events |= EPOLLOUT
        
        if event.events == 0:
            self.remove_reader(fd)
            self.remove_writer(fd)
        else:
            event.data = <void*>fd
            if epoll_ctl(self.epoll_fd, EPOLL_CTL_MOD, fd, &event) == -1:
                raise OSError(f"Failed to modify events for fd {fd}: {os.strerror(errno)}")
    
    async def run_forever(self):
        """
        Run the event loop indefinitely.
        
        This method processes epoll events and calls the appropriate
        callbacks for each event.
        """
        self.running = True
        
        cdef epoll_event events[1024]
        cdef int n_events, i, fd
        cdef unsigned int event_flags
        
        while self.running:
            n_events = epoll_wait(self.epoll_fd, events, 1024, -1)
            
            if n_events == -1:
                if errno == EINTR:
                    continue
                raise OSError(f"epoll_wait failed: {os.strerror(errno)}")
            
            for i in range(n_events):
                fd = <int>events[i].data
                event_flags = events[i].events
                
                if fd in self.fd_to_callback:
                    callback_info = self.fd_to_callback[fd]
                    callback = callback_info["callback"]
                    
                    try:
                        # Check for error conditions
                        if event_flags & EPOLLERR or event_flags & EPOLLHUP:
                            # Handle error condition
                            await self._handle_error(fd, callback_info)
                        else:
                            # Handle normal events
                            await callback()
                    except Exception as e:
                        # Log error and continue
                        print(f"Error in callback for fd {fd}: {e}")
                        await self._handle_error(fd, callback_info)
    
    async def _handle_error(self, int fd, dict callback_info):
        """
        Handle error conditions for a file descriptor.
        
        Args:
            fd: File descriptor with error
            callback_info: Information about the callback
        """
        try:
            # Remove the file descriptor from monitoring
            if callback_info["type"] == "reader":
                self.remove_reader(fd)
            else:
                self.remove_writer(fd)
        except Exception as e:
            print(f"Error handling error for fd {fd}: {e}")
    
    def stop(self):
        """Stop the event loop."""
        self.running = False
    
    @property
    def is_running(self) -> bool:
        """Check if the event loop is running."""
        return self.running
    
    @property
    def active_file_descriptors(self) -> Set[int]:
        """Get the set of active file descriptors."""
        return self.active_fds.copy()


cdef class EpollNetworkStream:
    """
    Network stream implementation using epoll.
    
    This class provides a high-performance network stream that uses
    the epoll event loop for non-blocking I/O operations.
    """
    
    cdef int sock_fd
    cdef EpollEventLoop loop
    cdef bint closed
    cdef bytes buffer
    cdef int buffer_pos
    cdef object read_future
    cdef object write_future
    
    def __init__(self, int sock_fd, EpollEventLoop loop):
        """
        Initialize the epoll network stream.
        
        Args:
            sock_fd: Socket file descriptor
            loop: EpollEventLoop instance
        """
        self.sock_fd = sock_fd
        self.loop = loop
        self.closed = False
        self.buffer = b""
        self.buffer_pos = 0
        self.read_future = None
        self.write_future = None
    
    async def read(self, max_bytes: Optional[int] = None) -> bytes:
        """
        Read data from the stream.
        
        Args:
            max_bytes: Maximum number of bytes to read
        
        Returns:
            The data read from the stream
        
        Raises:
            RuntimeError: If the stream is closed
            OSError: If a network error occurs
        """
        if self.closed:
            raise RuntimeError("Stream is closed")
        
        if max_bytes is None:
            max_bytes = 8192  # Default chunk size
        
        cdef bytes data = b""
        cdef int bytes_read
        
        while len(data) < max_bytes:
            try:
                bytes_read = socket.recv(self.sock_fd, max_bytes - len(data))
                if bytes_read == 0:
                    # Connection closed by peer
                    break
                data += bytes_read
            except BlockingIOError:
                # No data available, wait for more
                await self._wait_for_read()
            except OSError as e:
                raise OSError(f"Failed to read from socket: {e}")
        
        return data
    
    async def write(self, data: bytes) -> None:
        """
        Write data to the stream.
        
        Args:
            data: The data to write
        
        Raises:
            RuntimeError: If the stream is closed
            OSError: If a network error occurs
        """
        if self.closed:
            raise RuntimeError("Stream is closed")
        
        cdef int total_sent = 0
        cdef int bytes_sent
        
        while total_sent < len(data):
            try:
                bytes_sent = socket.send(
                    self.sock_fd, 
                    data[total_sent:],
                    MSG_NOSIGNAL
                )
                if bytes_sent == -1:
                    raise OSError("Failed to send data")
                total_sent += bytes_sent
            except BlockingIOError:
                # Socket buffer full, wait for write availability
                await self._wait_for_write()
            except OSError as e:
                raise OSError(f"Failed to write to socket: {e}")
    
    async def _wait_for_read(self):
        """Wait for data to be available for reading."""
        if self.read_future is None:
            self.read_future = asyncio.Future()
            self.loop.add_reader(self.sock_fd, self._read_ready)
        
        await self.read_future
        self.read_future = None
    
    async def _wait_for_write(self):
        """Wait for write availability."""
        if self.write_future is None:
            self.write_future = asyncio.Future()
            self.loop.add_writer(self.sock_fd, self._write_ready)
        
        await self.write_future
        self.write_future = None
    
    def _read_ready(self):
        """Called when data is available for reading."""
        if self.read_future and not self.read_future.done():
            self.read_future.set_result(None)
    
    def _write_ready(self):
        """Called when write is possible."""
        if self.write_future and not self.write_future.done():
            self.write_future.set_result(None)
    
    async def aclose(self) -> None:
        """Close the stream and cleanup resources."""
        if not self.closed:
            # Remove from event loop
            try:
                self.loop.remove_reader(self.sock_fd)
                self.loop.remove_writer(self.sock_fd)
            except:
                pass
            
            # Close socket
            socket.close(self.sock_fd)
            self.closed = True
    
    def get_extra_info(self, name: str) -> Optional[Any]:
        """
        Get extra information about the stream.
        
        Args:
            name: The name of the information to retrieve
        
        Returns:
            The requested information or None if not available
        """
        if name == "socket":
            return self.sock_fd
        elif name == "peername":
            try:
                return socket.getpeername(self.sock_fd)
            except:
                return None
        elif name == "sockname":
            try:
                return socket.getsockname(self.sock_fd)
            except:
                return None
        return None
    
    @property
    def is_closed(self) -> bool:
        """Check if the stream is closed."""
        return self.closed


cdef class EpollNetworkBackend:
    """
    Network backend implementation using epoll.
    
    This class provides a high-performance network backend that uses
    the epoll event loop for efficient I/O operations.
    """
    
    cdef EpollEventLoop loop
    
    def __init__(self):
        """Initialize the epoll network backend."""
        self.loop = EpollEventLoop()
    
    async def connect_tcp(
        self, 
        host: str, 
        port: int, 
        timeout: Optional[float] = None
    ) -> EpollNetworkStream:
        """
        Connect to a TCP endpoint.
        
        Args:
            host: The hostname or IP address to connect to
            port: The port number to connect to
            timeout: Optional timeout in seconds for the connection
        
        Returns:
            An EpollNetworkStream representing the TCP connection
        
        Raises:
            OSError: If the connection fails
            TimeoutError: If the connection times out
        """
        cdef int sock_fd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # Set non-blocking
        socket.setblocking(sock_fd, False)
        
        # Connect
        try:
            socket.connect(sock_fd, (host, port))
        except BlockingIOError:
            # Connection in progress, wait for completion
            await self._wait_for_connection(sock_fd, timeout)
        except OSError as e:
            socket.close(sock_fd)
            raise OSError(f"Failed to connect to {host}:{port}: {e}")
        
        return EpollNetworkStream(sock_fd, self.loop)
    
    async def _wait_for_connection(self, int sock_fd, timeout: Optional[float]):
        """
        Wait for a non-blocking connection to complete.
        
        Args:
            sock_fd: Socket file descriptor
            timeout: Optional timeout in seconds
        
        Raises:
            TimeoutError: If the connection times out
            OSError: If the connection fails
        """
        future = asyncio.Future()
        
        def connection_ready():
            try:
                # Check if connection is complete
                socket.getpeername(sock_fd)
                if not future.done():
                    future.set_result(None)
            except:
                # Connection not ready yet
                pass
        
        self.loop.add_writer(sock_fd, connection_ready)
        
        try:
            if timeout is not None:
                await asyncio.wait_for(future, timeout)
            else:
                await future
        except asyncio.TimeoutError:
            socket.close(sock_fd)
            raise TimeoutError(f"Connection to socket timed out")
        finally:
            self.loop.remove_writer(sock_fd)
    
    async def connect_tls(
        self,
        stream: EpollNetworkStream,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        alpn_protocols: Optional[List[str]] = None,
    ) -> EpollNetworkStream:
        """
        Upgrade a TCP stream to TLS.
        
        Args:
            stream: The existing TCP EpollNetworkStream to upgrade
            host: The hostname for TLS certificate verification
            port: The port number (used for logging/debugging)
            timeout: Optional timeout in seconds for the TLS handshake
            alpn_protocols: Optional list of ALPN protocols to negotiate
        
        Returns:
            An EpollNetworkStream representing the TLS connection
        
        Raises:
            OSError: If the TLS handshake fails
            TimeoutError: If the TLS handshake times out
        """
        # Create SSL context
        context = ssl.create_default_context()
        if alpn_protocols:
            context.set_alpn_protocols(alpn_protocols)
        
        # Wrap socket with SSL
        ssl_sock = context.wrap_socket(
            socket.socket(fileno=stream.sock_fd),
            server_hostname=host
        )
        
        # Create new stream with SSL socket
        return EpollNetworkStream(ssl_sock.fileno(), self.loop)
    
    async def start_tls(
        self,
        stream: EpollNetworkStream,
        host: str,
        alpn_protocols: Optional[List[str]] = None,
    ) -> EpollNetworkStream:
        """
        Start TLS on an existing stream.
        
        Args:
            stream: The existing stream to upgrade
            host: The hostname for TLS certificate verification
            alpn_protocols: Optional list of ALPN protocols to negotiate
        
        Returns:
            An EpollNetworkStream representing the TLS connection
        
        Raises:
            OSError: If the TLS handshake fails
        """
        # Similar to connect_tls but for existing connection
        context = ssl.create_default_context()
        if alpn_protocols:
            context.set_alpn_protocols(alpn_protocols)
        
        ssl_sock = context.wrap_socket(
            socket.socket(fileno=stream.sock_fd),
            server_hostname=host,
            do_handshake_on_connect=False
        )
        
        return EpollNetworkStream(ssl_sock.fileno(), self.loop)
    
    def get_event_loop(self) -> EpollEventLoop:
        """Get the underlying event loop."""
        return self.loop 