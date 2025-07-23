# c_http_core

A high-performance HTTP transport library focused on performance, supporting HTTP/1.1, HTTP/2, WebSockets, and Server-Sent Events.

## Overview

`c_http_core` is a minimal, robust HTTP transport library designed to be the foundation for high-performance HTTP clients. It provides:

- **HTTP/1.1 support** with full streaming capabilities
- **HTTP/2 support** with multiplexing (planned)
- **WebSocket support** via HTTP upgrade mechanism (planned)
- **Server-Sent Events (SSE)** support (planned)
- **High-performance networking** with custom epoll-based event loop
- **Connection pooling** for efficient resource management
- **Immutable data structures** for thread safety

## Philosophy

Following the "Do One Thing and Do It Well" principle, `c_http_core` focuses exclusively on:

1. Connection management (pooling)
2. Protocol logic (HTTP/1.1, HTTP/2)
3. Protocol upgrades (WebSockets)
4. Exposing low-level streams for high-level clients

This library is not a complete HTTP client like `httpx`, but rather the transport engine that powers such clients.

## Installation

```bash
# Install from source (development)
git clone https://github.com/yourusername/c_http_core.git
cd c_http_core
pip install -e .

# Install development dependencies
pip install -e ".[dev]"
# Install test dependencies
pip install -e ".[test]"

# Build the epoll extension (Linux only)
python setup.py build_ext --inplace

```

After building, you can run the epoll-specific tests:

```bash
pytest -m epoll
```

## Quick Start

### Basic Usage

```python
import asyncio
from c_http_core import Request, Response

# Create a request
request = Request.create(
    method="GET",
    url="https://httpbin.org/get",
    headers=[(b"User-Agent", b"c_http_core/0.1.0")]
)

# TODO: Add connection pool and HTTP client implementation
# response = await client.request(request)
```

### Streaming Example

```python
import asyncio
from c_http_core import (
    Request, 
    Response, 
    create_request_stream,
    create_response_stream
)

# Create a streaming request
async def file_chunk_generator():
    """Simulate reading a file in chunks."""
    file_content = b"Hello, World!" * 1000  # Large file
    chunk_size = 8192
    for i in range(0, len(file_content), chunk_size):
        yield file_content[i:i + chunk_size]

# Create request with streaming body
request_stream = create_request_stream(
    file_chunk_generator(),
    chunked=True
)

request = Request.create(
    method="POST",
    url="https://api.example.com/upload",
    headers=[(b"Content-Type", b"application/octet-stream")],
    stream=request_stream
)

# Process request stream with progress
total_bytes = 0
async for chunk in request_stream:
    total_bytes += len(chunk)
    print(f"Uploaded: {total_bytes} bytes")

print(f"Total uploaded: {total_bytes} bytes")
```

## Development Status

This project is currently in **Alpha** development. The current implementation includes:

### ✅ Completed (Phase 1 & 2)
- [x] Project structure and configuration
- [x] Custom exception hierarchy
- [x] HTTP primitives (Request, Response, URLComponents)
- [x] Streaming framework (RequestStream, ResponseStream)
- [x] Factory functions and utility functions
- [x] Comprehensive unit tests
- [x] Examples and documentation

### 🚧 In Progress
- [ ] Network backend interfaces
- [ ] Epoll-based event loop (Cython)
- [ ] HTTP/1.1 connection implementation

### 📋 Planned
- [ ] Connection pooling
- [ ] HTTPS and TLS support
- [ ] HTTP/2 implementation
- [ ] WebSocket support
- [ ] Server-Sent Events support
- [ ] Performance benchmarks

## Architecture

The library follows a modular design with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                        │
│  (httpx-like client using c_http_core as transport)        │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   c_http_core (Transport)                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │  ConnectionPool │  │  HTTP11Connection│  │ HTTP2Connection│ │
│  └─────────────────┘  └─────────────────┘  └─────────────┘ │
│                              │                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              Network Backend (Cython)                   │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │ │
│  │  │ EpollLoop   │  │NetworkStream│  │   TLS Support   │ │ │
│  │  └─────────────┘  └─────────────┘  └─────────────────┘ │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Operating System                         │
│  (epoll, sockets, TLS)                                      │
└─────────────────────────────────────────────────────────────┘
```

## Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=c_http_core

# Run specific test file
pytest tests/test_http_primitives.py

# Run with verbose output
pytest -v
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Inspired by [httpcore](https://github.com/encode/httpcore) and [httpx](https://github.com/encode/httpx)
- Built with [h11](https://github.com/python-hyper/h11) for HTTP/1.1 parsing
- Uses [Cython](https://cython.org/) for high-performance networking
