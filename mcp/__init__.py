"""
geeViz MCP (Model Context Protocol) server package.

Exposes an MCP server with 33 execution and introspection tools for
Earth Engine via geeViz.  Unlike static code snippets, these tools
execute code in a persistent REPL, inspect live GEE assets, and
dynamically query API signatures.

Quick start:
  Run server:    python -m geeViz.mcp.server
  Help:          python -m geeViz.mcp.server --help
  As package:    python -m geeViz.mcp --help

  In code:       from geeViz.mcp import app

See geeViz/mcp/README.md for setup and tool documentation.
"""

# Copyright 2026 Ian Housman
# Licensed under the Apache License, Version 2.0. See license in repo.

__author__ = "Ian Housman"
__email__ = "ian.housman@gmail.com"

# Version format yyyy.m.n
__version__ = "2026.3.1"

__all__ = ["app", "__version__"]


def __getattr__(name: str):
    """Lazy import of app to avoid circular import when running python -m geeViz.mcp."""
    if name == "app":
        from geeViz.mcp.server import app
        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
