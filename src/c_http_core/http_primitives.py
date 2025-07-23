"""
HTTP primitives for c_http_core.

This module defines the core data structures for HTTP requests and responses.
All classes are immutable to ensure thread safety and simplify reasoning.
"""

from typing import (
    Any, 
    AsyncIterable, 
    Dict, 
    List, 
    Optional, 
    Tuple, 
    Union,
    NamedTuple,
)
from dataclasses import dataclass, field
from urllib.parse import urlparse, ParseResult


# Type aliases for better readability
Headers = List[Tuple[bytes, bytes]]
URL = Tuple[bytes, bytes, int, bytes]  # (scheme, host, port, path)
StatusCode = int


class URLComponents(NamedTuple):
    """Immutable representation of URL components."""
    scheme: bytes
    host: bytes
    port: int
    path: bytes
    
    @classmethod
    def from_url(cls, url: str) -> "URLComponents":
        """Create URLComponents from a URL string."""
        parsed = urlparse(url)
        scheme = parsed.scheme.encode() if parsed.scheme else b"http"
        host = parsed.hostname.encode() if parsed.hostname else b""
        port = parsed.port or (443 if scheme == b"https" else 80)
        path = parsed.path.encode() if parsed.path else b"/"
        
        return cls(scheme=scheme, host=host, port=port, path=path)
    
    def to_tuple(self) -> URL:
        """Convert to the internal URL tuple format."""
        return (self.scheme, self.host, self.port, self.path)


@dataclass(frozen=True)
class Request:
    """
    Immutable HTTP request representation.
    
    This class represents an HTTP request with all its components.
    Once created, the request cannot be modified - any changes
    must create a new Request instance.
    """
    
    method: bytes
    url: URL
    headers: Headers = field(default_factory=list)
    stream: Optional[AsyncIterable[bytes]] = None
    
    def __post_init__(self) -> None:
        """Validate request data after initialization."""
        if not isinstance(self.method, bytes):
            raise ValueError("method must be bytes")
        
        if not isinstance(self.url, tuple) or len(self.url) != 4:
            raise ValueError("url must be a 4-tuple (scheme, host, port, path)")
        
        if not all(isinstance(component, bytes) for component in self.url[:2] + (self.url[3],)):
            raise ValueError("URL components must be bytes")
        
        if not isinstance(self.url[2], int):
            raise ValueError("URL port must be int")
        
        if not isinstance(self.headers, list):
            raise ValueError("headers must be a list")
        
        for name, value in self.headers:
            if not isinstance(name, bytes) or not isinstance(value, bytes):
                raise ValueError("header names and values must be bytes")
    
    @classmethod
    def create(
        cls,
        method: Union[str, bytes],
        url: Union[str, URL, URLComponents],
        headers: Optional[Headers] = None,
        stream: Optional[AsyncIterable[bytes]] = None,
    ) -> "Request":
        """
        Create a Request with proper type conversion.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: URL string, tuple, or URLComponents
            headers: Optional list of (name, value) header tuples
            stream: Optional async iterable for request body
            
        Returns:
            New Request instance
        """
        # Convert method to bytes
        if isinstance(method, str):
            method = method.encode()
        
        # Convert URL to internal format
        if isinstance(url, str):
            url_components = URLComponents.from_url(url)
            url = url_components.to_tuple()
        elif isinstance(url, URLComponents):
            url = url.to_tuple()
        elif not isinstance(url, tuple):
            raise ValueError("url must be string, URLComponents, or URL tuple")
        
        # Convert headers
        if headers is None:
            headers = []
        
        return cls(method=method, url=url, headers=headers, stream=stream)
    
    def with_method(self, method: Union[str, bytes]) -> "Request":
        """Create a new request with a different method."""
        if isinstance(method, str):
            method = method.encode()
        return Request(method=method, url=self.url, headers=self.headers, stream=self.stream)
    
    def with_url(self, url: Union[str, URL, URLComponents]) -> "Request":
        """Create a new request with a different URL."""
        if isinstance(url, str):
            url_components = URLComponents.from_url(url)
            url = url_components.to_tuple()
        elif isinstance(url, URLComponents):
            url = url.to_tuple()
        
        return Request(method=self.method, url=url, headers=self.headers, stream=self.stream)
    
    def with_headers(self, headers: Headers) -> "Request":
        """Create a new request with different headers."""
        return Request(method=self.method, url=self.url, headers=headers, stream=self.stream)
    
    def with_stream(self, stream: Optional[AsyncIterable[bytes]]) -> "Request":
        """Create a new request with a different stream."""
        return Request(method=self.method, url=self.url, headers=self.headers, stream=stream)
    
    def add_header(self, name: Union[str, bytes], value: Union[str, bytes]) -> "Request":
        """Add a header to the request."""
        if isinstance(name, str):
            name = name.encode()
        if isinstance(value, str):
            value = value.encode()
        
        new_headers = self.headers + [(name, value)]
        return Request(method=self.method, url=self.url, headers=new_headers, stream=self.stream)
    
    @property
    def scheme(self) -> bytes:
        """Get the URL scheme."""
        return self.url[0]
    
    @property
    def host(self) -> bytes:
        """Get the URL host."""
        return self.url[1]
    
    @property
    def port(self) -> int:
        """Get the URL port."""
        return self.url[2]
    
    @property
    def path(self) -> bytes:
        """Get the URL path."""
        return self.url[3]


