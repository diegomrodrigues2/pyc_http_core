"""
Unit tests for streaming framework.

Tests the RequestStream, ResponseStream, and utility functions
to ensure proper streaming behavior and backpressure.
"""

import pytest
import asyncio
from typing import AsyncIterable, List
from unittest.mock import AsyncMock, MagicMock

from c_http_core.streams import (
    RequestStream,
    ResponseStream,
    create_request_stream,
    create_response_stream,
    read_stream_to_bytes,
    stream_to_list,
    calculate_content_length,
    is_stream_empty,
)
from c_http_core.exceptions import StreamError


class TestRequestStream:
    """Test RequestStream class functionality."""
    
    @pytest.mark.asyncio
    async def test_create_with_bytes(self) -> None:
        """Test creating RequestStream with bytes."""
        data = b"Hello, World!"
        stream = RequestStream(data)
        
        assert stream.content_length is None
        assert stream.chunked is False
        assert stream.closed is False
        
        # Test iteration
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)
        
        assert chunks == [b"Hello, World!"]
    
    @pytest.mark.asyncio
    async def test_create_with_list(self) -> None:
        """Test creating RequestStream with list of bytes."""
        data = [b"Hello", b", ", b"World", b"!"]
        stream = RequestStream(data)
        
        # Test iteration
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)
        
        assert chunks == [b"Hello", b", ", b"World", b"!"]
    
    @pytest.mark.asyncio
    async def test_create_with_async_iterable(self) -> None:
        """Test creating RequestStream with async iterable."""
        async def data_generator():
            yield b"Hello"
            yield b", "
            yield b"World"
            yield b"!"
        
        stream = RequestStream(data_generator())
        
        # Test iteration
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)
        
        assert chunks == [b"Hello", b", ", b"World", b"!"]
    
    @pytest.mark.asyncio
    async def test_create_with_content_length(self) -> None:
        """Test creating RequestStream with content length."""
        data = b"Hello, World!"
        stream = RequestStream(data, content_length=13)
        
        assert stream.content_length == 13
        
        # Test iteration
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)
        
        assert chunks == [b"Hello, World!"]
    
    @pytest.mark.asyncio
    async def test_create_with_chunked(self) -> None:
        """Test creating RequestStream with chunked encoding."""
        data = [b"Hello", b", ", b"World", b"!"]
        stream = RequestStream(data, chunked=True)
        
        assert stream.chunked is True
        
        # Test iteration
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)
        
        assert chunks == [b"Hello", b", ", b"World", b"!"]
    
    @pytest.mark.asyncio
    async def test_content_length_validation(self) -> None:
        """Test content length validation."""
        data = b"Hello, World!"
        
        # Valid content length
        stream = RequestStream(data, content_length=13)
        assert stream.content_length == 13
        
        # Invalid content length
        with pytest.raises(ValueError, match="does not match provided content_length"):
            RequestStream(data, content_length=10)
        
        # Negative content length
        with pytest.raises(ValueError, match="content_length must be non-negative"):
            RequestStream(data, content_length=-1)
    
    @pytest.mark.asyncio
    async def test_aread(self) -> None:
        """Test reading entire stream."""
        data = [b"Hello", b", ", b"World", b"!"]
        stream = RequestStream(data)
        
        result = await stream.aread()
        assert result == b"Hello, World!"
    
    @pytest.mark.asyncio
    async def test_aclose(self) -> None:
        """Test closing stream."""
        data = b"Hello, World!"
        stream = RequestStream(data)
        
        assert stream.closed is False
        await stream.aclose()
        assert stream.closed is True
        
        # Should not be able to iterate after closing
        with pytest.raises(StreamError, match="Cannot iterate over closed stream"):
            async for _ in stream:
                pass
    
    @pytest.mark.asyncio
    async def test_empty_stream(self) -> None:
        """Test empty stream behavior."""
        # Empty bytes
        stream = RequestStream(b"")
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)
        assert chunks == []
        
        # Empty list
        stream = RequestStream([])
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)
        assert chunks == []
        
        # Async iterable that yields nothing
        async def empty_generator():
            if False:
                yield b""
        
        stream = RequestStream(empty_generator())
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)
        assert chunks == []
    
    @pytest.mark.asyncio
    async def test_multiple_iterations(self) -> None:
        """Test that stream can be iterated multiple times."""
        data = [b"Hello", b", ", b"World", b"!"]
        stream = RequestStream(data)
        
        # First iteration
        chunks1 = []
        async for chunk in stream:
            chunks1.append(chunk)
        
        # Second iteration
        chunks2 = []
        async for chunk in stream:
            chunks2.append(chunk)
        
        assert chunks1 == chunks2 == [b"Hello", b", ", b"World", b"!"]


