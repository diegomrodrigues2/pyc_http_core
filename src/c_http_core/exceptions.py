"""
Custom exceptions for c_http_core.

This module defines the exception hierarchy used throughout
the library for error handling and debugging.
"""

from typing import Optional


class HTTPCoreError(Exception):
    """Base exception for all c_http_core errors."""
    
    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(message)
        self.message = message
        self.cause = cause


class ConnectionError(HTTPCoreError):
    """Raised when there's an error with network connections."""
    
    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"Connection error: {message}", cause)


class ProtocolError(HTTPCoreError):
    """Raised when there's an error with HTTP protocol handling."""
    
    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"Protocol error: {message}", cause)


class TimeoutError(HTTPCoreError):
    """Raised when an operation times out."""
    
    def __init__(self, message: str, timeout: Optional[float] = None) -> None:
        if timeout is not None:
            message = f"{message} (timeout: {timeout}s)"
        super().__init__(f"Timeout error: {message}")


class StreamError(HTTPCoreError):
    """Raised when there's an error with stream operations."""
    
    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"Stream error: {message}", cause) 