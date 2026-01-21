"""Input validation for MCP tool parameters."""

from pathlib import Path

from .paths import ValidationError, validate_path


def validate_check_types_input(path: str | None) -> Path:
    """Validate path parameter for check_types tool.

    Args:
        path: File or directory path to type check

    Returns:
        Normalized absolute Path object

    Raises:
        ValidationError: If path is None, empty, or invalid

    Note:
        Does not enforce allowed_paths here - that's done at tool layer
        with config. This validates basic input structure only.
    """
    if path is None:
        raise ValidationError("path", "path parameter is required")

    if not path.strip():
        raise ValidationError("path", "path parameter cannot be empty")

    # Validate path exists and normalize
    # Note: allowed_paths enforcement happens at tool layer
    return validate_path(path)
