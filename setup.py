"""
Setup script for c_http_core.

This script handles the compilation of Cython extensions and
installation of the package.
"""

import os
import sys
from setuptools import setup, Extension, find_packages
from setuptools.command.build_ext import build_ext

# Check if Cython is available
try:
    from Cython.Build import cythonize
    from Cython.Distutils import build_ext as cython_build_ext
    HAS_CYTHON = True
except ImportError:
    HAS_CYTHON = False
    print("Warning: Cython not found. Epoll backend will not be compiled.")
    print("Install Cython with: pip install Cython>=3.0")


class CustomBuildExt(build_ext):
    """Custom build extension that handles Cython compilation."""
    
    def build_extension(self, ext):
        """Build a Cython extension."""
        if HAS_CYTHON and ext.sources[0].endswith('.pyx'):
            # Use Cython to compile
            from Cython.Build import cythonize
            cythonize([ext], compiler_directives={
                'language_level': 3,
                'boundscheck': False,
                'wraparound': False,
                'initializedcheck': False,
                'cdivision': True,
            })
        super().build_extension(ext)


def get_extensions():
    """Get list of Cython extensions to compile."""
    if not HAS_CYTHON:
        return []
    
    extensions = [
        Extension(
            "c_http_core.network.epoll",
            ["src/c_http_core/network/epoll.pyx"],
            libraries=["c"],
            extra_compile_args=["-O3", "-Wall"],
            extra_link_args=["-O3"],
            define_macros=[("CYTHON_TRACE", "0")],
        )
    ]
    
    return extensions


def get_package_data():
    """Get package data files."""
    return {
        "c_http_core.network": ["*.pxd"],
    }


def get_long_description():
    """Get long description from README."""
    try:
        with open("README.md", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "High-performance HTTP transport library with HTTP/2 support"


def main():
    """Main setup function."""
    # Check Python version
    if sys.version_info < (3, 8):
        raise RuntimeError("Python 3.8 or higher is required")
    
    # Platform-specific settings
    if sys.platform.startswith("linux"):
        # Linux-specific optimizations
        extra_compile_args = ["-O3", "-Wall", "-march=native"]
        extra_link_args = ["-O3"]
    elif sys.platform == "darwin":
        # macOS-specific settings
        extra_compile_args = ["-O3", "-Wall"]
        extra_link_args = ["-O3"]
    else:
        # Windows and other platforms
        extra_compile_args = ["/O2"] if sys.platform == "win32" else ["-O3"]
        extra_link_args = []
    
    # Update extensions with platform-specific settings
    extensions = get_extensions()
    for ext in extensions:
        ext.extra_compile_args = extra_compile_args
        ext.extra_link_args = extra_link_args
    
    setup(
        name="c_http_core",
        version="0.1.0",
        description="High-performance HTTP transport library with HTTP/2 support",
        long_description=get_long_description(),
        long_description_content_type="text/markdown",
        author="Developer",
        author_email="dev@example.com",
        url="https://github.com/yourusername/c_http_core",
        packages=find_packages(where="src"),
        package_dir={"": "src"},
        package_data=get_package_data(),
        ext_modules=cythonize(extensions, compiler_directives={
            'language_level': 3,
            'boundscheck': False,
            'wraparound': False,
            'initializedcheck': False,
            'cdivision': True,
        }) if HAS_CYTHON and extensions else [],
        cmdclass={
            'build_ext': CustomBuildExt,
        },
        python_requires=">=3.8",
        install_requires=[
            "h11>=0.14.0",
            "typing-extensions>=4.0.0",
        ],
        extras_require={
            "dev": [
                "pytest>=7.0.0",
                "pytest-asyncio>=0.21.0",
                "black>=22.0.0",
                "mypy>=1.0.0",
                "pre-commit>=2.20.0",
                "pytest-cov>=4.0.0",
                "Cython>=3.0",
            ],
            "docs": [
                "sphinx>=4.0.0",
                "sphinx-rtd-theme>=1.0.0",
                "myst-parser>=0.18.0",
            ],
        },
        classifiers=[
            "Development Status :: 3 - Alpha",
            "Intended Audience :: Developers",
            "License :: OSI Approved :: MIT License",
            "Operating System :: OS Independent",
            "Programming Language :: Python :: 3",
            "Programming Language :: Python :: 3.8",
            "Programming Language :: Python :: 3.9",
            "Programming Language :: Python :: 3.10",
            "Programming Language :: Python :: 3.11",
            "Programming Language :: Python :: 3.12",
            "Topic :: Internet :: WWW/HTTP",
            "Topic :: Software Development :: Libraries :: Python Modules",
        ],
        keywords=["http", "async", "transport", "http2", "websockets", "epoll"],
        zip_safe=False,
        include_package_data=True,
    )


if __name__ == "__main__":
    main() 