class TestResponseStream:
    """Test ResponseStream class functionality."""
    
    @pytest.fixture
    def mock_connection(self):
        """Create a mock HTTP11Connection."""
        connection = AsyncMock()
        connection._receive_body_chunk.return_value = self._mock_body_chunks()
        connection._response_closed = AsyncMock()
        return connection
    
    async def _mock_body_chunks(self):
        """Mock body chunks for testing."""
        chunks = [b"Hello", b", ", b"World", b"!"]
        for chunk in chunks:
            yield chunk
    
    @pytest.mark.asyncio
    async def test_create_basic(self, mock_connection) -> None:
        """Test creating basic ResponseStream."""
        stream = ResponseStream(mock_connection)
        
        assert stream.content_length is None
        assert stream.chunked is False
        assert stream.encoding is None
        assert stream.closed is False
        assert stream.bytes_read == 0
    
    @pytest.mark.asyncio
    async def test_create_with_options(self, mock_connection) -> None:
        """Test creating ResponseStream with options."""
        stream = ResponseStream(
            mock_connection,
            content_length=13,
            chunked=True,
            encoding="gzip"
        )
        
        assert stream.content_length == 13
        assert stream.chunked is True
        assert stream.encoding == "gzip"
    
    @pytest.mark.asyncio
    async def test_iteration(self, mock_connection) -> None:
        """Test iterating over ResponseStream."""
        stream = ResponseStream(mock_connection)
        
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)
        
        assert chunks == [b"Hello", b", ", b"World", b"!"]
        assert stream.bytes_read == 13
        mock_connection._response_closed.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_content_length_validation(self, mock_connection) -> None:
        """Test content length validation during iteration."""
        # Mock connection that returns more data than content_length
        mock_connection._receive_body_chunk.return_value = self._mock_body_chunks()
        
        stream = ResponseStream(mock_connection, content_length=5)
        
        # Should raise error when reading more than content_length
        with pytest.raises(StreamError, match="Read more bytes"):
            async for chunk in stream:
                pass
    
    @pytest.mark.asyncio
    async def test_aread(self, mock_connection) -> None:
        """Test reading entire stream."""
        stream = ResponseStream(mock_connection)
        
        result = await stream.aread()
        assert result == b"Hello, World!"
        assert stream.bytes_read == 13
        mock_connection._response_closed.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_aclose(self, mock_connection) -> None:
        """Test closing stream."""
        stream = ResponseStream(mock_connection)
        
        assert stream.closed is False
        await stream.aclose()
        assert stream.closed is True
        mock_connection._response_closed.assert_called_once()
        
        # Should not be able to iterate after closing
        with pytest.raises(StreamError, match="Cannot iterate over closed stream"):
            async for _ in stream:
                pass
    
    @pytest.mark.asyncio
    async def test_aclose_early(self, mock_connection) -> None:
        """Test closing stream early during iteration."""
        stream = ResponseStream(mock_connection)
        
        # Start iteration
        async for chunk in stream:
            if chunk == b", ":
                # Close early
                await stream.aclose()
                break
        
        assert stream.closed is True
        mock_connection._response_closed.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_negative_content_length(self, mock_connection) -> None:
        """Test that negative content length is rejected."""
        with pytest.raises(ValueError, match="content_length must be non-negative"):
            ResponseStream(mock_connection, content_length=-1)


