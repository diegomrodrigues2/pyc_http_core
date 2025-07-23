from setuptools import setup, Extension
from Cython.Build import cythonize

# Extensões Cython para o backend de rede
extensions = [
    Extension(
        "c_http_core.network.epoll",
        ["src/c_http_core/network/epoll.pyx"],
        extra_compile_args=["-O3"],
    )
]

setup(
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            'language_level': "3",
            'boundscheck': False,
            'wraparound': False,
            'initializedcheck': False,
        }
    ),
    zip_safe=False,
) 