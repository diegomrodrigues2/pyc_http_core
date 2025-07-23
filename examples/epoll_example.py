#!/usr/bin/env python3
"""
Example usage of the epoll network backend.

This example demonstrates how to use the high-performance epoll-based
network backend for HTTP connections.
"""

import asyncio
import socket
import sys
import os

# Add the src directory to the path so we can import c_http_core
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from c_http_core.network import (
    EpollNetworkBackend,
    EpollEventLoop,
    parse_url,
    format_host_header,
    HAS_EPOLL
)


async def test_tcp_connection():
    """Test basic TCP connection using epoll backend."""
    if not HAS_EPOLL:
        print("Epoll not available on this platform")
        return
    
    print("Testing TCP connection with epoll backend...")
    
    backend = EpollNetworkBackend()
    
    try:
        # Connect to a test server
        stream = await backend.connect_tcp("httpbin.org", 80)
        print(f"Connected to httpbin.org:80")
        print(f"Socket info: {stream.get_extra_info('socket')}")
        print(f"Peer info: {stream.get_extra_info('peername')}")
        
        # Send a simple HTTP request
        request = (
            "GET /get HTTP/1.1\r\n"
            f"Host: {format_host_header('httpbin.org', 80, 'http')}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode()
        
        await stream.write(request)
        print("Sent HTTP request")
        
        # Read response
        response = await stream.read()
        print(f"Received {len(response)} bytes")
        print("Response preview:", response[:200].decode('utf-8', errors='ignore'))
        
        await stream.aclose()
        print("Connection closed")
        
    except Exception as e:
        print(f"Error: {e}")


async def test_tls_connection():
    """Test TLS connection using epoll backend."""
    if not HAS_EPOLL:
        print("Epoll not available on this platform")
        return
    
    print("\nTesting TLS connection with epoll backend...")
    
    backend = EpollNetworkBackend()
    
    try:
        # Connect to HTTPS server
        tcp_stream = await backend.connect_tcp("httpbin.org", 443)
        print("TCP connection established")
        
        # Upgrade to TLS
        tls_stream = await backend.connect_tls(
            tcp_stream, 
            "httpbin.org", 
            443,
            alpn_protocols=["http/1.1"]
        )
        print("TLS handshake completed")
        
        # Send HTTPS request
        request = (
            "GET /get HTTP/1.1\r\n"
            f"Host: {format_host_header('httpbin.org', 443, 'https')}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode()
        
        await tls_stream.write(request)
        print("Sent HTTPS request")
        
        # Read response
        response = await tls_stream.read()
        print(f"Received {len(response)} bytes")
        print("Response preview:", response[:200].decode('utf-8', errors='ignore'))
        
        await tls_stream.aclose()
        print("TLS connection closed")
        
    except Exception as e:
        print(f"Error: {e}")


async def test_event_loop():
    """Test the epoll event loop directly."""
    if not HAS_EPOLL:
        print("Epoll not available on this platform")
        return
    
    print("\nTesting epoll event loop...")
    
    loop = EpollEventLoop()
    
    # Create a simple echo server
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(('127.0.0.1', 0))  # Use random port
    server_sock.listen(1)
    server_sock.setblocking(False)
    
    port = server_sock.getsockname()[1]
    print(f"Echo server listening on port {port}")
    
    # Add server socket to event loop
    def accept_connection():
        try:
            client_sock, addr = server_sock.accept()
            client_sock.setblocking(False)
            print(f"Accepted connection from {addr}")
            
            # Add client socket for reading
            loop.add_reader(client_sock.fileno(), lambda: handle_client(client_sock))
        except BlockingIOError:
            pass
    
    def handle_client(client_sock):
        try:
            data = client_sock.recv(1024)
            if data:
                print(f"Echoing {len(data)} bytes")
                client_sock.send(data)
            else:
                print("Client disconnected")
                loop.remove_reader(client_sock.fileno())
                client_sock.close()
        except (BlockingIOError, ConnectionResetError):
            pass
    
    loop.add_reader(server_sock.fileno(), accept_connection)
    
    # Start event loop in background
    loop_task = asyncio.create_task(loop.run_forever())
    
    # Give it a moment to start
    await asyncio.sleep(0.1)
    
    # Test the echo server
    try:
        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.connect(('127.0.0.1', port))
        
        test_data = b"Hello, epoll!"
        client_sock.send(test_data)
        
        response = client_sock.recv(1024)
        print(f"Echo response: {response}")
        
        client_sock.close()
        
    except Exception as e:
        print(f"Error testing echo server: {e}")
    
    # Stop the event loop
    loop.stop()
    await loop_task
    
    server_sock.close()
    print("Event loop test completed")


async def main():
    """Run all tests."""
    print("Epoll Network Backend Example")
    print("=" * 40)
    
    if not HAS_EPOLL:
        print("Epoll is not available on this platform.")
        print("This example requires Linux with epoll support.")
        return
    
    await test_tcp_connection()
    await test_tls_connection()
    
    # Note: Event loop test is more complex and may need additional setup
    # await test_event_loop()
    
    print("\nAll tests completed!")


if __name__ == "__main__":
    asyncio.run(main()) 