class TestStreamFactories:
    """Test factory functions for creating streams."""
    
    @pytest.mark.asyncio
    async def test_create_request_stream_bytes(self) -> None:
        """Test create_request_stream with bytes."""
        stream = create_request_stream(b"Hello, World!")
        
        assert isinstance(stream, RequestStream)
        result = await stream.aread()
        assert result == b"Hello, World!"
    
    @pytest.mark.asyncio
    async def test_create_request_stream_string(self) -> None:
        """Test create_request_stream with string."""
        stream = create_request_stream("Hello, World!")
        
        assert isinstance(stream, RequestStream)
        result = await stream.aread()
        assert result == b"Hello, World!"
    
    @pytest.mark.asyncio
    async def test_create_request_stream_list(self) -> None:
        """Test create_request_stream with list."""
        data = [b"Hello", b", ", b"World", b"!"]
        stream = create_request_stream(data)
        
        assert isinstance(stream, RequestStream)
        result = await stream.aread()
        assert result == b"Hello, World!"
    
    @pytest.mark.asyncio
    async def test_create_request_stream_async_iterable(self) -> None:
        """Test create_request_stream with async iterable."""
        async def data_generator():
            yield b"Hello"
            yield b", "
            yield b"World"
            yield b"!"
        
        stream = create_request_stream(data_generator())
        
        assert isinstance(stream, RequestStream)
        result = await stream.aread()
        assert result == b"Hello, World!"
    
    @pytest.mark.asyncio
    async def test_create_request_stream_with_options(self) -> None:
        """Test create_request_stream with options."""
        stream = create_request_stream(
            b"Hello, World!",
            content_length=13,
            chunked=True
        )
        
        assert stream.content_length == 13
        assert stream.chunked is True
    
    @pytest.mark.asyncio
    async def test_create_response_stream(self) -> None:
        """Test create_response_stream."""
        mock_connection = AsyncMock()
        mock_connection._receive_body_chunk.return_value = iter([b"Hello, World!"])
        mock_connection._response_closed = AsyncMock()
        
        stream = create_response_stream(
            mock_connection,
            content_length=13,
            chunked=True,
            encoding="gzip"
        )
        
        assert isinstance(stream, ResponseStream)
        assert stream.content_length == 13
        assert stream.chunked is True
        assert stream.encoding == "gzip"


class TestStreamUtilities:
    """Test utility functions for working with streams."""
    
    @pytest.mark.asyncio
    async def test_read_stream_to_bytes(self) -> None:
        """Test read_stream_to_bytes function."""
        async def data_generator():
            yield b"Hello"
            yield b", "
            yield b"World"
            yield b"!"
        
        result = await read_stream_to_bytes(data_generator())
        assert result == b"Hello, World!"
    
    @pytest.mark.asyncio
    async def test_stream_to_list(self) -> None:
        """Test stream_to_list function."""
        async def data_generator():
            yield b"Hello"
            yield b", "
            yield b"World"
            yield b"!"
        
        result = await stream_to_list(data_generator())
        assert result == [b"Hello", b", ", b"World", b"!"]
    
    def test_calculate_content_length_bytes(self) -> None:
        """Test calculate_content_length with bytes."""
        data = b"Hello, World!"
        result = calculate_content_length(data)
        assert result == 13
    
    def test_calculate_content_length_list(self) -> None:
        """Test calculate_content_length with list."""
        data = [b"Hello", b", ", b"World", b"!"]
        result = calculate_content_length(data)
        assert result == 13
    
    def test_calculate_content_length_invalid(self) -> None:
        """Test calculate_content_length with invalid data."""
        with pytest.raises(ValueError, match="data must be bytes or list of bytes"):
            calculate_content_length("invalid")
    
    def test_is_stream_empty_bytes(self) -> None:
        """Test is_stream_empty with bytes."""
        assert is_stream_empty(b"") is True
        assert is_stream_empty(b"Hello") is False
    
    def test_is_stream_empty_list(self) -> None:
        """Test is_stream_empty with list."""
        assert is_stream_empty([]) is True
        assert is_stream_empty([b""]) is True
        assert is_stream_empty([b"Hello"]) is False
        assert is_stream_empty([b"Hello", b"World"]) is False
    
    def test_is_stream_empty_async_iterable(self) -> None:
        """Test is_stream_empty with async iterable."""
        # For async iterables, we can't determine emptiness without iteration
        assert is_stream_empty(iter([])) is False


