"""
c_http_core - High-performance HTTP transport library

A minimal, robust HTTP transport library focused on performance,
supporting HTTP/1.1, HTTP/2, WebSockets, and Server-Sent Events.
"""

__version__ = "0.1.0"
__author__ = "Developer"
__email__ = "dev@example.com"

# Import main components for easy access
from .http_primitives import Request, Response
from .exceptions import HTTPCoreError, ConnectionError, ProtocolError, StreamError
from .streams import (
    RequestStream,
    ResponseStream,
    create_request_stream,
    create_response_stream,
    read_stream_to_bytes,
    stream_to_list,
    calculate_content_length,
)

__all__ = [
    "Request",
    "Response", 
    "HTTPCoreError",
    "ConnectionError",
    "ProtocolError",
    "StreamError",
    "RequestStream",
    "ResponseStream",
    "create_request_stream",
    "create_response_stream",
    "read_stream_to_bytes",
    "stream_to_list",
    "calculate_content_length",
] 