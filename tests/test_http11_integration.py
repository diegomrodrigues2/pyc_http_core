"""
Integration tests for HTTP/1.1 connection implementation.

This module contains integration tests that use real HTTP servers
to validate the HTTP11Connection implementation.
"""

import pytest
import asyncio
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from c_http_core.http11 import HTTP11Connection, ConnectionState
from c_http_core.http_primitives import Request, Response
from c_http_core.network import HAS_EPOLL

# Only import the epoll backend if it is actually available on this
# platform.  Attempting to import it unconditionally causes an
# ImportError on systems without epoll support and prevents the tests
# from being collected.  The test class below is already marked with a
# skip condition based on ``HAS_EPOLL`` so conditional importing here
# keeps test collection working across platforms.
if HAS_EPOLL:
    from c_http_core.network import EpollNetworkBackend
from c_http_core.streams import create_request_stream


@pytest.mark.skipif(not HAS_EPOLL, reason="epoll not available on this platform")
class TestHTTP11Integration:
    """Integration tests with real HTTP server."""

    @pytest.mark.asyncio
    async def test_httpbin_get_request(self):
        """Test GET request to httpbin.org."""
        backend = EpollNetworkBackend()
        try:
            stream = await backend.connect_tcp("httpbin.org", 80, timeout=2.0)
        except Exception as e:
            pytest.skip(f"Network test skipped: {e}")
        connection = HTTP11Connection(stream)

        try:
            request = Request.create(
                method="GET",
                url="http://httpbin.org/get",
                headers=[(b"Host", b"httpbin.org")],
            )

            response = await connection.handle_request(request)
            assert response.status_code == 200

            # Read response body
            body = await response.stream.aread()
            assert b"httpbin.org" in body
            assert b"args" in body

            # Verify connection state
            assert connection._state == ConnectionState.IDLE
            assert connection.is_idle

        finally:
            await connection.close()

    @pytest.mark.asyncio
    async def test_httpbin_post_request(self):
        """Test POST request to httpbin.org."""
        backend = EpollNetworkBackend()
        try:
            stream = await backend.connect_tcp("httpbin.org", 80, timeout=2.0)
        except Exception as e:
            pytest.skip(f"Network test skipped: {e}")
        connection = HTTP11Connection(stream)

        try:
            # Create request with JSON body
            request_stream = create_request_stream(b'{"test": "data"}')
            request = Request.create(
                method="POST",
                url="http://httpbin.org/post",
                headers=[
                    (b"Host", b"httpbin.org"),
                    (b"Content-Type", b"application/json"),
                ],
                stream=request_stream,
            )

            response = await connection.handle_request(request)
            assert response.status_code == 200

            # Read response body
            body = await response.stream.aread()
            assert b"test" in body
            assert b"data" in body

            # Verify our data was received
            assert b'"test": "data"' in body

        finally:
            await connection.close()

    @pytest.mark.asyncio
    async def test_httpbin_keep_alive(self):
        """Test keep-alive with multiple requests to httpbin.org."""
        backend = EpollNetworkBackend()
        try:
            stream = await backend.connect_tcp("httpbin.org", 80, timeout=2.0)
        except Exception as e:
            pytest.skip(f"Network test skipped: {e}")
        connection = HTTP11Connection(stream)

        try:
            # First request
            request1 = Request.create(
                method="GET",
                url="http://httpbin.org/get",
                headers=[(b"Host", b"httpbin.org")],
            )

            response1 = await connection.handle_request(request1)
            assert response1.status_code == 200

            # Verify connection is idle
            assert connection._state == ConnectionState.IDLE
            assert connection.is_idle

            # Second request (should reuse connection)
            request2 = Request.create(
                method="GET",
                url="http://httpbin.org/headers",
                headers=[(b"Host", b"httpbin.org")],
            )

            response2 = await connection.handle_request(request2)
            assert response2.status_code == 200

            # Verify metrics
            assert connection._request_count == 2
            assert connection._bytes_sent > 0
            assert connection._bytes_received > 0

        finally:
            await connection.close()

    @pytest.mark.asyncio
    async def test_httpbin_streaming_response(self):
        """Test streaming response from httpbin.org."""
        backend = EpollNetworkBackend()
        try:
            stream = await backend.connect_tcp("httpbin.org", 80, timeout=2.0)
        except Exception as e:
            pytest.skip(f"Network test skipped: {e}")
        connection = HTTP11Connection(stream)

        try:
            # Request a large response
            request = Request.create(
                method="GET",
                url="http://httpbin.org/bytes/5000",  # 5KB response
                headers=[(b"Host", b"httpbin.org")],
            )

            response = await connection.handle_request(request)
            assert response.status_code == 200

            # Process response in chunks
            total_bytes = 0
            chunk_count = 0

            async for chunk in response.stream:
                total_bytes += len(chunk)
                chunk_count += 1

            # Verify we got the expected amount of data
            assert total_bytes == 5000
            assert chunk_count > 0

        finally:
            await connection.close()

    @pytest.mark.asyncio
    async def test_httpbin_large_request_body(self):
        """Test large request body to httpbin.org."""
        backend = EpollNetworkBackend()
        try:
            stream = await backend.connect_tcp("httpbin.org", 80, timeout=2.0)
        except Exception as e:
            pytest.skip(f"Network test skipped: {e}")
        connection = HTTP11Connection(stream)

        try:
            # Create large request body
            large_data = b"X" * 5000  # 5KB
            request_stream = create_request_stream(large_data)
            request = Request.create(
                method="POST",
                url="http://httpbin.org/post",
                headers=[
                    (b"Host", b"httpbin.org"),
                    (b"Content-Type", b"application/octet-stream"),
                ],
                stream=request_stream,
            )

            response = await connection.handle_request(request)
            assert response.status_code == 200

            # Read response body
            body = await response.stream.aread()

            # Verify our data was received
            assert b"5000" in body  # Content-Length should be 5000

        finally:
            await connection.close()

    @pytest.mark.asyncio
    async def test_httpbin_error_handling(self):
        """Test error handling with httpbin.org."""
        backend = EpollNetworkBackend()
        try:
            stream = await backend.connect_tcp("httpbin.org", 80, timeout=2.0)
        except Exception as e:
            pytest.skip(f"Network test skipped: {e}")
        connection = HTTP11Connection(stream)

        try:
            # Request a 404 error
            request = Request.create(
                method="GET",
                url="http://httpbin.org/nonexistent",
                headers=[(b"Host", b"httpbin.org")],
            )

            response = await connection.handle_request(request)
            assert response.status_code == 404

            # Read response body
            body = await response.stream.aread()
            assert len(body) > 0

        finally:
            await connection.close()

    @pytest.mark.asyncio
    async def test_httpbin_different_methods(self):
        """Test different HTTP methods with httpbin.org."""
        backend = EpollNetworkBackend()
        try:
            stream = await backend.connect_tcp("httpbin.org", 80, timeout=2.0)
        except Exception as e:
            pytest.skip(f"Network test skipped: {e}")
        connection = HTTP11Connection(stream)

        try:
            # Test PUT
            request_stream = create_request_stream(b'{"method": "PUT"}')
            request = Request.create(
                method="PUT",
                url="http://httpbin.org/put",
                headers=[
                    (b"Host", b"httpbin.org"),
                    (b"Content-Type", b"application/json"),
                ],
                stream=request_stream,
            )

            response = await connection.handle_request(request)
            assert response.status_code == 200

            body = await response.stream.aread()
            assert b'"method": "PUT"' in body

            # Test DELETE
            request = Request.create(
                method="DELETE",
                url="http://httpbin.org/delete",
                headers=[(b"Host", b"httpbin.org")],
            )

            response = await connection.handle_request(request)
            assert response.status_code == 200

            body = await response.stream.aread()
            assert b'"method": "DELETE"' in body

        finally:
            await connection.close()

    @pytest.mark.asyncio
    async def test_httpbin_custom_headers(self):
        """Test custom headers with httpbin.org."""
        backend = EpollNetworkBackend()
        try:
            stream = await backend.connect_tcp("httpbin.org", 80, timeout=2.0)
        except Exception as e:
            pytest.skip(f"Network test skipped: {e}")
        connection = HTTP11Connection(stream)

        try:
            request = Request.create(
                method="GET",
                url="http://httpbin.org/headers",
                headers=[
                    (b"Host", b"httpbin.org"),
                    (b"X-Custom-Header", b"test-value"),
                    (b"User-Agent", b"c_http_core/0.1.0"),
                ],
            )

            response = await connection.handle_request(request)
            assert response.status_code == 200

            body = await response.stream.aread()

            # Verify our headers were sent
            assert b"X-Custom-Header" in body
            assert b"test-value" in body
            assert b"User-Agent" in body
            assert b"c_http_core/0.1.0" in body

        finally:
            await connection.close()


