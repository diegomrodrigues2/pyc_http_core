"""
Basic HTTP/1.1 client example using c_http_core.

This example demonstrates how to use the HTTP11Connection
to make HTTP requests with proper streaming and keep-alive.
"""

import asyncio
import logging
from c_http_core.http_primitives import Request
from c_http_core.http11 import HTTP11Connection
from c_http_core.network import EpollNetworkBackend
from c_http_core.streams import create_request_stream

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def simple_get_request():
    """Demonstrate a simple GET request."""
    logger.info("Making simple GET request...")
    
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
        logger.info(f"Response status: {response.status_code}")
        
        # Read response body
        body = await response.stream.aread()
        logger.info(f"Response body length: {len(body)} bytes")
        
        # Check if connection is idle (can be reused)
        logger.info(f"Connection state: {connection._state}")
        logger.info(f"Connection is idle: {connection.is_idle}")
        
    finally:
        await connection.close()


async def post_request_with_body():
    """Demonstrate a POST request with body."""
    logger.info("Making POST request with body...")
    
    backend = EpollNetworkBackend()
    stream = await backend.connect_tcp("httpbin.org", 80)
    connection = HTTP11Connection(stream)
    
    try:
        # Create request with body
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
        
        # Send request and get response
        response = await connection.handle_request(request)
        logger.info(f"Response status: {response.status_code}")
        
        # Read response body
        body = await response.stream.aread()
        logger.info(f"Response body length: {len(body)} bytes")
        
        # Verify our data was received
        if b"Hello, World!" in body:
            logger.info("✓ Our data was received by the server")
        
    finally:
        await connection.close()


async def keep_alive_demo():
    """Demonstrate keep-alive with multiple requests."""
    logger.info("Demonstrating keep-alive with multiple requests...")
    
    backend = EpollNetworkBackend()
    stream = await backend.connect_tcp("httpbin.org", 80)
    connection = HTTP11Connection(stream)
    
    try:
        # First request
        logger.info("Making first request...")
        request1 = Request.create(
            method="GET",
            url="http://httpbin.org/get",
            headers=[(b"Host", b"httpbin.org")]
        )
        
        response1 = await connection.handle_request(request1)
        logger.info(f"First response: {response1.status_code}")
        
        # Check connection state
        logger.info(f"Connection state after first request: {connection._state}")
        logger.info(f"Connection is idle: {connection.is_idle}")
        
        # Second request (should reuse connection)
        logger.info("Making second request...")
        request2 = Request.create(
            method="GET",
            url="http://httpbin.org/headers",
            headers=[(b"Host", b"httpbin.org")]
        )
        
        response2 = await connection.handle_request(request2)
        logger.info(f"Second response: {response2.status_code}")
        
        # Check metrics
        logger.info(f"Total requests: {connection._request_count}")
        logger.info(f"Bytes sent: {connection._bytes_sent}")
        logger.info(f"Bytes received: {connection._bytes_received}")
        
    finally:
        await connection.close()


async def streaming_response_demo():
    """Demonstrate streaming response handling."""
    logger.info("Demonstrating streaming response...")
    
    backend = EpollNetworkBackend()
    stream = await backend.connect_tcp("httpbin.org", 80)
    connection = HTTP11Connection(stream)
    
    try:
        # Request a large response
        request = Request.create(
            method="GET",
            url="http://httpbin.org/bytes/10000",  # 10KB response
            headers=[(b"Host", b"httpbin.org")]
        )
        
        response = await connection.handle_request(request)
        logger.info(f"Response status: {response.status_code}")
        
        # Process response in chunks
        total_bytes = 0
        chunk_count = 0
        
        async for chunk in response.stream:
            total_bytes += len(chunk)
            chunk_count += 1
            logger.info(f"Received chunk {chunk_count}: {len(chunk)} bytes (total: {total_bytes})")
        
        logger.info(f"Streaming complete: {total_bytes} bytes in {chunk_count} chunks")
        
    finally:
        await connection.close()


async def main():
    """Run all examples."""
    logger.info("Starting HTTP/1.1 client examples...")
    
    try:
        await simple_get_request()
        print()
        
        await post_request_with_body()
        print()
        
        await keep_alive_demo()
        print()
        
        await streaming_response_demo()
        
    except Exception as e:
        logger.error(f"Example failed: {e}")
        raise
    
    logger.info("All examples completed successfully!")


if __name__ == "__main__":
    asyncio.run(main()) 