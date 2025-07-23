# AGENTS.md

This repository contains a Cython-based epoll network backend.

To run the full test suite, including tests marked with `epoll`, the extension must be compiled first.

Steps for testing:

1. Install development dependencies (includes `Cython`):
   ```bash
   pip install -e .[dev] -e .[test]
   ```
2. Build the Cython extension in place:
   ```bash
   python setup.py build_ext --inplace
   ```
3. Run the tests normally with `pytest`.

