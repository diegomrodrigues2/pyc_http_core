"""
Unit tests for custom exceptions.

Tests the exception hierarchy to ensure proper error handling
and cause tracking.
"""

import pytest

from c_http_core.exceptions import (
    HTTPCoreError,
    ConnectionError,
    ProtocolError,
    TimeoutError,
    StreamError,
)


class TestHTTPCoreError:
    """Test base HTTPCoreError class."""
    
    def test_basic_creation(self) -> None:
        """Test creating basic HTTPCoreError."""
        error = HTTPCoreError("Test error message")
        assert str(error) == "Test error message"
        assert error.message == "Test error message"
        assert error.cause is None
    
    def test_with_cause(self) -> None:
        """Test creating HTTPCoreError with cause."""
        original_error = ValueError("Original error")
        error = HTTPCoreError("Test error message", cause=original_error)
        assert str(error) == "Test error message"
        assert error.message == "Test error message"
        assert error.cause == original_error


class TestConnectionError:
    """Test ConnectionError class."""
    
    def test_basic_creation(self) -> None:
        """Test creating basic ConnectionError."""
        error = ConnectionError("Connection failed")
        assert "Connection error: Connection failed" in str(error)
        assert error.message == "Connection error: Connection failed"
        assert error.cause is None
    
    def test_with_cause(self) -> None:
        """Test creating ConnectionError with cause."""
        original_error = OSError("Network unreachable")
        error = ConnectionError("Connection failed", cause=original_error)
        assert "Connection error: Connection failed" in str(error)
        assert error.cause == original_error


class TestProtocolError:
    """Test ProtocolError class."""
    
    def test_basic_creation(self) -> None:
        """Test creating basic ProtocolError."""
        error = ProtocolError("Invalid HTTP version")
        assert "Protocol error: Invalid HTTP version" in str(error)
        assert error.message == "Protocol error: Invalid HTTP version"
        assert error.cause is None
    
    def test_with_cause(self) -> None:
        """Test creating ProtocolError with cause."""
        original_error = ValueError("Invalid format")
        error = ProtocolError("Invalid HTTP version", cause=original_error)
        assert "Protocol error: Invalid HTTP version" in str(error)
        assert error.cause == original_error


class TestTimeoutError:
    """Test TimeoutError class."""
    
    def test_basic_creation(self) -> None:
        """Test creating basic TimeoutError."""
        error = TimeoutError("Request timed out")
        assert "Timeout error: Request timed out" in str(error)
        assert error.message == "Timeout error: Request timed out"
    
    def test_with_timeout_value(self) -> None:
        """Test creating TimeoutError with timeout value."""
        error = TimeoutError("Request timed out", timeout=30.0)
        assert "Timeout error: Request timed out (timeout: 30.0s)" in str(error)
        assert error.message == "Timeout error: Request timed out (timeout: 30.0s)"


class TestStreamError:
    """Test StreamError class."""
    
    def test_basic_creation(self) -> None:
        """Test creating basic StreamError."""
        error = StreamError("Stream closed unexpectedly")
        assert "Stream error: Stream closed unexpectedly" in str(error)
        assert error.message == "Stream error: Stream closed unexpectedly"
        assert error.cause is None
    
    def test_with_cause(self) -> None:
        """Test creating StreamError with cause."""
        original_error = IOError("Broken pipe")
        error = StreamError("Stream closed unexpectedly", cause=original_error)
        assert "Stream error: Stream closed unexpectedly" in str(error)
        assert error.cause == original_error


class TestExceptionHierarchy:
    """Test exception hierarchy and inheritance."""
    
    def test_inheritance(self) -> None:
        """Test that all exceptions inherit from HTTPCoreError."""
        assert issubclass(ConnectionError, HTTPCoreError)
        assert issubclass(ProtocolError, HTTPCoreError)
        assert issubclass(TimeoutError, HTTPCoreError)
        assert issubclass(StreamError, HTTPCoreError)
    
    def test_exception_types(self) -> None:
        """Test that exceptions are of correct types."""
        conn_error = ConnectionError("test")
        proto_error = ProtocolError("test")
        timeout_error = TimeoutError("test")
        stream_error = StreamError("test")
        
        assert isinstance(conn_error, HTTPCoreError)
        assert isinstance(proto_error, HTTPCoreError)
        assert isinstance(timeout_error, HTTPCoreError)
        assert isinstance(stream_error, HTTPCoreError)
    
    def test_exception_raising(self) -> None:
        """Test that exceptions can be raised and caught properly."""
        with pytest.raises(ConnectionError) as exc_info:
            raise ConnectionError("Connection failed")
        
        assert "Connection error: Connection failed" in str(exc_info.value)
        
        with pytest.raises(ProtocolError) as exc_info:
            raise ProtocolError("Protocol violation")
        
        assert "Protocol error: Protocol violation" in str(exc_info.value)
        
        with pytest.raises(TimeoutError) as exc_info:
            raise TimeoutError("Operation timed out", timeout=60.0)
        
        assert "Timeout error: Operation timed out (timeout: 60.0s)" in str(exc_info.value)
        
        with pytest.raises(StreamError) as exc_info:
            raise StreamError("Stream error occurred")
        
        assert "Stream error: Stream error occurred" in str(exc_info.value) 