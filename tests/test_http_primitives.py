"""
Unit tests for HTTP primitives.

Tests the Request, Response, and URLComponents classes
to ensure they work correctly and maintain immutability.
"""

import pytest
import dataclasses
from typing import AsyncIterable

from c_http_core.http_primitives import (
    Request,
    Response,
    URLComponents,
    Headers,
    URL,
)


class TestURLComponents:
    """Test URLComponents class functionality."""
    
    def test_from_url_with_http(self) -> None:
        """Test creating URLComponents from HTTP URL."""
        url = URLComponents.from_url("http://example.com/path")
        assert url.scheme == b"http"
        assert url.host == b"example.com"
        assert url.port == 80
        assert url.path == b"/path"
    
    def test_from_url_with_https(self) -> None:
        """Test creating URLComponents from HTTPS URL."""
        url = URLComponents.from_url("https://example.com:8443/api/v1")
        assert url.scheme == b"https"
        assert url.host == b"example.com"
        assert url.port == 8443
        assert url.path == b"/api/v1"
    
    def test_from_url_without_scheme(self) -> None:
        """Test creating URLComponents from URL without scheme."""
        url = URLComponents.from_url("example.com/test")
        assert url.scheme == b"http"  # Default scheme
        assert url.host == b"example.com"
        assert url.port == 80
        assert url.path == b"/test"
    
    def test_from_url_without_path(self) -> None:
        """Test creating URLComponents from URL without path."""
        url = URLComponents.from_url("https://example.com")
        assert url.scheme == b"https"
        assert url.host == b"example.com"
        assert url.port == 443
        assert url.path == b"/"  # Default path
    
    def test_to_tuple(self) -> None:
        """Test converting URLComponents to tuple."""
        url = URLComponents(b"https", b"example.com", 443, b"/api")
        url_tuple = url.to_tuple()
        assert url_tuple == (b"https", b"example.com", 443, b"/api")
        assert isinstance(url_tuple, tuple)


