"""
Pytest configuration for c_http_core tests.

This file contains shared fixtures and configuration
for all tests in the project.
"""

import pytest
import asyncio
from typing import AsyncIterable, List


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


class MockAsyncStream:
    """Mock async stream for testing."""
    
    def __init__(self, data: List[bytes]) -> None:
        self.data = data
        self.index = 0
    
    def __aiter__(self) -> "MockAsyncStream":
        return self
    
    async def __anext__(self) -> bytes:
        if self.index >= len(self.data):
            raise StopAsyncIteration
        result = self.data[self.index]
        self.index += 1
        return result


@pytest.fixture
def mock_stream():
    """Create a mock async stream for testing."""
    def _create_stream(data: List[bytes]) -> MockAsyncStream:
        return MockAsyncStream(data)
    return _create_stream


@pytest.fixture
def sample_headers():
    """Sample headers for testing."""
    return [
        (b"Content-Type", b"application/json"),
        (b"Authorization", b"Bearer token123"),
        (b"User-Agent", b"c_http_core/0.1.0"),
        (b"Accept", b"*/*"),
    ]


@pytest.fixture
def sample_request_data():
    """Sample request data for testing."""
    return {
        "method": "POST",
        "url": "https://api.example.com:8443/v1/data",
        "headers": [
            (b"Content-Type", b"application/json"),
            (b"Authorization", b"Bearer token123"),
        ],
    }


@pytest.fixture
def sample_response_data():
    """Sample response data for testing."""
    return {
        "status_code": 201,
        "headers": [
            (b"Content-Type", b"application/json"),
            (b"Location", b"/v1/data/123"),
            (b"Server", b"nginx/1.18.0"),
        ],
    }


@pytest.fixture
def sample_stream_data():
    """Sample stream data for testing."""
    return [
        b"Hello",
        b", ",
        b"World",
        b"!",
    ]


@pytest.fixture
def sample_large_stream_data():
    """Sample large stream data for testing."""
    return [b"x" * 1024 for _ in range(100)]  # 100KB of data


@pytest.fixture
def mock_http11_connection():
    """Create a mock HTTP11Connection for testing ResponseStream."""
    from unittest.mock import AsyncMock
    
    connection = AsyncMock()
    connection._receive_body_chunk.return_value = iter([b"Response", b" data"])
    connection._response_closed = AsyncMock()
    return connection


@pytest.fixture
def async_data_generator():
    """Create an async data generator for testing."""
    async def generator(data: List[bytes]):
        for chunk in data:
            yield chunk
    
    return generator 