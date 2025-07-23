"""
Network backend components for c_http_core.

This module provides the low-level networking abstractions
including the event loop and network streams.
"""

from .backend import NetworkBackend
from .stream import NetworkStream
from .mock import MockNetworkBackend, MockNetworkStream
from .utils import (
    create_socket,
    create_ssl_context,
    parse_url,
    format_host_header,
    is_ipv6_address,
    is_ipv4_address,
    get_address_family,
    create_connection_socket,
    get_socket_error,
    set_socket_timeout,
    get_socket_info,
    validate_port,
    normalize_host,
    is_localhost,
)

# Try to import epoll implementation
try:
    from .epoll import EpollEventLoop, EpollNetworkStream, EpollNetworkBackend
    HAS_EPOLL = True
except ImportError:
    HAS_EPOLL = False

__all__ = [
    "NetworkBackend", 
    "NetworkStream",
    "MockNetworkBackend", 
    "MockNetworkStream",
    "create_socket",
    "create_ssl_context",
    "parse_url",
    "format_host_header",
    "is_ipv6_address",
    "is_ipv4_address",
    "get_address_family",
    "create_connection_socket",
    "get_socket_error",
    "set_socket_timeout",
    "get_socket_info",
    "validate_port",
    "normalize_host",
    "is_localhost",
]

if HAS_EPOLL:
    __all__.extend([
        "EpollEventLoop", 
        "EpollNetworkStream", 
        "EpollNetworkBackend"
    ]) 