@dataclass(frozen=True)
class Response:
    """
    Immutable HTTP response representation.
    
    This class represents an HTTP response with status, headers,
    and a stream for the response body. The response itself is
    immutable, but the stream can be consumed asynchronously.
    """
    
    status_code: StatusCode
    headers: Headers = field(default_factory=list)
    stream: Optional[AsyncIterable[bytes]] = None
    extensions: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate response data after initialization."""
        if not isinstance(self.status_code, int):
            raise ValueError("status_code must be int")
        
        if not isinstance(self.headers, list):
            raise ValueError("headers must be a list")
        
        for name, value in self.headers:
            if not isinstance(name, bytes) or not isinstance(value, bytes):
                raise ValueError("header names and values must be bytes")
        
        if not isinstance(self.extensions, dict):
            raise ValueError("extensions must be a dict")
    
    @classmethod
    def create(
        cls,
        status_code: StatusCode,
        headers: Optional[Headers] = None,
        stream: Optional[AsyncIterable[bytes]] = None,
        extensions: Optional[Dict[str, Any]] = None,
    ) -> "Response":
        """
        Create a Response with proper validation.
        
        Args:
            status_code: HTTP status code
            headers: Optional list of (name, value) header tuples
            stream: Optional async iterable for response body
            extensions: Optional dict for additional data
            
        Returns:
            New Response instance
        """
        if headers is None:
            headers = []
        
        if extensions is None:
            extensions = {}
        
        return cls(
            status_code=status_code,
            headers=headers,
            stream=stream,
            extensions=extensions,
        )
    
    def with_status_code(self, status_code: StatusCode) -> "Response":
        """Create a new response with a different status code."""
        return Response(
            status_code=status_code,
            headers=self.headers,
            stream=self.stream,
            extensions=self.extensions,
        )
    
    def with_headers(self, headers: Headers) -> "Response":
        """Create a new response with different headers."""
        return Response(
            status_code=self.status_code,
            headers=headers,
            stream=self.stream,
            extensions=self.extensions,
        )
    
    def with_stream(self, stream: Optional[AsyncIterable[bytes]]) -> "Response":
        """Create a new response with a different stream."""
        return Response(
            status_code=self.status_code,
            headers=self.headers,
            stream=stream,
            extensions=self.extensions,
        )
    
    def with_extensions(self, extensions: Dict[str, Any]) -> "Response":
        """Create a new response with different extensions."""
        return Response(
            status_code=self.status_code,
            headers=self.headers,
            stream=self.stream,
            extensions=extensions,
        )
    
    def add_header(self, name: Union[str, bytes], value: Union[str, bytes]) -> "Response":
        """Add a header to the response."""
        if isinstance(name, str):
            name = name.encode()
        if isinstance(value, str):
            value = value.encode()
        
        new_headers = self.headers + [(name, value)]
        return Response(
            status_code=self.status_code,
            headers=new_headers,
            stream=self.stream,
            extensions=self.extensions,
        )
    
    def get_header(self, name: Union[str, bytes]) -> Optional[bytes]:
        """Get a header value by name (case-insensitive)."""
        if isinstance(name, str):
            name = name.encode()
        
        name_lower = name.lower()
        for header_name, header_value in self.headers:
            if header_name.lower() == name_lower:
                return header_value
        
        return None
    
    def has_header(self, name: Union[str, bytes]) -> bool:
        """Check if a header exists (case-insensitive)."""
        return self.get_header(name) is not None 