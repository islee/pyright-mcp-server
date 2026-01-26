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

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP


def create_mcp_server() -> FastMCP:
    """Create and initialize the MCP server instance.

    Includes defensive logging initialization to prevent duplicate handlers
    when server is created multiple times (e.g., in tests).

    Returns:
        FastMCP server instance
    """
    # Defensive logging initialization
    root_logger = logging.getLogger()
    if not root_logger.hasHandlers():
        from .config import get_config
        from .logging_config import setup_logging

        config = get_config()
        setup_logging(config)

    return FastMCP("pyright-mcp")


# Create server instance
mcp = create_mcp_server()


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


# ============================================================================
# Phase 3: Additional LSP-based tools for completions and references
# ============================================================================


@mcp.tool()
async def get_completions(
    file: str,
    line: int,
    column: int,
    trigger_character: str | None = None,
) -> dict[str, Any]:
    """
    Get code completion suggestions at a position.

    Use this tool to get intelligent code completions based on context.
    Returns a list of completion items with their types and documentation.

    Args:
        file: Absolute path to the Python file
        line: Line number (1-indexed, first line is 1)
        column: Column number (1-indexed, first column is 1)
        trigger_character: Optional trigger character that triggered completion (e.g., ".", "(")

    Returns:
        Dictionary with status field indicating success or error.
        Success includes items array with completion suggestions.
        Each item has label, kind, detail, and documentation.
        Error includes error_code and message.

    Example:
        For "import os; os." with cursor after ".":
        - items: [
            {"label": "getcwd", "kind": "function", "detail": "() -> str"},
            {"label": "listdir", "kind": "function", "detail": "(path) -> list[str]"}
          ]
    """
    # Lazy import to avoid circular dependencies
    from .tools.completions import get_completions as get_completions_impl

    return await get_completions_impl(file, line, column, trigger_character)


@mcp.tool()
async def find_references(
    file: str,
    line: int,
    column: int,
    include_declaration: bool = True,
) -> dict[str, Any]:
    """
    Find all references to a symbol at a position.

    Use this tool to find all places where a symbol (variable, function, class, etc.)
    is referenced in the codebase. Returns file paths and positions of all references.

    Args:
        file: Absolute path to the Python file
        line: Line number (1-indexed, first line is 1)
        column: Column number (1-indexed, first column is 1)
        include_declaration: Whether to include the declaration in results (default True)

    Returns:
        Dictionary with status field indicating success or error.
        Success includes references array with all reference locations.
        Each reference has file, line, and column (1-indexed).
        Also includes count of total references.
        Error includes error_code and message.

    Example:
        For finding all references to a function `my_func`:
        - references: [
            {"file": "/path/file1.py", "line": 10, "column": 5},
            {"file": "/path/file2.py", "line": 25, "column": 12}
          ]
        - count: 2
    """
    # Lazy import to avoid circular dependencies
    from .tools.references import find_references as find_references_impl

    return await find_references_impl(file, line, column, include_declaration)
