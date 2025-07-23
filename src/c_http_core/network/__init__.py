"""
Network backend components for c_http_core.

This module provides the low-level networking abstractions
including the event loop and network streams.
"""

from .backend import NetworkBackend
from .stream import NetworkStream
from .mock import MockNetworkBackend, MockNetworkStream

__all__ = [
    "NetworkBackend", 
    "NetworkStream",
    "MockNetworkBackend", 
    "MockNetworkStream",
] 