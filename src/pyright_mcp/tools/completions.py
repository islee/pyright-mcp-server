"""Implementation of get_completions tool."""

import time
from pathlib import Path
from typing import Any

from ..backends.selector import get_selector
from ..context.project import detect_project
from ..logging_config import get_logger
from ..metrics import get_metrics_collector
from ..validation.inputs import validate_position_input

logger = get_logger("tools.completions")


async def get_completions(
    file: str,
    line: int,
    column: int,
    trigger_character: str | None = None,
) -> dict[str, Any]:
    """Get code completion suggestions at a position.

    Args:
        file: Absolute path to Python file
        line: Line number (1-indexed)
        column: Column number (1-indexed)
        trigger_character: Optional trigger character (e.g., ".", "(")

    Returns:
        Dictionary with status and completion items
        - status: "success" or "error"
        - items: List of completion suggestions (if success)
        - error_code: Error code (if error)
        - message: Error message (if error)

    Raises:
        ValueError: If inputs are invalid
    """
    start_time = time.time()
    success = False
    context = None

    try:
        # Validate inputs
        file_path = Path(file)
        line_0indexed, column_0indexed = validate_position_input(
            file_path, line, column, must_exist=True
        )

        # Detect project context
        context = await detect_project(file_path)

        # Get completion backend
        selector = get_selector()
        backend = await selector.get_completion_backend(file_path)

        # Call completion
        result = await backend.complete(
            file=file_path,
            line=line_0indexed,
            column=column_0indexed,
            project_root=context.root,
            trigger_character=trigger_character,
        )

        success = True
        return result.to_dict()

    except ValueError as e:
        logger.warning(f"Validation error in get_completions: {e}")
        return {
            "status": "error",
            "error_code": "validation_error",
            "message": str(e),
        }
    except Exception as e:
        logger.error(f"Completions request failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error_code": "execution_error",
            "message": f"Completions request failed: {e}",
        }
    finally:
        # Record metrics
        duration_ms = (time.time() - start_time) * 1000
        if context:
            metrics_collector = get_metrics_collector()
            await metrics_collector.record(
                workspace_root=context.root,
                operation="completion",
                duration_ms=duration_ms,
                success=success,
            )
