"""Path and URI conversion utilities.

Handles conversion between filesystem paths and file:// URIs, with proper
handling of platform differences (Windows drive letters, URL encoding, etc.).
"""

import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlparse


def path_to_uri(path: Path) -> str:
    """Convert filesystem path to file:// URI.

    Handles platform differences:
    - Unix: file:///path/to/file
    - Windows: file:///C:/path/to/file

    Args:
        path: Filesystem path to convert

    Returns:
        file:// URI string with proper URL encoding

    Example:
        >>> path = Path("/home/user/project/file.py")
        >>> uri = path_to_uri(path)
        >>> uri.startswith("file://")
        True
    """
    path = path.resolve()

    if sys.platform == "win32":
        # Windows: file:///C:/path/to/file
        # Keep forward slashes and colons unencoded
        return f"file:///{quote(str(path), safe='/:')}"
    # Unix: file:///path/to/file
    # Keep forward slashes unencoded
    return f"file://{quote(str(path), safe='/')}"


def uri_to_path(uri: str) -> Path:
    """Convert file:// URI to filesystem path.

    Handles URL decoding and platform-specific path formats.

    Args:
        uri: file:// URI string

    Returns:
        Path object representing the filesystem path

    Raises:
        ValueError: If URI is not a file:// URI

    Example:
        >>> uri = "file:///home/user/project/file.py"
        >>> path = uri_to_path(uri)
        >>> path == Path("/home/user/project/file.py")
        True
    """
    parsed = urlparse(uri)

    if parsed.scheme != "file":
        raise ValueError(f"Expected file:// URI, got: {uri}")

    path_str = unquote(parsed.path)

    # Handle Windows drive letters (e.g., /C:/path -> C:/path)
    if sys.platform == "win32" and path_str.startswith("/") and len(path_str) > 2 and path_str[2] == ":":
        path_str = path_str[1:]

    return Path(path_str)


def normalize_path(path: str | Path) -> Path:
    """Normalize a path for consistent handling.

    Normalization includes:
    - Converting to absolute path
    - Resolving symlinks
    - Normalizing path separators

    Args:
        path: String or Path object to normalize

    Returns:
        Normalized absolute Path

    Example:
        >>> path = normalize_path("relative/path.py")
        >>> path.is_absolute()
        True
    """
    return Path(path).resolve()