@pytest.mark.skipif(not HAS_EPOLL, reason="epoll not available on this platform")
class TestHTTP11Performance:
    """Performance tests for HTTP/1.1 connection."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_performance(self):
        """Test performance with concurrent requests."""
        backend = EpollNetworkBackend()

        async def make_request():
            """Make a single request."""
            try:
                stream = await backend.connect_tcp("httpbin.org", 80, timeout=2.0)
            except Exception:
                return 0
            connection = HTTP11Connection(stream)

            try:
                request = Request.create(
                    method="GET",
                    url="http://httpbin.org/get",
                    headers=[(b"Host", b"httpbin.org")],
                )

                response = await connection.handle_request(request)
                body = await response.stream.aread()

                return len(body)

            finally:
                await connection.close()

        # Make 5 concurrent requests
        start_time = asyncio.get_event_loop().time()

        tasks = [make_request() for _ in range(5)]
        results = await asyncio.gather(*tasks)

        end_time = asyncio.get_event_loop().time()
        total_time = end_time - start_time

        # Skip if none succeeded
        if not any(size > 0 for size in results):
            pytest.skip("Network test skipped: no successful requests")

        # Verify all requests succeeded
        assert len(results) == 5
        assert all(size > 0 for size in results)

        # Log performance metrics
        print(f"Made 5 concurrent requests in {total_time:.3f}s")
        print(f"Average time per request: {total_time/5:.3f}s")

    @pytest.mark.asyncio
    async def test_keep_alive_performance(self):
        """Test performance with keep-alive connections."""
        backend = EpollNetworkBackend()
        try:
            stream = await backend.connect_tcp("httpbin.org", 80, timeout=2.0)
        except Exception as e:
            pytest.skip(f"Network test skipped: {e}")
        connection = HTTP11Connection(stream)

        try:
            start_time = asyncio.get_event_loop().time()

            # Make 10 requests on the same connection
            for i in range(10):
                request = Request.create(
                    method="GET",
                    url=f"http://httpbin.org/get?request={i}",
                    headers=[(b"Host", b"httpbin.org")],
                )

                response = await connection.handle_request(request)
                body = await response.stream.aread()

                assert response.status_code == 200
                assert len(body) > 0

            end_time = asyncio.get_event_loop().time()
            total_time = end_time - start_time

            # Verify connection is still idle
            assert connection._state == ConnectionState.IDLE
            assert connection._request_count == 10

            # Log performance metrics
            print(f"Made 10 keep-alive requests in {total_time:.3f}s")
            print(f"Average time per request: {total_time/10:.3f}s")
            print(f"Total bytes sent: {connection._bytes_sent}")
            print(f"Total bytes received: {connection._bytes_received}")

        finally:
            await connection.close()
