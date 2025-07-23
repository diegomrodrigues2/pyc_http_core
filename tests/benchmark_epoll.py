#!/usr/bin/env python3
"""
Performance benchmarks for epoll network backend.

This script provides comprehensive performance benchmarks for the epoll-based
network backend, comparing it with standard asyncio and other implementations.
"""

import asyncio
import time
import statistics
import sys
import os
from typing import List, Dict, Any

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from c_http_core.network import (
    EpollNetworkBackend,
    MockNetworkBackend,
    parse_url,
    format_host_header,
    HAS_EPOLL,
)


class BenchmarkResult:
    """Container for benchmark results."""
    
    def __init__(self, name: str):
        self.name = name
        self.times: List[float] = []
        self.throughputs: List[float] = []
        self.success_count = 0
        self.total_count = 0
    
    def add_result(self, time_taken: float, data_size: int):
        """Add a benchmark result."""
        self.times.append(time_taken)
        if time_taken > 0:
            self.throughputs.append(data_size / time_taken)
        self.success_count += 1
        self.total_count += 1
    
    def add_failure(self):
        """Add a failed benchmark."""
        self.total_count += 1
    
    @property
    def avg_time(self) -> float:
        """Average time taken."""
        return statistics.mean(self.times) if self.times else 0
    
    @property
    def avg_throughput(self) -> float:
        """Average throughput in bytes per second."""
        return statistics.mean(self.throughputs) if self.throughputs else 0
    
    @property
    def success_rate(self) -> float:
        """Success rate as percentage."""
        return (self.success_count / self.total_count * 100) if self.total_count > 0 else 0
    
    def print_summary(self):
        """Print benchmark summary."""
        print(f"\n{self.name}:")
        print(f"  Success Rate: {self.success_rate:.1f}% ({self.success_count}/{self.total_count})")
        if self.times:
            print(f"  Average Time: {self.avg_time:.3f}s")
            print(f"  Min Time: {min(self.times):.3f}s")
            print(f"  Max Time: {max(self.times):.3f}s")
            print(f"  Std Dev: {statistics.stdev(self.times):.3f}s")
        if self.throughputs:
            print(f"  Average Throughput: {self.avg_throughput:.0f} bytes/s")
            print(f"  Min Throughput: {min(self.throughputs):.0f} bytes/s")
            print(f"  Max Throughput: {max(self.throughputs):.0f} bytes/s")


