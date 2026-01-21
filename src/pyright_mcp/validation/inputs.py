"""Input validation for MCP tool parameters."""

from pathlib import Path

from .paths import ValidationError, validate_path


def validate_position_input(
    file: str | None,
    line: int | None,
    column: int | None,
) -> tuple[Path, int, int]:
    """Validate position input parameters.

    Args:
        file: File path (must be absolute)
        line: 1-indexed line number
        column: 1-indexed column number

    Returns:
        Tuple of (validated_path, 0-indexed line, 0-indexed column)

    Raises:
        ValidationError: If any input is invalid
    """
    # Validate file path
    if file is None:
        raise ValidationError("file", "file parameter is required")
    if not file.strip():
        raise ValidationError("file", "file parameter cannot be empty")

    # Validate line
    if line is None:
        raise ValidationError("line", "line parameter is required")
    if line < 1:
        raise ValidationError("line", f"line must be >= 1, got {line}")

    # Validate column
    if column is None:
        raise ValidationError("column", "column parameter is required")
    if column < 1:
        raise ValidationError("column", f"column must be >= 1, got {column}")

    # Validate path exists and normalize
    validated_path = validate_path(file)

    # Convert 1-indexed to 0-indexed
    line_0 = line - 1
    column_0 = column - 1

    return validated_path, line_0, column_0


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