class TestStreamIntegration:
    """Test integration between different stream components."""
    
    @pytest.mark.asyncio
    async def test_request_response_roundtrip(self) -> None:
        """Test round-trip with RequestStream and ResponseStream."""
        # Create request stream
        request_data = [b"Hello", b", ", b"World", b"!"]
        request_stream = RequestStream(request_data)
        
        # Simulate reading request stream
        request_bytes = await request_stream.aread()
        assert request_bytes == b"Hello, World!"
        
        # Create mock response stream
        mock_connection = AsyncMock()
        mock_connection._receive_body_chunk.return_value = iter([b"Response", b" data"])
        mock_connection._response_closed = AsyncMock()
        
        response_stream = ResponseStream(mock_connection)
        
        # Simulate reading response stream
        response_bytes = await response_stream.aread()
        assert response_bytes == b"Response data"
    
    @pytest.mark.asyncio
    async def test_stream_with_factories(self) -> None:
        """Test using factory functions for stream creation."""
        # Create request stream using factory
        request_stream = create_request_stream("Hello, World!")
        request_bytes = await request_stream.aread()
        assert request_bytes == b"Hello, World!"
        
        # Create response stream using factory
        mock_connection = AsyncMock()
        mock_connection._receive_body_chunk.return_value = iter([b"Response"])
        mock_connection._response_closed = AsyncMock()
        
        response_stream = create_response_stream(mock_connection)
        response_bytes = await response_stream.aread()
        assert response_bytes == b"Response"
    
    @pytest.mark.asyncio
    async def test_stream_utilities_integration(self) -> None:
        """Test integration with utility functions."""
        # Create stream
        async def data_generator():
            yield b"Hello"
            yield b", "
            yield b"World"
            yield b"!"
        
        # Test utilities
        bytes_result = await read_stream_to_bytes(data_generator())
        assert bytes_result == b"Hello, World!"
        
        # Test with list
        list_result = await stream_to_list(data_generator())
        assert list_result == [b"Hello", b", ", b"World", b"!"]
        
        # Test content length calculation
        length = calculate_content_length(b"Hello, World!")
        assert length == 13


class TestStreamErrorHandling:
    """Test error handling in streams."""
    
    @pytest.mark.asyncio
    async def test_request_stream_error_during_iteration(self) -> None:
        """Test error handling during RequestStream iteration."""
        async def error_generator():
            yield b"Hello"
            raise RuntimeError("Test error")
        
        stream = RequestStream(error_generator())
        
        with pytest.raises(StreamError, match="Error reading from stream"):
            async for chunk in stream:
                pass
    
    @pytest.mark.asyncio
    async def test_response_stream_error_during_iteration(self) -> None:
        """Test error handling during ResponseStream iteration."""
        async def error_generator():
            yield b"Hello"
            raise RuntimeError("Test error")
        
        mock_connection = AsyncMock()
        mock_connection._receive_body_chunk.return_value = error_generator()
        mock_connection._response_closed = AsyncMock()
        
        stream = ResponseStream(mock_connection)
        
        with pytest.raises(StreamError, match="Error reading from stream"):
            async for chunk in stream:
                pass
        
        # Should call _response_closed on error
        mock_connection._response_closed.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_stream_closed_operations(self) -> None:
        """Test operations on closed streams."""
        stream = RequestStream(b"Hello, World!")
        await stream.aclose()
        
        # Should not be able to read from closed stream
        with pytest.raises(StreamError, match="Cannot read from closed stream"):
            await stream.aread()
        
        # Should not be able to iterate over closed stream
        with pytest.raises(StreamError, match="Cannot iterate over closed stream"):
            async for chunk in stream:
                pass 