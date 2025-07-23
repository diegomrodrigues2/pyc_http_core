# HTTP/1.1 Connection Guide

This guide covers the HTTP/1.1 connection implementation in c_http_core, including the `HTTP11Connection` class and `ConnectionPool` for efficient connection management.

## Overview

The HTTP/1.1 implementation provides:

- **Full HTTP/1.1 protocol support** using the `h11` library
- **Connection pooling** for efficient resource management
- **Keep-alive support** for connection reuse
- **Streaming request/response bodies** with backpressure
- **Configurable timeouts** and error handling
- **Comprehensive metrics** for monitoring

## Basic Usage

### Simple HTTP Request

```python
import asyncio
from c_http_core import HTTP11Connection, Request
from c_http_core.network import EpollNetworkBackend

async def simple_request():
    # Create network backend
    backend = EpollNetworkBackend()
    
    # Connect to server
    stream = await backend.connect_tcp("httpbin.org", 80)
    
    # Create HTTP/1.1 connection
    connection = HTTP11Connection(stream)
    
    try:
        # Create request
        request = Request.create(
            method="GET",
            url="http://httpbin.org/get",
            headers=[(b"Host", b"httpbin.org")]
        )
        
        # Send request and get response
        response = await connection.handle_request(request)
        
        # Read response body
        body = await response.stream.aread()
        print(f"Status: {response.status_code}")
        print(f"Body: {body[:100]}...")
        
    finally:
        await connection.close()

asyncio.run(simple_request())
```

### POST Request with Body

```python
async def post_request():
    backend = EpollNetworkBackend()
    stream = await backend.connect_tcp("httpbin.org", 80)
    connection = HTTP11Connection(stream)
    
    try:
        # Create request with JSON body
        from c_http_core import create_request_stream
        
        request_stream = create_request_stream(b'{"message": "Hello, World!"}')
        request = Request.create(
            method="POST",
            url="http://httpbin.org/post",
            headers=[
                (b"Host", b"httpbin.org"),
                (b"Content-Type", b"application/json")
            ],
            stream=request_stream
        )
        
        response = await connection.handle_request(request)
        body = await response.stream.aread()
        
        print(f"Status: {response.status_code}")
        print(f"Response: {body}")
        
    finally:
        await connection.close()
```

## Connection Pooling

For applications making multiple requests, use the connection pool for better performance:

### Using ConnectionPool

```python
from c_http_core import ConnectionPool, Request
from c_http_core.network import EpollNetworkBackend

async def pooled_requests():
    backend = EpollNetworkBackend()
    
    # Create connection pool
    pool = ConnectionPool(
        backend=backend,
        max_connections=10,
        max_connections_per_host=5,
        keep_alive_timeout=300.0,
        max_requests_per_connection=100
    )
    
    async with pool:
        # Make multiple requests
        for i in range(5):
            # Get connection from pool
            connection = await pool.get_connection("httpbin.org", 80)
            
            try:
                request = Request.create(
                    method="GET",
                    url=f"http://httpbin.org/get?request={i}",
                    headers=[(b"Host", b"httpbin.org")]
                )
                
                response = await connection.handle_request(request)
                body = await response.stream.aread()
                
                print(f"Request {i}: {response.status_code}")
                
            finally:
                # Return connection to pool
                await pool.return_connection(connection, "httpbin.org", 80)
        
        # Print pool metrics
        print("Pool metrics:", pool.metrics)
```

### Using PooledHTTPClient

For even simpler usage, use the `PooledHTTPClient`:

```python
from c_http_core import PooledHTTPClient, Request

async def client_example():
    backend = EpollNetworkBackend()
    
    # Create pooled client
    client = PooledHTTPClient(
        backend=backend,
        max_connections=10,
        max_connections_per_host=5
    )
    
    async with client:
        # Make requests (connection management is automatic)
        for i in range(5):
            request = Request.create(
                method="GET",
                url=f"http://httpbin.org/get?request={i}",
                headers=[(b"Host", b"httpbin.org")]
            )
            
            response = await client.request(request)
            body = await response.stream.aread()
            
            print(f"Request {i}: {response.status_code}")
        
        # Print client metrics
        print("Client metrics:", client.metrics)
```