class TestRequest:
    """Test Request class functionality."""
    
    def test_create_with_strings(self) -> None:
        """Test creating Request with string inputs."""
        request = Request.create("GET", "http://example.com/api")
        assert request.method == b"GET"
        assert request.url == (b"http", b"example.com", 80, b"/api")
        assert request.headers == []
        assert request.stream is None
    
    def test_create_with_bytes(self) -> None:
        """Test creating Request with bytes inputs."""
        request = Request.create(b"POST", (b"https", b"api.example.com", 443, b"/data"))
        assert request.method == b"POST"
        assert request.url == (b"https", b"api.example.com", 443, b"/data")
    
    def test_create_with_headers(self) -> None:
        """Test creating Request with headers."""
        headers = [(b"Content-Type", b"application/json"), (b"Authorization", b"Bearer token")]
        request = Request.create("PUT", "http://example.com/resource", headers=headers)
        assert request.headers == headers
    
    def test_create_with_url_components(self) -> None:
        """Test creating Request with URLComponents."""
        url_components = URLComponents(b"https", b"example.com", 443, b"/api")
        request = Request.create("GET", url_components)
        assert request.url == url_components.to_tuple()
    
    def test_validation_method_bytes(self) -> None:
        """Test that method must be bytes."""
        with pytest.raises(ValueError, match="method must be bytes"):
            Request(method="GET", url=(b"http", b"example.com", 80, b"/"))
    
    def test_validation_url_tuple(self) -> None:
        """Test that url must be a 4-tuple."""
        with pytest.raises(ValueError, match="url must be a 4-tuple"):
            Request(method=b"GET", url=(b"http", b"example.com", 80))
    
    def test_validation_url_components_bytes(self) -> None:
        """Test that URL components must be bytes."""
        with pytest.raises(ValueError, match="URL components must be bytes"):
            Request(method=b"GET", url=("http", b"example.com", 80, b"/"))
    
    def test_validation_url_port_int(self) -> None:
        """Test that URL port must be int."""
        with pytest.raises(ValueError, match="URL port must be int"):
            Request(method=b"GET", url=(b"http", b"example.com", "80", b"/"))
    
    def test_validation_headers_list(self) -> None:
        """Test that headers must be a list."""
        with pytest.raises(ValueError, match="headers must be a list"):
            Request(method=b"GET", url=(b"http", b"example.com", 80, b"/"), headers={})
    
    def test_validation_header_bytes(self) -> None:
        """Test that header names and values must be bytes."""
        with pytest.raises(ValueError, match="header names and values must be bytes"):
            Request(
                method=b"GET",
                url=(b"http", b"example.com", 80, b"/"),
                headers=[("Content-Type", b"text/plain")]
            )
    
    def test_immutability(self) -> None:
        """Test that Request is immutable."""
        request = Request.create("GET", "http://example.com")
        
        # Should not be able to modify attributes
        with pytest.raises(dataclasses.FrozenInstanceError):
            request.method = b"POST"
        
        with pytest.raises(dataclasses.FrozenInstanceError):
            request.headers = [(b"X-Test", b"value")]
    
    def test_with_method(self) -> None:
        """Test creating new request with different method."""
        original = Request.create("GET", "http://example.com")
        modified = original.with_method("POST")
        
        assert modified.method == b"POST"
        assert modified.url == original.url
        assert modified.headers == original.headers
        assert modified is not original  # New instance
    
    def test_with_url(self) -> None:
        """Test creating new request with different URL."""
        original = Request.create("GET", "http://example.com")
        modified = original.with_url("https://api.example.com:8443/v2")
        
        assert modified.method == original.method
        assert modified.url == (b"https", b"api.example.com", 8443, b"/v2")
        assert modified is not original  # New instance
    
    def test_with_headers(self) -> None:
        """Test creating new request with different headers."""
        original = Request.create("GET", "http://example.com")
        new_headers = [(b"X-Test", b"value")]
        modified = original.with_headers(new_headers)
        
        assert modified.method == original.method
        assert modified.url == original.url
        assert modified.headers == new_headers
        assert modified is not original  # New instance
    
    def test_add_header(self) -> None:
        """Test adding a header to request."""
        request = Request.create("GET", "http://example.com")
        modified = request.add_header("Content-Type", "application/json")
        
        assert len(modified.headers) == 1
        assert modified.headers[0] == (b"Content-Type", b"application/json")
        assert modified is not request  # New instance
    
    def test_add_header_with_bytes(self) -> None:
        """Test adding a header with bytes input."""
        request = Request.create("GET", "http://example.com")
        modified = request.add_header(b"Authorization", b"Bearer token")
        
        assert len(modified.headers) == 1
        assert modified.headers[0] == (b"Authorization", b"Bearer token")
    
    def test_url_properties(self) -> None:
        """Test URL property accessors."""
        request = Request.create("GET", "https://example.com:8443/api/v1")
        
        assert request.scheme == b"https"
        assert request.host == b"example.com"
        assert request.port == 8443
        assert request.path == b"/api/v1"