async def benchmark_single_connection(backend, host: str, port: int) -> BenchmarkResult:
    """Benchmark single connection performance."""
    result = BenchmarkResult(f"Single Connection to {host}:{port}")
    
    for i in range(10):  # 10 iterations
        try:
            start_time = time.time()
            
            stream = await backend.connect_tcp(host, port)
            
            # Send HTTP request
            request = (
                "GET / HTTP/1.1\r\n"
                f"Host: {format_host_header(host, port, 'http')}\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode()
            
            await stream.write(request)
            
            # Read response
            response = await stream.read()
            
            await stream.aclose()
            
            end_time = time.time()
            time_taken = end_time - start_time
            
            result.add_result(time_taken, len(response))
            
        except Exception as e:
            print(f"  Iteration {i+1} failed: {e}")
            result.add_failure()
    
    return result


async def benchmark_concurrent_connections(backend, host: str, port: int, concurrency: int) -> BenchmarkResult:
    """Benchmark concurrent connection performance."""
    result = BenchmarkResult(f"Concurrent Connections ({concurrency}) to {host}:{port}")
    
    async def single_request():
        """Make a single request."""
        try:
            start_time = time.time()
            
            stream = await backend.connect_tcp(host, port)
            
            request = (
                "GET / HTTP/1.1\r\n"
                f"Host: {format_host_header(host, port, 'http')}\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode()
            
            await stream.write(request)
            response = await stream.read()
            await stream.aclose()
            
            end_time = time.time()
            time_taken = end_time - start_time
            
            return time_taken, len(response)
            
        except Exception as e:
            return None
    
    # Run concurrent requests
    tasks = [single_request() for _ in range(concurrency)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result_data in results:
        if isinstance(result_data, tuple):
            time_taken, data_size = result_data
            result.add_result(time_taken, data_size)
        else:
            result.add_failure()
    
    return result


async def benchmark_throughput(backend, host: str, port: int) -> BenchmarkResult:
    """Benchmark data throughput."""
    result = BenchmarkResult(f"Throughput Test to {host}:{port}")
    
    for i in range(5):  # 5 iterations
        try:
            stream = await backend.connect_tcp(host, port)
            
            # Request larger data
            request = (
                "GET /bytes/50000 HTTP/1.1\r\n"  # 50KB of data
                f"Host: {format_host_header(host, port, 'http')}\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode()
            
            start_time = time.time()
            await stream.write(request)
            response = await stream.read()
            end_time = time.time()
            
            time_taken = end_time - start_time
            await stream.aclose()
            
            result.add_result(time_taken, len(response))
            
        except Exception as e:
            print(f"  Throughput iteration {i+1} failed: {e}")
            result.add_failure()
    
    return result


async def benchmark_mock_vs_epoll():
    """Compare mock backend vs epoll backend performance."""
    print("Benchmarking Mock vs Epoll Backend Performance")
    print("=" * 50)
    
    # Test with mock backend
    print("\nTesting Mock Backend...")
    mock_backend = MockNetworkBackend()
    
    # Add some test data to mock
    mock_backend.add_connection_data("httpbin.org", 80, b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n" + b"x" * 100)
    
    mock_single = await benchmark_single_connection(mock_backend, "httpbin.org", 80)
    mock_concurrent = await benchmark_concurrent_connections(mock_backend, "httpbin.org", 80, 10)
    mock_throughput = await benchmark_throughput(mock_backend, "httpbin.org", 80)
    
    mock_single.print_summary()
    mock_concurrent.print_summary()
    mock_throughput.print_summary()
    
    # Test with epoll backend if available
    if HAS_EPOLL:
        print("\nTesting Epoll Backend...")
        epoll_backend = EpollNetworkBackend()
        
        try:
            epoll_single = await benchmark_single_connection(epoll_backend, "httpbin.org", 80)
            epoll_concurrent = await benchmark_concurrent_connections(epoll_backend, "httpbin.org", 80, 10)
            epoll_throughput = await benchmark_throughput(epoll_backend, "httpbin.org", 80)
            
            epoll_single.print_summary()
            epoll_concurrent.print_summary()
            epoll_throughput.print_summary()
            
            # Compare results
            print("\nPerformance Comparison:")
            print("=" * 30)
            
            if epoll_single.success_count > 0 and mock_single.success_count > 0:
                speedup = mock_single.avg_time / epoll_single.avg_time
                print(f"Single Connection Speedup: {speedup:.2f}x")
            
            if epoll_concurrent.success_count > 0 and mock_concurrent.success_count > 0:
                speedup = mock_concurrent.avg_time / epoll_concurrent.avg_time
                print(f"Concurrent Speedup: {speedup:.2f}x")
            
            if epoll_throughput.success_count > 0 and mock_throughput.success_count > 0:
                throughput_ratio = epoll_throughput.avg_throughput / mock_throughput.avg_throughput
                print(f"Throughput Ratio: {throughput_ratio:.2f}x")
        
        except Exception as e:
            print(f"Epoll benchmark failed: {e}")
    else:
        print("\nEpoll backend not available on this platform.")


async def benchmark_scalability():
    """Benchmark scalability with different concurrency levels."""
    if not HAS_EPOLL:
        print("Epoll not available, skipping scalability benchmark.")
        return
    
    print("\nScalability Benchmark")
    print("=" * 30)
    
    backend = EpollNetworkBackend()
    concurrency_levels = [1, 5, 10, 20, 50]
    
    for concurrency in concurrency_levels:
        print(f"\nTesting {concurrency} concurrent connections...")
        
        try:
            result = await benchmark_concurrent_connections(backend, "httpbin.org", 80, concurrency)
            result.print_summary()
            
            if result.success_count > 0:
                print(f"  Requests per second: {concurrency / result.avg_time:.1f}")
        
        except Exception as e:
            print(f"  Failed: {e}")


async def benchmark_latency():
    """Benchmark connection latency."""
    if not HAS_EPOLL:
        print("Epoll not available, skipping latency benchmark.")
        return
    
    print("\nLatency Benchmark")
    print("=" * 20)
    
    backend = EpollNetworkBackend()
    result = BenchmarkResult("Connection Latency")
    
    for i in range(20):  # 20 iterations
        try:
            start_time = time.time()
            stream = await backend.connect_tcp("httpbin.org", 80)
            connect_time = time.time() - start_time
            
            # Send minimal request
            request = "GET / HTTP/1.1\r\nHost: httpbin.org\r\nConnection: close\r\n\r\n".encode()
            await stream.write(request)
            
            # Read minimal response
            response = await stream.read(1024)  # Read only first 1KB
            await stream.aclose()
            
            total_time = time.time() - start_time
            
            result.add_result(total_time, len(response))
            
            print(f"  Iteration {i+1}: Connect={connect_time:.3f}s, Total={total_time:.3f}s")
            
        except Exception as e:
            print(f"  Iteration {i+1} failed: {e}")
            result.add_failure()
    
    result.print_summary()


async def main():
    """Run all benchmarks."""
    print("Epoll Network Backend Performance Benchmarks")
    print("=" * 50)
    
    # Check platform
    print(f"Platform: {sys.platform}")
    print(f"Epoll Available: {HAS_EPOLL}")
    
    # Run benchmarks
    await benchmark_mock_vs_epoll()
    await benchmark_scalability()
    await benchmark_latency()
    
    print("\nBenchmark completed!")


if __name__ == "__main__":
    asyncio.run(main()) 