## Configuration Options

### HTTP11Connection Configuration

```python
# Create connection with custom configuration
connection = HTTP11Connection(
    stream=stream,
    read_timeout=60.0,           # 60 seconds read timeout
    write_timeout=30.0,          # 30 seconds write timeout
    keep_alive_timeout=600.0,    # 10 minutes keep-alive
    max_requests=50              # Max 50 requests per connection
)
```

### ConnectionPool Configuration

```python
pool = ConnectionPool(
    backend=backend,
    max_connections=20,              # Total connections in pool
    max_connections_per_host=10,     # Max per host
    keep_alive_timeout=300.0,        # 5 minutes keep-alive
    max_requests_per_connection=100, # Max requests per connection
    cleanup_interval=60.0            # Cleanup every 60 seconds
)
```

## Streaming Responses

Handle large responses efficiently with streaming:

```python
async def streaming_example():
    backend = EpollNetworkBackend()
    stream = await backend.connect_tcp("httpbin.org", 80)
    connection = HTTP11Connection(stream)
    
    try:
        # Request large response
        request = Request.create(
            method="GET",
            url="http://httpbin.org/bytes/10000",  # 10KB
            headers=[(b"Host", b"httpbin.org")]
        )
        
        response = await connection.handle_request(request)
        
        # Process response in chunks
        total_bytes = 0
        async for chunk in response.stream:
            total_bytes += len(chunk)
            print(f"Received chunk: {len(chunk)} bytes (total: {total_bytes})")
        
        print(f"Total received: {total_bytes} bytes")
        
    finally:
        await connection.close()
```

## Error Handling

### Timeout Handling

```python
async def timeout_example():
    backend = EpollNetworkBackend()
    stream = await backend.connect_tcp("httpbin.org", 80)
    connection = HTTP11Connection(stream)
    
    try:
        request = Request.create(
            method="GET",
            url="http://httpbin.org/delay/10",  # 10 second delay
            headers=[(b"Host", b"httpbin.org")]
        )
        
        # Request with 5 second timeout
        response = await connection.handle_request(request, timeout=5.0)
        
    except asyncio.TimeoutError:
        print("Request timed out")
    except Exception as e:
        print(f"Request failed: {e}")
    finally:
        await connection.close()
```

### Connection State Management

```python
async def state_management():
    backend = EpollNetworkBackend()
    stream = await backend.connect_tcp("httpbin.org", 80)
    connection = HTTP11Connection(stream)
    
    try:
        # Check connection state
        print(f"Initial state: {connection._state}")
        print(f"Is closed: {connection.is_closed}")
        print(f"Is idle: {connection.is_idle}")
        
        # Make request
        request = Request.create(
            method="GET",
            url="http://httpbin.org/get",
            headers=[(b"Host", b"httpbin.org")]
        )
        
        response = await connection.handle_request(request)
        body = await response.stream.aread()
        
        # Check state after request
        print(f"After request state: {connection._state}")
        print(f"Is idle: {connection.is_idle}")
        
        # Check if connection has expired
        print(f"Has expired: {connection.has_expired(30.0)}")
        
    finally:
        await connection.close()
```

## Metrics and Monitoring

### Connection Metrics

