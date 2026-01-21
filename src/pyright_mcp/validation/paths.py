"""Path validation and workspace restriction."""

from pathlib import Path


class ValidationError(Exception):
    """Base exception for validation errors."""

    def __init__(self, field: str, message: str) -> None:
        """Initialize validation error.

        Args:
            field: The field that failed validation
            message: Description of what went wrong
        """
        super().__init__(message)
        self.field = field
        self.message = message

    def to_error_response(self) -> dict[str, str]:
        """Convert to MCP-compatible error response.

        Returns:
            Error dict with status, error_code, and message fields
        """
        return {
            "status": "error",
            "error_code": "validation_error",
            "message": f"{self.field}: {self.message}",
        }


def validate_path(
    path: str | Path,
    *,
    allowed_paths: list[Path] | None = None,
) -> Path:
    """Validate and normalize a path for security and correctness.

    Args:
        path: Path to validate (can be relative or absolute)
        allowed_paths: List of allowed parent paths. If None, all paths allowed.

    Returns:
        Normalized absolute Path object

    Raises:
        ValidationError: If path is invalid or not allowed

    Security:
        - Resolves symlinks to prevent directory traversal attacks
        - Validates path is within allowed directories
        - Ensures path exists
    """
    try:
        # Normalize to absolute path and resolve symlinks
        normalized = Path(path).resolve()
    except (OSError, RuntimeError) as e:
        raise ValidationError("path", f"Failed to resolve path: {e}") from e

    # Check if path exists
    if not normalized.exists():
        raise ValidationError("path", f"Path does not exist: {normalized}")

    # Check workspace restriction if configured
    if allowed_paths is not None and not is_path_allowed(normalized, allowed_paths):
        allowed_str = ", ".join(str(p) for p in allowed_paths)
        raise ValidationError(
            "path",
            f"Path not in allowed workspace: {normalized}. "
            f"Allowed paths: {allowed_str}",
        )

    return normalized


def is_path_allowed(path: Path, allowed_paths: list[Path]) -> bool:
    """Check if path is within any allowed parent path.

    Args:
        path: Path to check (should be absolute and resolved)
        allowed_paths: List of allowed parent paths

    Returns:
        True if path is under any allowed path, False otherwise

    Security:
        - Uses relative_to() which is safe against directory traversal
        - Assumes path is already resolved (symlinks resolved)
    """
    # Ensure path is resolved (in case caller didn't)
    path = path.resolve()

    for allowed_root in allowed_paths:
        allowed_root = allowed_root.resolve()
        try:
            # If path is under allowed_root, relative_to succeeds
            path.relative_to(allowed_root)
            return True
        except ValueError:
            # Path is not under this allowed_root, try next
            continue

    return False
