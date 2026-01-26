"""Definition tool implementation.

This module provides the go_to_definition MCP tool, which finds the definition
location(s) for a symbol at a given position using the Pyright LSP.
"""

import time
from typing import Any

from ..backends.base import BackendError
from ..backends.selector import get_selector
from ..config import get_config
from ..context.project import detect_project
from ..logging_config import get_logger
from ..metrics import get_metrics_collector
from ..validation import ValidationError, validate_path, validate_position_input

logger = get_logger("tools.definition")


async def go_to_definition(
    file: str,
    line: int,
    column: int,
) -> dict[str, Any]:
    """
    Find the definition location(s) for a symbol at a position.

    Analyzes the specified position in a Python file and returns the location(s)
    where the symbol is defined.

    Args:
        file: Absolute path to the Python file
        line: Line number (1-indexed)
        column: Column number (1-indexed)

    Returns:
        Discriminated union dict with status field:

        Success (with definitions):
            {
                "status": "success",
                "definitions": [
                    {
                        "file": "/path/to/module.py",
                        "line": 5,
                        "column": 4
                    }
                ]
            }

        Success (no definition found):
            {
                "status": "success",
                "definitions": []
            }

        Error:
            {
                "status": "error",
                "error_code": "file_not_found" | "validation_error" | ...,
                "message": "Human-readable error message"
            }

    Example:
        >>> result = await go_to_definition("/path/to/file.py", line=10, column=5)
        >>> if result["status"] == "success" and result["definitions"]:
        ...     defn = result["definitions"][0]
        ...     print(f"Defined at {defn['file']}:{defn['line']}")
    """
    start_time = time.time()
    success = False
    context = None

    logger.info(f"go_to_definition called: file={file}, line={line}, column={column}")

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

    # Step 4: Get definition backend and execute
    try:
        selector = get_selector()
        backend = await selector.get_definition_backend(validated_path)
        result = await backend.definition(
            validated_path,
            line_0,
            column_0,
            project_root=context.root,
        )
        success = True
        logger.info(f"Definition complete: {len(result.definitions)} location(s) found")
        return result.to_dict()

    except BackendError as e:
        logger.error(f"Backend error: {e.error_code} - {e.message}")
        return {
            "status": "error",
            "error_code": e.error_code,
            "message": e.message,
        }
    except Exception as e:
        logger.error(f"Unexpected error during definition: {e}", exc_info=True)
        return {
            "status": "error",
            "error_code": "execution_error",
            "message": f"Unexpected error during definition: {e}",
        }
    finally:
        # Record metrics
        duration_ms = (time.time() - start_time) * 1000
        if context:
            metrics_collector = get_metrics_collector()
            await metrics_collector.record(
                workspace_root=context.root,
                operation="definition",
                duration_ms=duration_ms,
                success=success,
            )
