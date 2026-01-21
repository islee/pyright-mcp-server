"""FastMCP server for pyright-mcp.

NOTE: Do NOT initialize logging here at import time.
Logging is initialized in __main__.py to avoid import side effects.

Phase 1 Tools:
- check_types: Type checking via Pyright CLI
- health_check: Server health and configuration

Phase 2 Tools:
- get_hover: Type info and documentation at position via LSP
- go_to_definition: Find definition locations via LSP
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


# ============================================================================
# Phase 2: LSP-based tools for hover and definition
# ============================================================================


@mcp.tool()
async def get_hover(
    file: str,
    line: int,
    column: int,
) -> dict[str, Any]:
    """
    Get type information and documentation for a symbol at a position.

    Use this tool to understand what type a variable, function, or class has,
    and to see its documentation. Useful for understanding code before making changes.

    Args:
        file: Absolute path to the Python file
        line: Line number (1-indexed, first line is 1)
        column: Column number (1-indexed, first column is 1)

    Returns:
        Dictionary with status field indicating success or error.
        Success includes symbol, type, and documentation (any may be null).
        Error includes error_code and message.

    Example:
        For a function call `add(1, 2)` with cursor on `add`:
        - symbol: "add"
        - type: "(x: int, y: int) -> int"
        - documentation: "Add two integers and return the result."
    """
    # Lazy import to avoid circular dependencies
    from .tools.hover import get_hover as get_hover_impl

    return await get_hover_impl(file, line, column)


@mcp.tool()
async def go_to_definition(
    file: str,
    line: int,
    column: int,
) -> dict[str, Any]:
    """
    Find where a symbol is defined.

    Use this tool to navigate to the definition of a variable, function, class,
    or imported module. Returns file path and position of the definition.

    Args:
        file: Absolute path to the Python file
        line: Line number (1-indexed, first line is 1)
        column: Column number (1-indexed, first column is 1)

    Returns:
        Dictionary with status field indicating success or error.
        Success includes definitions array (may be empty if no definition found).
        Each definition has file, line, and column (1-indexed).
        Error includes error_code and message.

    Example:
        For an import `from mymodule import helper` with cursor on `helper`:
        - definitions: [{"file": "/path/to/mymodule.py", "line": 10, "column": 5}]
    """
    # Lazy import to avoid circular dependencies
    from .tools.definition import go_to_definition as go_to_definition_impl

    return await go_to_definition_impl(file, line, column)
