"""Entry point for pyright-mcp server.

CRITICAL: Logging must be initialized BEFORE importing server module
to avoid import-time side effects.
"""

import sys


def main() -> int:
    """
    Run the MCP server.

    Initializes logging and configuration, then starts the FastMCP server.

    Returns:
        Exit code (0 for success)
    """
    # Step 1: Initialize logging FIRST (before any other imports that might log)
    from .config import get_config
    from .logging_config import setup_logging

    config = get_config()
    setup_logging(config)

    # Step 2: Now import and run the server (after logging is configured)
    from .server import mcp

    mcp.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
