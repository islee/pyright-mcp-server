"""FastMCP server for pyright-mcp.

NOTE: Do NOT initialize logging here at import time.
Logging is initialized in __main__.py to avoid import side effects.
"""

from typing import Any

from mcp.server.fastmcp import FastMCP

# Create server instance
mcp = FastMCP("pyright-mcp")


@mcp.tool()
async def check_types(
    path: str,
    python_version: str | None = None,
) -> dict[str, Any]:
    """
    Run Pyright type checking on a Python file or directory.

    Use this tool to verify Python code has no type errors before suggesting changes.
    Returns diagnostics with file locations, severity, and error messages.

    Args:
        path: Absolute path to the file or directory to check
        python_version: Python version to check against (e.g., "3.11").
                       Auto-detected from project config if not specified.

    Returns:
        Dictionary with status field indicating success or error.
        Success includes summary, error_count, warning_count, diagnostics.
        Error includes error_code and message.
    """
    # Lazy import to avoid circular dependencies and import-time side effects
    from .tools.check_types import check_types as check_types_impl

    return await check_types_impl(path, python_version)


@mcp.tool()
async def health_check() -> dict[str, Any]:
    """
    Check server health and verify Pyright is available.

    Verifies that Pyright CLI is installed, server configuration is valid,
    and runtime is healthy.

    Returns:
        Dictionary with status field.
        Success includes pyright_version, config, and uptime_seconds.
        Error includes error_code and message.
    """
    # Lazy import to avoid circular dependencies
    from .config import get_config
    from .tools.health_check import health_check as health_check_impl

    config = get_config()
    if not config.enable_health_check:
        return {
            "status": "error",
            "error_code": "disabled",
            "message": "Health check tool is disabled. Set PYRIGHT_MCP_ENABLE_HEALTH_CHECK=true to enable.",
        }

    return await health_check_impl()
