"""
Entry point for python -m geeViz.mcp.

  python -m geeViz.mcp           -> run the MCP server (same as geeViz.mcp.server)
  python -m geeViz.mcp --help   -> show server usage and options
  python -m geeViz.mcp -h       -> same as --help
"""
import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        # Help for the mcp package: docstring + pointer to server help
        print("""geeViz MCP package – Model Context Protocol server for geeViz.

Usage:
  python -m geeViz.mcp              Run the MCP server (stdio).
  python -m geeViz.mcp --help       Show server options and environment variables.

In code:
  from geeViz.mcp import app        Get the FastMCP app instance.

Docs: geeViz/mcp/README.md
""", file=sys.stderr)
        sys.exit(0)
    # Delegate to server main (passes through argv so server can handle future args)
    from geeViz.mcp.server import main
    main()
