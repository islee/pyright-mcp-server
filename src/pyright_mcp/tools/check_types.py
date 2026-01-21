"""Type checking tool implementation.

This module provides the check_types MCP tool, which analyzes Python files
for type errors using Pyright.
"""

from typing import Any

from ..backends.base import BackendError
from ..backends.cli_runner import PyrightCLIRunner
from ..config import get_config
from ..context.project import detect_project
from ..logging_config import get_logger
from ..validation import ValidationError, validate_check_types_input, validate_path

logger = get_logger("tools.check_types")


async def check_types(path: str, python_version: str | None = None) -> dict[str, Any]:
    """
    Check Python files for type errors using Pyright.

    Analyzes the specified file or directory for type errors and returns
    structured diagnostics with file locations, severity levels, and messages.

    Args:
        path: Absolute path to file or directory to check
        python_version: Python version to target (e.g., "3.11"). Auto-detected if not specified.

    Returns:
        Discriminated union dict with status field:

        Success:
            {
                "status": "success",
                "summary": "Analyzed 5 files in 0.45s. Found 1 error(s).",
                "files_analyzed": 5,
                "error_count": 1,
                "warning_count": 0,
                "information_count": 0,
                "hint_count": 0,
                "diagnostics": [
                    {
                        "file": "/path/to/file.py",
                        "location": "10:5",  # 1-indexed for human readability
                        "severity": "error",
                        "message": "Argument of type 'str' cannot be assigned...",
                        "rule": "reportArgumentType"
                    }
                ]
            }

        Error:
            {
                "status": "error",
                "error_code": "file_not_found" | "timeout" | "parse_error" | "validation_error" | "path_not_allowed",
                "message": "Human-readable error message"
            }

    Example:
        >>> result = await check_types("/path/to/project/src")
        >>> if result["status"] == "success":
        ...     print(f"Found {result['error_count']} errors")
    """
    logger.info(f"check_types called with path: {path}")

    # Step 1: Validate input
    try:
        validated_path = validate_check_types_input(path)
    except ValidationError as e:
        logger.warning(f"Input validation failed: {e}")
        return e.to_error_response()

    # Step 2: Validate path against allowed_paths
    config = get_config()
    try:
        validated_path = validate_path(validated_path, allowed_paths=config.allowed_paths)
    except ValidationError as e:
        logger.warning(f"Path validation failed: {e}")
        return e.to_error_response()

    # Step 3: Detect project context
    try:
        context = await detect_project(validated_path)
        logger.debug(
            f"Project context detected: root={context.root}, "
            f"config={context.config_file}, venv={context.venv_path}"
        )
    except Exception as e:
        logger.error(f"Failed to detect project context: {e}", exc_info=True)
        return {
            "status": "error",
            "error_code": "execution_error",
            "message": f"Failed to detect project context: {e}",
        }

    # Step 4: Run type check
    try:
        runner = PyrightCLIRunner(config)
        result = await runner.check(
            validated_path, project_root=context.root, python_version=python_version
        )
        logger.info(
            f"Type check complete: {result.files_analyzed} files, "
            f"{len(result.diagnostics)} diagnostics"
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
        logger.error(f"Unexpected error during type check: {e}", exc_info=True)
        return {
            "status": "error",
            "error_code": "execution_error",
            "message": f"Unexpected error during type check: {e}",
        }
