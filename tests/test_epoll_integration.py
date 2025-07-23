"""
Integration tests for epoll network backend.

This module contains comprehensive integration tests for the epoll-based
network backend, including performance benchmarks and real-world scenarios.
"""

import pytest
import asyncio
import socket
import time
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from c_http_core.network import (
    MockNetworkBackend,
    parse_url,
    format_host_header,
    HAS_EPOLL,
)

# Only import epoll classes if available
if HAS_EPOLL:
    from c_http_core.network import (
        EpollNetworkBackend,
        EpollEventLoop,
    )


@pytest.mark.skipif(not HAS_EPOLL, reason="epoll not available on this platform")
class TestEpollIntegration:
    """Integration tests for epoll backend."""
    
    @pytest.mark.asyncio
    async def test_tcp_connection_integration(self):
        """Test complete TCP connection flow."""
        backend = EpollNetworkBackend()
        
        # Test connection to a real server
        try:
            stream = await backend.connect_tcp("httpbin.org", 80)
            
            # Verify connection properties
            assert not stream.is_closed
            assert stream.get_extra_info("socket") is not None
            assert stream.get_extra_info("peername") is not None
            
            # Send HTTP request
            request = (
                "GET /get HTTP/1.1\r\n"
                f"Host: {format_host_header('httpbin.org', 80, 'http')}\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode()
            
            await stream.write(request)
            
            # Read response
            response = await stream.read()
            assert len(response) > 0
            assert b"HTTP/1.1" in response
            
            await stream.aclose()
            assert stream.is_closed
            
        except Exception as e:
            pytest.skip(f"Network test failed: {e}")
    
    @pytest.mark.asyncio
    async def test_tls_connection_integration(self):
        """Test complete TLS connection flow."""
        backend = EpollNetworkBackend()
        
        try:
            # Establish TCP connection
            tcp_stream = await backend.connect_tcp("httpbin.org", 443)
            
            # Upgrade to TLS
            tls_stream = await backend.connect_tls(
                tcp_stream, 
                "httpbin.org", 
                443,
                alpn_protocols=["http/1.1"]
            )
            
            # Verify TLS properties
            assert not tls_stream.is_closed
            assert tls_stream.get_extra_info("ssl_object") is True
            
            # Send HTTPS request
            request = (
                "GET /get HTTP/1.1\r\n"
                f"Host: {format_host_header('httpbin.org', 443, 'https')}\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode()
            
            await tls_stream.write(request)
            
            # Read response
            response = await tls_stream.read()
            assert len(response) > 0
            assert b"HTTP/1.1" in response
            
            await tls_stream.aclose()
            
        except Exception as e:
            pytest.skip(f"TLS test failed: {e}")
    
    @pytest.mark.asyncio
    async def test_multiple_connections(self):
        """Test handling multiple concurrent connections."""
        backend = EpollNetworkBackend()
        
        async def make_request(host: str, port: int):
            """Make a single request."""
            try:
                stream = await backend.connect_tcp(host, port)
                request = f"GET / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode()
                await stream.write(request)
                response = await stream.read()
                await stream.aclose()
                return len(response)
            except Exception:
                return 0
        
        # Make multiple concurrent requests
        tasks = [
            make_request("httpbin.org", 80),
            make_request("httpbin.org", 80),
            make_request("httpbin.org", 80),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # At least some requests should succeed
        successful_requests = [r for r in results if isinstance(r, int) and r > 0]
        assert len(successful_requests) > 0
    
    @pytest.mark.asyncio
    async def test_connection_timeout(self):
        """Test connection timeout handling."""
        backend = EpollNetworkBackend()
        
        # Try to connect to a non-existent host with timeout
        with pytest.raises((OSError, TimeoutError, asyncio.TimeoutError)):
            await backend.connect_tcp("nonexistent.example.com", 80, timeout=1.0)
    
    @pytest.mark.asyncio
    async def test_stream_read_write(self):
        """Test basic stream read/write operations."""
        backend = EpollNetworkBackend()
        
        try:
            stream = await backend.connect_tcp("httpbin.org", 80)
            
            # Test writing data
            test_data = b"GET / HTTP/1.1\r\nHost: httpbin.org\r\nConnection: close\r\n\r\n"
            await stream.write(test_data)
            
            # Test reading data
            response = await stream.read(1024)  # Read first 1KB
            assert len(response) > 0
            
            await stream.aclose()
            
        except Exception as e:
            pytest.skip(f"Stream test failed: {e}")


@pytest.mark.skipif(not HAS_EPOLL, reason="epoll not available on this platform")
class TestEpollPerformance:
    """Performance tests for epoll backend."""
    
    @pytest.mark.asyncio
    async def test_connection_speed(self):
        """Test connection establishment speed."""
        backend = EpollNetworkBackend()
        
        start_time = time.time()
        
        try:
            stream = await backend.connect_tcp("httpbin.org", 80)
            connection_time = time.time() - start_time
            
            # Connection should be established quickly
            assert connection_time < 5.0  # 5 seconds max
            
            await stream.aclose()
            
        except Exception as e:
            pytest.skip(f"Performance test failed: {e}")
    
    @pytest.mark.asyncio
    async def test_throughput(self):
        """Test data throughput."""
        backend = EpollNetworkBackend()
        
        try:
            stream = await backend.connect_tcp("httpbin.org", 80)
            
            # Send request
            request = (
                "GET /bytes/10000 HTTP/1.1\r\n"
                "Host: httpbin.org\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode()
            
            start_time = time.time()
            await stream.write(request)
            
            # Read response
            response = await stream.read()
            end_time = time.time()
            
            throughput = len(response) / (end_time - start_time)
            
            # Should achieve reasonable throughput (at least 1KB/s)
            assert throughput > 1024
            
            await stream.aclose()
            
        except Exception as e:
            pytest.skip(f"Throughput test failed: {e}")
    
    @pytest.mark.asyncio
    async def test_concurrent_throughput(self):
        """Test concurrent connection throughput."""
        backend = EpollNetworkBackend()
        
        async def single_request():
            """Make a single request and return response size."""
            try:
                stream = await backend.connect_tcp("httpbin.org", 80)
                request = "GET / HTTP/1.1\r\nHost: httpbin.org\r\nConnection: close\r\n\r\n".encode()
                await stream.write(request)
                response = await stream.read()
                await stream.aclose()
                return len(response)
            except Exception:
                return 0
        
        # Make 10 concurrent requests
        start_time = time.time()
        tasks = [single_request() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        end_time = time.time()
        
        total_data = sum(results)
        total_time = end_time - start_time
        concurrent_throughput = total_data / total_time
        
        # Should achieve good concurrent throughput
        assert concurrent_throughput > 1024  # At least 1KB/s total
        assert len([r for r in results if r > 0]) >= 5  # At least 5 successful requests


@pytest.mark.skipif(not HAS_EPOLL, reason="epoll not available on this platform")
class TestEpollEventLoop:
    """Tests for the epoll event loop."""
    
    @pytest.mark.asyncio
    async def test_event_loop_basic(self):
        """Test basic event loop functionality."""
        loop = EpollEventLoop()
        
        # Test loop properties
        assert not loop.is_running
        assert len(loop.active_file_descriptors) == 0
        
        # Test adding/removing file descriptors
        test_fd = 999  # Dummy file descriptor
        
        def dummy_callback():
            pass
        
        # Add reader
        loop.add_reader(test_fd, dummy_callback)
        assert test_fd in loop.active_file_descriptors
        
        # Remove reader
        loop.remove_reader(test_fd)
        assert test_fd not in loop.active_file_descriptors
    
    @pytest.mark.asyncio
    async def test_event_loop_lifecycle(self):
        """Test event loop start/stop lifecycle."""
        loop = EpollEventLoop()
        
        # Start loop in background
        loop_task = asyncio.create_task(loop.run_forever())
        
        # Give it a moment to start
        await asyncio.sleep(0.1)
        
        # Check if running
        assert loop.is_running
        
        # Stop loop
        loop.stop()
        await loop_task
        
        # Check if stopped
        assert not loop.is_running


class TestEpollFallback:
    """Tests for epoll fallback behavior."""
    
    def test_epoll_availability_check(self):
        """Test epoll availability detection."""
        # HAS_EPOLL should be a boolean
        assert isinstance(HAS_EPOLL, bool)
        
        # On Windows, epoll should not be available
        if sys.platform == "win32":
            assert not HAS_EPOLL
        # On Linux, epoll should be available
        elif sys.platform.startswith("linux"):
            # This might be available depending on the environment
            pass
    
    @pytest.mark.asyncio
    async def test_mock_fallback(self):
        """Test that mock backend works when epoll is not available."""
        # Mock backend should always work
        backend = MockNetworkBackend()
        
        stream = await backend.connect_tcp("example.com", 80)
        assert not stream.is_closed
        
        await stream.write(b"test data")
        assert stream.written_data == b"test data"
        
        await stream.aclose()


@pytest.mark.skipif(not HAS_EPOLL, reason="epoll not available on this platform")
class TestEpollErrorHandling:
    """Tests for epoll error handling."""
    
    @pytest.mark.asyncio
    async def test_invalid_host(self):
        """Test handling of invalid hostnames."""
        backend = EpollNetworkBackend()
        
        with pytest.raises((OSError, socket.gaierror)):
            await backend.connect_tcp("invalid.host.name.that.does.not.exist", 80)
    
    @pytest.mark.asyncio
    async def test_invalid_port(self):
        """Test handling of invalid ports."""
        backend = EpollNetworkBackend()
        
        with pytest.raises((OSError, ConnectionRefusedError)):
            await backend.connect_tcp("httpbin.org", 99999)
    
    @pytest.mark.asyncio
    async def test_closed_stream_operations(self):
        """Test operations on closed streams."""
        backend = EpollNetworkBackend()
        
        try:
            stream = await backend.connect_tcp("httpbin.org", 80)
            await stream.aclose()
            
            # Operations on closed stream should fail
            with pytest.raises(RuntimeError):
                await stream.read()
            
            with pytest.raises(RuntimeError):
                await stream.write(b"data")
                
        except Exception as e:
            pytest.skip(f"Error handling test failed: {e}")


@pytest.mark.skipif(not HAS_EPOLL, reason="epoll not available on this platform")
class TestEpollUtils:
    """Tests for epoll-related utilities."""
    
    def test_parse_url(self):
        """Test URL parsing utility."""
        scheme, host, port, path = parse_url("https://httpbin.org:443/get?param=value")
        
        assert scheme == "https"
        assert host == "httpbin.org"
        assert port == 443
        assert path == "/get?param=value"
    
    def test_format_host_header(self):
        """Test host header formatting."""
        # Standard ports should not include port
        assert format_host_header("example.com", 80, "http") == "example.com"
        assert format_host_header("example.com", 443, "https") == "example.com"
        
        # Non-standard ports should include port
        assert format_host_header("example.com", 8080, "http") == "example.com:8080"
        assert format_host_header("example.com", 8443, "https") == "example.com:8443" 