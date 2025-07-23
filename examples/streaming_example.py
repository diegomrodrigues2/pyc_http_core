"""
Example usage of c_http_core streaming framework.

This example demonstrates how to use RequestStream and ResponseStream
for efficient HTTP request/response handling with streaming.
"""

import asyncio
from typing import AsyncIterable
from c_http_core import (
    Request,
    Response,
    RequestStream,
    ResponseStream,
    create_request_stream,
    create_response_stream,
    read_stream_to_bytes,
    stream_to_list,
    calculate_content_length,
)


async def file_stream_example():
    """Example: Streaming file upload with progress tracking."""
    print("=== File Upload Streaming Example ===")
    
    # Simulate reading a large file in chunks
    async def file_chunk_generator():
        """Simulate reading a file in 8KB chunks."""
        file_content = b"x" * 1024 * 100  # 100KB file
        chunk_size = 8192
        
        for i in range(0, len(file_content), chunk_size):
            chunk = file_content[i:i + chunk_size]
            yield chunk
            # Simulate some processing time
            await asyncio.sleep(0.01)
    
    # Create request stream with chunked transfer encoding
    request_stream = create_request_stream(
        file_chunk_generator(),
        chunked=True
    )
    
    # Create request
    request = Request.create(
        method="POST",
        url="https://api.example.com/upload",
        headers=[
            (b"Content-Type", b"application/octet-stream"),
            (b"Transfer-Encoding", b"chunked"),
        ],
        stream=request_stream
    )
    
    print(f"Request method: {request.method}")
    print(f"Request URL: {request.url}")
    print(f"Request has stream: {request.stream is not None}")
    print(f"Stream is chunked: {request_stream.chunked}")
    
    # Simulate reading the stream with progress
    total_bytes = 0
    async for chunk in request_stream:
        total_bytes += len(chunk)
        print(f"Uploaded: {total_bytes} bytes")
    
    print(f"Total uploaded: {total_bytes} bytes")


async def response_streaming_example():
    """Example: Streaming response processing."""
    print("\n=== Response Streaming Example ===")
    
    # Mock HTTP11Connection for demonstration
    class MockConnection:
        async def _receive_body_chunk(self):
            """Mock receiving body chunks."""
            chunks = [
                b"Hello",
                b", ",
                b"World",
                b"! ",
                b"This is a ",
                b"streaming ",
                b"response.",
            ]
            for chunk in chunks:
                yield chunk
                await asyncio.sleep(0.1)  # Simulate network delay
        
        async def _response_closed(self):
            """Mock response closed callback."""
            print("Response stream closed")
    
    # Create response stream
    connection = MockConnection()
    response_stream = create_response_stream(
        connection,
        content_length=35,
        encoding="utf-8"
    )
    
    # Create response
    response = Response.create(
        status_code=200,
        headers=[
            (b"Content-Type", b"text/plain"),
            (b"Content-Length", b"35"),
        ],
        stream=response_stream
    )
    
    print(f"Response status: {response.status_code}")
    print(f"Response has stream: {response.stream is not None}")
    print(f"Content length: {response_stream.content_length}")
    
    # Process response stream with progress
    print("Processing response stream:")
    total_bytes = 0
    async for chunk in response_stream:
        total_bytes += len(chunk)
        print(f"Received: {chunk.decode()} ({total_bytes} bytes total)")
    
    print(f"Total received: {total_bytes} bytes")


async def utility_functions_example():
    """Example: Using utility functions with streams."""
    print("\n=== Utility Functions Example ===")
    
    # Create a sample stream
    async def sample_data():
        yield b"Hello"
        yield b", "
        yield b"World"
        yield b"!"
    
    # Test utility functions
    print("Testing utility functions:")
    
    # Read entire stream to bytes
    all_bytes = await read_stream_to_bytes(sample_data())
    print(f"read_stream_to_bytes: {all_bytes}")
    
    # Convert stream to list
    chunks = await stream_to_list(sample_data())
    print(f"stream_to_list: {chunks}")
    
    # Calculate content length
    length = calculate_content_length(b"Hello, World!")
    print(f"calculate_content_length: {length}")
    
    # Test with different data types
    data_list = [b"Hello", b", ", b"World", b"!"]
    length_list = calculate_content_length(data_list)
    print(f"calculate_content_length (list): {length_list}")


async def performance_example():
    """Example: Performance comparison between streaming and non-streaming."""
    print("\n=== Performance Example ===")
    
    # Create large dataset
    large_data = [b"x" * 1024 for _ in range(1000)]  # 1MB of data
    
    # Method 1: Load everything in memory
    print("Method 1: Load everything in memory")
    start_time = asyncio.get_event_loop().time()
    
    all_data = b"".join(large_data)
    memory_size = len(all_data)
    
    end_time = asyncio.get_event_loop().time()
    print(f"Time: {end_time - start_time:.3f}s")
    print(f"Memory usage: {memory_size / 1024 / 1024:.2f}MB")
    
    # Method 2: Streaming
    print("\nMethod 2: Streaming")
    start_time = asyncio.get_event_loop().time()
    
    stream = create_request_stream(large_data)
    total_processed = 0
    
    async for chunk in stream:
        total_processed += len(chunk)
        # Simulate processing each chunk
    
    end_time = asyncio.get_event_loop().time()
    print(f"Time: {end_time - start_time:.3f}s")
    print(f"Total processed: {total_processed / 1024 / 1024:.2f}MB")
    print("Memory efficient: Only one chunk in memory at a time")


async def error_handling_example():
    """Example: Error handling in streams."""
    print("\n=== Error Handling Example ===")
    
    # Create a stream that raises an error
    async def error_stream():
        yield b"Hello"
        yield b", "
        raise RuntimeError("Simulated error during streaming")
    
    try:
        stream = create_request_stream(error_stream())
        async for chunk in stream:
            print(f"Received: {chunk}")
    except Exception as e:
        print(f"Caught error: {e}")
    
    # Test closing stream early
    print("\nTesting early stream closure:")
    stream = create_request_stream(b"Hello, World!")
    
    async for chunk in stream:
        print(f"Received: {chunk}")
        if chunk == b"Hello":
            print("Closing stream early...")
            await stream.aclose()
            break


async def main():
    """Run all streaming examples."""
    print("c_http_core Streaming Framework Examples")
    print("=" * 50)
    
    try:
        await file_stream_example()
        await response_streaming_example()
        await utility_functions_example()
        await performance_example()
        await error_handling_example()
        
        print("\n" + "=" * 50)
        print("All examples completed successfully!")
        
    except Exception as e:
        print(f"Error running examples: {e}")


if __name__ == "__main__":
    asyncio.run(main()) 