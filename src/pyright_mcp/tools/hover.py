"""Hover tool implementation.

This module provides the get_hover MCP tool, which returns type information
and documentation for a symbol at a given position using the Pyright LSP.
"""

from typing import Any

from ..backends.base import BackendError
from ..backends.selector import get_selector
from ..config import get_config
from ..context.project import detect_project
from ..logging_config import get_logger
from ..validation import ValidationError, validate_path, validate_position_input

logger = get_logger("tools.hover")


async def get_hover(
    file: str,
    line: int,
    column: int,
) -> dict[str, Any]:
    """
    Get type information and documentation for a symbol at a position.

    Analyzes the specified position in a Python file and returns type signature
    and documentation if available.

    Args:
        file: Absolute path to the Python file
        line: Line number (1-indexed)
        column: Column number (1-indexed)

    Returns:
        Discriminated union dict with status field:

        Success (with info):
            {
                "status": "success",
                "symbol": "add",
                "type": "(x: int, y: int) -> int",
                "documentation": "Add two integers."
            }

        Success (no info at position):
            {
                "status": "success",
                "symbol": null,
                "type": null,
                "documentation": null
            }

        Error:
            {
                "status": "error",
                "error_code": "file_not_found" | "validation_error" | ...,
                "message": "Human-readable error message"
            }

    Example:
        >>> result = await get_hover("/path/to/file.py", line=10, column=5)
        >>> if result["status"] == "success" and result["type"]:
        ...     print(f"Type: {result['type']}")
    """
    logger.info(f"get_hover called: file={file}, line={line}, column={column}")

    # Step 1: Validate input (convert 1-indexed to 0-indexed)
    try:
        validated_path, line_0, column_0 = validate_position_input(file, line, column)
    except ValidationError as e:
        logger.warning(f"Input validation failed: {e}")
        return e.to_error_response()

    # Step 2: Validate path against allowed_paths
    config = get_config()
    try:
        validated_path = validate_path(
            validated_path, allowed_paths=config.allowed_paths
        )
    except ValidationError as e:
        logger.warning(f"Path validation failed: {e}")
        return e.to_error_response()

    # Step 3: Detect project context
    try:
        context = await detect_project(validated_path)
        logger.debug(f"Project context: root={context.root}")
    except Exception as e:
        logger.error(f"Failed to detect project context: {e}", exc_info=True)
        return {
            "status": "error",
            "error_code": "execution_error",
            "message": f"Failed to detect project context: {e}",
        }

    # Step 4: Get hover backend and execute
    try:
        selector = get_selector()
        backend = await selector.get_hover_backend(validated_path)
        result = await backend.hover(
            validated_path,
            line_0,
            column_0,
            project_root=context.root,
        )
        logger.info(
            f"Hover complete: type={result.type_info is not None}, "
            f"doc={result.documentation is not None}"
        )
        return result.to_dict()

    except BackendError as e:
        logger.error(f"Backend error: {e.error_code} - {e.message}")
        return {
            "status": "error",
            "error_code": e.error_code,
            "message": e.message,
        }
    except Exception as e:
        logger.error(f"Unexpected error during hover: {e}", exc_info=True)
        return {
            "status": "error",
            "error_code": "execution_error",
            "message": f"Unexpected error during hover: {e}",
        }
