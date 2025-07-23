"""
Advanced HTTP/1.1 client example using c_http_core.

This example demonstrates advanced features including:
- Connection pooling
- Concurrent requests
- Streaming responses
- Error handling and retries
- Metrics monitoring
- Custom timeouts
"""

import asyncio
import logging
import time
import json
from typing import List, Dict, Any
from urllib.parse import urlparse

from c_http_core import (
    HTTP11Connection, 
    ConnectionPool, 
    PooledHTTPClient,
    Request, 
    Response,
    create_request_stream
)
from c_http_core.network import EpollNetworkBackend
from c_http_core.exceptions import ConnectionError, ProtocolError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AdvancedHTTPClient:
    """Advanced HTTP client with connection pooling and monitoring."""
    
    def __init__(
        self,
        max_connections: int = 20,
        max_connections_per_host: int = 10,
        keep_alive_timeout: float = 300.0,
        request_timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """Initialize the advanced HTTP client."""
        self.backend = EpollNetworkBackend()
        self.client = PooledHTTPClient(
            backend=self.backend,
            max_connections=max_connections,
            max_connections_per_host=max_connections_per_host,
            keep_alive_timeout=keep_alive_timeout,
            max_requests_per_connection=100,
        )
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_bytes_sent": 0,
            "total_bytes_received": 0,
            "total_request_time": 0.0,
        }
    
    async def __aenter__(self):
        """Start the client."""
        await self.client.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Stop the client."""
        await self.client.stop()
    
    async def request_with_retry(
        self, 
        method: str, 
        url: str, 
        headers: List[tuple] = None,
        body: bytes = None,
        timeout: float = None
    ) -> Response:
        """
        Make an HTTP request with automatic retries.
        
        Args:
            method: HTTP method
            url: Request URL
            headers: Request headers
            body: Request body
            timeout: Request timeout
            
        Returns:
            HTTP response
            
        Raises:
            Exception: If all retries fail
        """
        headers = headers or []
        timeout = timeout or self.request_timeout
        
        # Add default headers
        if not any(name.lower() == b"user-agent" for name, _ in headers):
            headers.append((b"User-Agent", b"c_http_core/0.1.0"))
        
        # Create request
        request_kwargs = {
            "method": method,
            "url": url,
            "headers": headers,
        }
        
        if body:
            request_kwargs["stream"] = create_request_stream(body)
        
        request = Request.create(**request_kwargs)
        
        # Try request with retries
        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                start_time = time.time()
                
                response = await self.client.request(request)
                
                duration = time.time() - start_time
                self._update_stats(duration, len(body or b""))
                
                logger.info(
                    f"Request {method} {url} -> {response.status_code} "
                    f"({duration:.3f}s, attempt {attempt + 1})"
                )
                
                return response
                
            except Exception as e:
                last_exception = e
                self.stats["failed_requests"] += 1
                
                if attempt < self.max_retries:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}): {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Request failed after {self.max_retries + 1} attempts: {e}")
        
        raise last_exception
    
    def _update_stats(self, duration: float, bytes_sent: int):
        """Update request statistics."""
        self.stats["total_requests"] += 1
        self.stats["successful_requests"] += 1
        self.stats["total_request_time"] += duration
        self.stats["total_bytes_sent"] += bytes_sent
    
    async def get_json(self, url: str, headers: List[tuple] = None) -> Dict[str, Any]:
        """Make a GET request and return JSON response."""
        response = await self.request_with_retry("GET", url, headers)
        body = await response.stream.aread()
        return json.loads(body.decode('utf-8'))
    
    async def post_json(self, url: str, data: Dict[str, Any], headers: List[tuple] = None) -> Dict[str, Any]:
        """Make a POST request with JSON data."""
        body = json.dumps(data).encode('utf-8')
        if headers is None:
            headers = []
        headers.append((b"Content-Type", b"application/json"))
        
        response = await self.request_with_retry("POST", url, headers, body)
        response_body = await response.stream.aread()
        return json.loads(response_body.decode('utf-8'))
    
    async def download_file(self, url: str, chunk_size: int = 8192) -> bytes:
        """Download a file with streaming."""
        response = await self.request_with_retry("GET", url)
        
        chunks = []
        total_bytes = 0
        
        async for chunk in response.stream:
            chunks.append(chunk)
            total_bytes += len(chunk)
            logger.debug(f"Downloaded {total_bytes} bytes...")
        
        return b''.join(chunks)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        stats = self.stats.copy()
        stats.update(self.client.metrics)
        
        if stats["total_requests"] > 0:
            stats["average_request_time"] = stats["total_request_time"] / stats["total_requests"]
            stats["success_rate"] = stats["successful_requests"] / stats["total_requests"]
        else:
            stats["average_request_time"] = 0.0
            stats["success_rate"] = 0.0
        
        return stats


async def concurrent_requests_demo():
    """Demonstrate concurrent requests with connection pooling."""
    logger.info("=== Concurrent Requests Demo ===")
    
    urls = [
        "http://httpbin.org/get?request=1",
        "http://httpbin.org/get?request=2", 
        "http://httpbin.org/get?request=3",
        "http://httpbin.org/headers",
        "http://httpbin.org/user-agent",
    ]
    
    async with AdvancedHTTPClient(max_connections=10) as client:
        # Make concurrent requests
        tasks = []
        for url in urls:
            task = asyncio.create_task(client.get_json(url))
            tasks.append(task)
        
        # Wait for all requests to complete
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.time() - start_time
        
        # Process results
        successful = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Request {i} failed: {result}")
            else:
                successful += 1
                logger.info(f"Request {i} successful: {result.get('url', 'N/A')}")
        
        logger.info(f"Completed {len(urls)} requests in {total_time:.3f}s ({successful} successful)")
        
        # Print statistics
        stats = client.get_stats()
        logger.info(f"Client stats: {stats}")


async def streaming_demo():
    """Demonstrate streaming response handling."""
    logger.info("=== Streaming Demo ===")
    
    async with AdvancedHTTPClient() as client:
        # Download a large file
        logger.info("Downloading large file...")
        start_time = time.time()
        
        data = await client.download_file("http://httpbin.org/bytes/50000")  # 50KB
        
        duration = time.time() - start_time
        logger.info(f"Downloaded {len(data)} bytes in {duration:.3f}s")
        logger.info(f"Download speed: {len(data) / duration / 1024:.1f} KB/s")


async def error_handling_demo():
    """Demonstrate error handling and retries."""
    logger.info("=== Error Handling Demo ===")
    
    async with AdvancedHTTPClient(max_retries=2) as client:
        # Test with a URL that will fail
        try:
            response = await client.request_with_retry(
                "GET", 
                "http://httpbin.org/status/500",
                timeout=5.0
            )
            logger.info(f"Got response: {response.status_code}")
        except Exception as e:
            logger.info(f"Expected error handled: {e}")
        
        # Test with a non-existent URL
        try:
            response = await client.request_with_retry(
                "GET", 
                "http://httpbin.org/nonexistent",
                timeout=5.0
            )
            logger.info(f"Got response: {response.status_code}")
        except Exception as e:
            logger.info(f"Expected error handled: {e}")


async def performance_benchmark():
    """Run a performance benchmark."""
    logger.info("=== Performance Benchmark ===")
    
    async with AdvancedHTTPClient(
        max_connections=20,
        max_connections_per_host=10,
        request_timeout=10.0
    ) as client:
        # Benchmark with different numbers of concurrent requests
        for num_requests in [10, 50, 100]:
            logger.info(f"Benchmarking {num_requests} concurrent requests...")
            
            start_time = time.time()
            
            # Create tasks
            tasks = []
            for i in range(num_requests):
                url = f"http://httpbin.org/get?request={i}"
                task = asyncio.create_task(client.get_json(url))
                tasks.append(task)
            
            # Wait for completion
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            duration = time.time() - start_time
            successful = sum(1 for r in results if not isinstance(r, Exception))
            
            logger.info(
                f"  {num_requests} requests: {successful} successful in {duration:.3f}s "
                f"({successful/duration:.1f} req/s)"
            )
        
        # Print final statistics
        stats = client.get_stats()
        logger.info("Final statistics:")
        for key, value in stats.items():
            if isinstance(value, float):
                logger.info(f"  {key}: {value:.3f}")
            else:
                logger.info(f"  {key}: {value}")


async def api_client_demo():
    """Demonstrate a real-world API client."""
    logger.info("=== API Client Demo ===")
    
    async with AdvancedHTTPClient() as client:
        # Simulate API calls
        logger.info("Making API calls...")
        
        # GET request
        user_data = await client.get_json("http://httpbin.org/get?user=john")
        logger.info(f"User data: {user_data.get('args', {})}")
        
        # POST request with JSON
        post_data = {"name": "John Doe", "email": "john@example.com"}
        response = await client.post_json("http://httpbin.org/post", post_data)
        logger.info(f"POST response: {response.get('json', {})}")
        
        # PUT request
        put_data = {"status": "updated"}
        response = await client.post_json("http://httpbin.org/put", put_data)
        logger.info(f"PUT response: {response.get('json', {})}")
        
        # DELETE request
        response = await client.request_with_retry("DELETE", "http://httpbin.org/delete")
        logger.info(f"DELETE response: {response.status_code}")


async def main():
    """Run all demos."""
    logger.info("Starting Advanced HTTP/1.1 Client Examples")
    
    try:
        await concurrent_requests_demo()
        print()
        
        await streaming_demo()
        print()
        
        await error_handling_demo()
        print()
        
        await performance_benchmark()
        print()
        
        await api_client_demo()
        
    except Exception as e:
        logger.error(f"Demo failed: {e}")
        raise
    
    logger.info("All demos completed successfully!")


if __name__ == "__main__":
    asyncio.run(main()) 