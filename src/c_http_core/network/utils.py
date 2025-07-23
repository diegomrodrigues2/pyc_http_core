"""
Network utilities for c_http_core.

This module provides utility functions for common network operations
including socket creation, SSL context setup, and URL parsing.
"""

import socket
import ssl
import os
from typing import Optional, Tuple, Union
from urllib.parse import urlparse


def create_socket(
    family: int = socket.AF_INET,
    type: int = socket.SOCK_STREAM,
    proto: int = 0
) -> socket.socket:
    """
    Create a socket with optimal settings.
    
    Args:
        family: Address family (default: AF_INET)
        type: Socket type (default: SOCK_STREAM)
        proto: Protocol (default: 0 for auto)
    
    Returns:
        Configured socket object
    
    Raises:
        OSError: If socket creation fails
    """
    sock = socket.socket(family, type, proto)
    
    # Set socket options for better performance
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    
    # Set keep-alive options
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    
    # Platform-specific keep-alive settings
    if hasattr(socket, 'TCP_KEEPIDLE'):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
    if hasattr(socket, 'TCP_KEEPINTVL'):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
    if hasattr(socket, 'TCP_KEEPCNT'):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 6)
    
    return sock


def create_ssl_context(
    alpn_protocols: Optional[list[str]] = None,
    verify_mode: int = ssl.CERT_REQUIRED,
    check_hostname: bool = True,
    cert_file: Optional[str] = None,
    key_file: Optional[str] = None,
) -> ssl.SSLContext:
    """
    Create an SSL context with optimal settings.
    
    Args:
        alpn_protocols: Optional list of ALPN protocols to negotiate
        verify_mode: SSL verification mode
        check_hostname: Whether to verify hostname
        cert_file: Path to certificate file (for client auth)
        key_file: Path to private key file (for client auth)
    
    Returns:
        Configured SSL context
    
    Raises:
        ssl.SSLError: If SSL context creation fails
    """
    context = ssl.create_default_context()
    context.verify_mode = verify_mode
    context.check_hostname = check_hostname
    
    # Set ALPN protocols if provided
    if alpn_protocols:
        context.set_alpn_protocols(alpn_protocols)
    
    # Optimize for performance and security
    context.options |= ssl.OP_NO_COMPRESSION
    context.options |= ssl.OP_NO_RENEGOTIATION
    
    # Disable legacy protocols
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    
    # Set cipher preferences
    context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20')
    
    # Load client certificate if provided
    if cert_file and key_file:
        context.load_cert_chain(cert_file, key_file)
    
    return context


def parse_url(url: str) -> Tuple[str, str, int, str]:
    """
    Parse URL into components.
    
    Args:
        url: URL string to parse
    
    Returns:
        Tuple of (scheme, host, port, path)
    
    Raises:
        ValueError: If URL is malformed
    """
    parsed = urlparse(url)
    
    # Extract scheme
    scheme = parsed.scheme or "http"
    
    # Extract host
    host = parsed.hostname or ""
    if not host:
        raise ValueError("No hostname found in URL")
    
    # Extract port
    port = parsed.port
    if port is None:
        port = 443 if scheme == "https" else 80
    
    # Extract path
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    if parsed.fragment:
        path += "#" + parsed.fragment
    
    return scheme, host, port, path


def format_host_header(host: str, port: int, scheme: str) -> str:
    """
    Format host header for HTTP requests.
    
    Args:
        host: Hostname
        port: Port number
        scheme: URL scheme
    
    Returns:
        Formatted host header string
    """
    if (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
        return host
    return f"{host}:{port}"


def is_ipv6_address(host: str) -> bool:
    """
    Check if a host string is an IPv6 address.
    
    Args:
        host: Host string to check
    
    Returns:
        True if the host is an IPv6 address
    """
    try:
        socket.inet_pton(socket.AF_INET6, host)
        return True
    except (OSError, socket.error):
        return False


def is_ipv4_address(host: str) -> bool:
    """
    Check if a host string is an IPv4 address.
    
    Args:
        host: Host string to check
    
    Returns:
        True if the host is an IPv4 address
    """
    try:
        socket.inet_pton(socket.AF_INET, host)
        return True
    except (OSError, socket.error):
        return False


def get_address_family(host: str) -> int:
    """
    Determine the appropriate address family for a host.
    
    Args:
        host: Host string
    
    Returns:
        Socket address family (AF_INET or AF_INET6)
    """
    if is_ipv6_address(host):
        return socket.AF_INET6
    return socket.AF_INET


def create_connection_socket(host: str, port: int) -> socket.socket:
    """
    Create a socket for connecting to a host.
    
    Args:
        host: Hostname or IP address
        port: Port number
    
    Returns:
        Configured socket ready for connection
    
    Raises:
        OSError: If socket creation fails
    """
    family = get_address_family(host)
    sock = create_socket(family, socket.SOCK_STREAM)
    
    # Set non-blocking mode
    sock.setblocking(False)
    
    return sock


def get_socket_error(sock: socket.socket) -> Optional[str]:
    """
    Get the error message for a socket.
    
    Args:
        sock: Socket object
    
    Returns:
        Error message or None if no error
    """
    try:
        error_code = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if error_code == 0:
            return None
        return os.strerror(error_code)
    except (OSError, socket.error):
        return "Unknown socket error"


def set_socket_timeout(sock: socket.socket, timeout: Optional[float]) -> None:
    """
    Set socket timeout.
    
    Args:
        sock: Socket object
        timeout: Timeout in seconds (None for blocking)
    """
    if timeout is not None:
        sock.settimeout(timeout)
    else:
        sock.settimeout(None)


def get_socket_info(sock: socket.socket) -> dict:
    """
    Get information about a socket.
    
    Args:
        sock: Socket object
    
    Returns:
        Dictionary with socket information
    """
    info = {}
    
    try:
        info['peername'] = sock.getpeername()
    except (OSError, socket.error):
        info['peername'] = None
    
    try:
        info['sockname'] = sock.getsockname()
    except (OSError, socket.error):
        info['sockname'] = None
    
    try:
        info['fileno'] = sock.fileno()
    except (OSError, socket.error):
        info['fileno'] = None
    
    return info


def validate_port(port: Union[int, str]) -> int:
    """
    Validate and convert port to integer.
    
    Args:
        port: Port number (int or string)
    
    Returns:
        Port as integer
    
    Raises:
        ValueError: If port is invalid
    """
    try:
        port_int = int(port)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid port: {port}")
    
    if not (1 <= port_int <= 65535):
        raise ValueError(f"Port must be between 1 and 65535, got {port_int}")
    
    return port_int


def normalize_host(host: str) -> str:
    """
    Normalize hostname for consistent comparison.
    
    Args:
        host: Hostname to normalize
    
    Returns:
        Normalized hostname
    """
    # Remove trailing dots (common in DNS)
    host = host.rstrip('.')
    
    # Convert to lowercase
    host = host.lower()
    
    return host


def is_localhost(host: str) -> bool:
    """
    Check if a host refers to localhost.
    
    Args:
        host: Hostname to check
    
    Returns:
        True if the host is localhost
    """
    localhost_names = {
        'localhost',
        '127.0.0.1',
        '::1',
        '0.0.0.0',
        '::'
    }
    
    return normalize_host(host) in localhost_names 