```python
async def metrics_example():
    backend = EpollNetworkBackend()
    stream = await backend.connect_tcp("httpbin.org", 80)
    connection = HTTP11Connection(stream)
    
    try:
        # Make several requests
        for i in range(3):
            request = Request.create(
                method="GET",
                url=f"http://httpbin.org/get?request={i}",
                headers=[(b"Host", b"httpbin.org")]
            )
            
            response = await connection.handle_request(request)
            body = await response.stream.aread()
        
        # Get connection metrics
        metrics = connection.metrics
        print("Connection metrics:")
        print(f"  Request count: {metrics['request_count']}")
        print(f"  Bytes sent: {metrics['bytes_sent']}")
        print(f"  Bytes received: {metrics['bytes_received']}")
        print(f"  Average request time: {metrics['average_request_time']:.3f}s")
        print(f"  Error rate: {metrics['error_rate']:.2%}")
        print(f"  State: {metrics['state']}")
        
    finally:
        await connection.close()
```

### Pool Metrics

```python
async def pool_metrics():
    backend = EpollNetworkBackend()
    pool = ConnectionPool(backend, max_connections=5)
    
    async with pool:
        # Make requests
        for i in range(10):
            connection = await pool.get_connection("httpbin.org", 80)
            
            try:
                request = Request.create(
                    method="GET",
                    url=f"http://httpbin.org/get?request={i}",
                    headers=[(b"Host", b"httpbin.org")]
                )
                
                response = await connection.handle_request(request)
                body = await response.stream.aread()
                
            finally:
                await pool.return_connection(connection, "httpbin.org", 80)
        
        # Get pool metrics
        metrics = pool.metrics
        print("Pool metrics:")
        print(f"  Total connections: {metrics['total_connections']}")
        print(f"  Connections created: {metrics['total_connections_created']}")
        print(f"  Connections closed: {metrics['total_connections_closed']}")
        print(f"  Requests handled: {metrics['total_requests_handled']}")
        print(f"  Connections per host: {metrics['connections_per_host']}")
```

## Best Practices

### 1. Always Close Connections

```python
# Good: Use try/finally
connection = HTTP11Connection(stream)
try:
    response = await connection.handle_request(request)
    # ... process response
finally:
    await connection.close()

# Better: Use async context manager
async with HTTP11Connection(stream) as connection:
    response = await connection.handle_request(request)
    # ... process response
```

### 2. Use Connection Pooling for Multiple Requests

```python
# Good for multiple requests to same host
async with PooledHTTPClient(backend) as client:
    for i in range(100):
        request = Request.create(...)
        response = await client.request(request)
        # ... process response
```

### 3. Handle Streaming Responses Properly

```python
# Good: Process streaming responses
async for chunk in response.stream:
    # Process chunk immediately
    process_chunk(chunk)

# Avoid: Reading entire response into memory
body = await response.stream.aread()  # May use lots of memory
```

### 4. Configure Appropriate Timeouts

```python
# Good: Set reasonable timeouts
connection = HTTP11Connection(
    stream=stream,
    read_timeout=30.0,    # 30 seconds for read
    write_timeout=10.0,   # 10 seconds for write
    keep_alive_timeout=300.0  # 5 minutes keep-alive
)
```

### 5. Monitor Connection Health

```python
# Check connection state before use
if connection.is_closed:
    # Create new connection
    connection = HTTP11Connection(stream)

if connection.has_expired(60.0):
    # Connection is too old, create new one
    await connection.close()
    connection = HTTP11Connection(stream)
```

## Performance Tips

1. **Reuse connections** when making multiple requests to the same host
2. **Use connection pooling** for applications with high request volume
3. **Configure appropriate timeouts** based on your use case
4. **Monitor metrics** to identify performance bottlenecks
5. **Use streaming** for large responses to avoid memory issues
6. **Handle errors gracefully** and implement retry logic when appropriate

## Troubleshooting

### Common Issues

1. **Connection closed unexpectedly**: Check network connectivity and server status
2. **Timeout errors**: Increase timeout values or check server response time
3. **Pool exhaustion**: Increase pool size or implement connection cleanup
4. **Memory issues**: Use streaming responses instead of reading entire body

### Debug Logging

Enable debug logging to troubleshoot issues:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

This will show detailed information about connection states, requests, and responses. 