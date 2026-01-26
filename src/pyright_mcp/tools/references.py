"""Implementation of find_references tool."""

import time
from pathlib import Path
from typing import Any

from ..backends.selector import get_selector
from ..context.project import detect_project
from ..logging_config import get_logger
from ..validation.inputs import validate_position_input

logger = get_logger("tools.references")

# Global metrics collector (set by server)
_metrics_collector: Any = None


def set_metrics_collector(collector: Any) -> None:
    """Set global metrics collector.

    Args:
        collector: MetricsCollector instance
    """
    global _metrics_collector
    _metrics_collector = collector


async def find_references(
    file: str,
    line: int,
    column: int,
    include_declaration: bool = True,
) -> dict[str, Any]:
    """Find all references to a symbol at a position.

    Args:
        file: Absolute path to Python file
        line: Line number (1-indexed)
        column: Column number (1-indexed)
        include_declaration: Include declaration in results (default True)

    Returns:
        Dictionary with status and references
        - status: "success" or "error"
        - references: List of reference locations (if success)
        - count: Number of references (if success)
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

        # Get references backend
        selector = get_selector()
        backend = await selector.get_references_backend(file_path)

        # Call references
        result = await backend.references(
            file=file_path,
            line=line_0indexed,
            column=column_0indexed,
            project_root=context.root,
            include_declaration=include_declaration,
        )

        success = True
        return result.to_dict()

    except ValueError as e:
        logger.warning(f"Validation error in find_references: {e}")
        return {
            "status": "error",
            "error_code": "validation_error",
            "message": str(e),
        }
    except Exception as e:
        logger.error(f"References request failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error_code": "execution_error",
            "message": f"References request failed: {e}",
        }
    finally:
        # Record metrics
        duration_ms = (time.time() - start_time) * 1000
        if context and _metrics_collector:
            await _metrics_collector.record(
                workspace_root=context.root,
                operation="references",
                duration_ms=duration_ms,
                success=success,
            )