class TestResponse:
    """Test Response class functionality."""
    
    def test_create_basic(self) -> None:
        """Test creating basic Response."""
        response = Response.create(200)
        assert response.status_code == 200
        assert response.headers == []
        assert response.stream is None
        assert response.extensions == {}
    
    def test_create_with_headers(self) -> None:
        """Test creating Response with headers."""
        headers = [(b"Content-Type", b"application/json"), (b"Server", b"nginx")]
        response = Response.create(201, headers=headers)
        assert response.status_code == 201
        assert response.headers == headers
    
    def test_create_with_extensions(self) -> None:
        """Test creating Response with extensions."""
        extensions = {"network_stream": "mock_stream", "protocol": "http/1.1"}
        response = Response.create(200, extensions=extensions)
        assert response.extensions == extensions
    
    def test_validation_status_code_int(self) -> None:
        """Test that status_code must be int."""
        with pytest.raises(ValueError, match="status_code must be int"):
            Response(status_code="200")
    
    def test_validation_headers_list(self) -> None:
        """Test that headers must be a list."""
        with pytest.raises(ValueError, match="headers must be a list"):
            Response(status_code=200, headers={})
    
    def test_validation_header_bytes(self) -> None:
        """Test that header names and values must be bytes."""
        with pytest.raises(ValueError, match="header names and values must be bytes"):
            Response(
                status_code=200,
                headers=[("Content-Type", b"text/plain")]
            )
    
    def test_validation_extensions_dict(self) -> None:
        """Test that extensions must be a dict."""
        with pytest.raises(ValueError, match="extensions must be a dict"):
            Response(status_code=200, extensions=[])
    
    def test_immutability(self) -> None:
        """Test that Response is immutable."""
        response = Response.create(200)
        
        # Should not be able to modify attributes
        with pytest.raises(dataclasses.FrozenInstanceError):
            response.status_code = 404
        
        with pytest.raises(dataclasses.FrozenInstanceError):
            response.headers = [(b"X-Test", b"value")]
    
    def test_with_status_code(self) -> None:
        """Test creating new response with different status code."""
        original = Response.create(200)
        modified = original.with_status_code(404)
        
        assert modified.status_code == 404
        assert modified.headers == original.headers
        assert modified is not original  # New instance
    
    def test_with_headers(self) -> None:
        """Test creating new response with different headers."""
        original = Response.create(200)
        new_headers = [(b"X-Test", b"value")]
        modified = original.with_headers(new_headers)
        
        assert modified.status_code == original.status_code
        assert modified.headers == new_headers
        assert modified is not original  # New instance
    
    def test_with_extensions(self) -> None:
        """Test creating new response with different extensions."""
        original = Response.create(200)
        new_extensions = {"protocol": "http/2"}
        modified = original.with_extensions(new_extensions)
        
        assert modified.status_code == original.status_code
        assert modified.extensions == new_extensions
        assert modified is not original  # New instance
    
    def test_add_header(self) -> None:
        """Test adding a header to response."""
        response = Response.create(200)
        modified = response.add_header("Content-Type", "application/json")
        
        assert len(modified.headers) == 1
        assert modified.headers[0] == (b"Content-Type", b"application/json")
        assert modified is not response  # New instance
    
    def test_add_header_with_bytes(self) -> None:
        """Test adding a header with bytes input."""
        response = Response.create(200)
        modified = response.add_header(b"Server", b"nginx")
        
        assert len(modified.headers) == 1
        assert modified.headers[0] == (b"Server", b"nginx")
    
    def test_get_header_case_insensitive(self) -> None:
        """Test getting header value case-insensitive."""
        response = Response.create(200, headers=[
            (b"Content-Type", b"application/json"),
            (b"Server", b"nginx")
        ])
        
        # Test with string
        assert response.get_header("content-type") == b"application/json"
        assert response.get_header("CONTENT-TYPE") == b"application/json"
        
        # Test with bytes
        assert response.get_header(b"server") == b"nginx"
        assert response.get_header(b"SERVER") == b"nginx"
        
        # Test non-existent header
        assert response.get_header("x-nonexistent") is None
    
    def test_has_header_case_insensitive(self) -> None:
        """Test checking header existence case-insensitive."""
        response = Response.create(200, headers=[
            (b"Content-Type", b"application/json")
        ])
        
        # Test with string
        assert response.has_header("content-type") is True
        assert response.has_header("CONTENT-TYPE") is True
        assert response.has_header("x-nonexistent") is False
        
        # Test with bytes
        assert response.has_header(b"content-type") is True
        assert response.has_header(b"CONTENT-TYPE") is True
        assert response.has_header(b"x-nonexistent") is False


class TestRequestResponseIntegration:
    """Test integration between Request and Response classes."""
    
    def test_request_response_roundtrip(self) -> None:
        """Test creating request and response with similar data."""
        # Create request
        request = Request.create(
            "POST",
            "https://api.example.com:8443/data",
            headers=[(b"Content-Type", b"application/json")],
        )
        
        # Create response
        response = Response.create(
            201,
            headers=[(b"Content-Type", b"application/json"), (b"Location", b"/data/123")],
        )
        
        # Verify they work together
        assert request.method == b"POST"
        assert request.scheme == b"https"
        assert request.host == b"api.example.com"
        assert request.port == 8443
        assert request.path == b"/data"
        
        assert response.status_code == 201
        assert response.get_header("content-type") == b"application/json"
        assert response.get_header("location") == b"/data/123"
    
    def test_immutability_preserved(self) -> None:
        """Test that immutability is preserved across operations."""
        # Create original objects
        original_request = Request.create("GET", "http://example.com")
        original_response = Response.create(200)
        
        # Create modified versions
        modified_request = original_request.add_header("X-Test", "value")
        modified_response = original_response.add_header("X-Test", "value")
        
        # Verify originals are unchanged
        assert len(original_request.headers) == 0
        assert len(original_response.headers) == 0
        
        # Verify modified are new instances
        assert modified_request is not original_request
        assert modified_response is not original_response 