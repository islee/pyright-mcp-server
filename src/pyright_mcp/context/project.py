"""Project context detection and configuration."""

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path

from ..logging_config import get_logger

logger = get_logger("context.project")


@dataclass
class ProjectContext:
    """Detected project configuration.

    Attributes:
        root: Project root directory
        config_file: pyrightconfig.json or pyproject.toml path if found
        venv_path: Virtual environment path if detected
        python_version: Python version if detected from config
    """

    root: Path
    config_file: Path | None = None
    venv_path: Path | None = None
    python_version: str | None = None


async def detect_project(path: Path) -> ProjectContext:
    """
    Detect project context from a target file or directory.

    Detection order:
    1. Walk up from target_path looking for config files
    2. Find venv in project root
    3. Extract Python version from config if present

    Note: Made async in Phase 1 to prepare for Phase 2 workspace indexing
    and I/O-heavy operations (e.g., scanning large directories, reading
    multiple config files in parallel).

    Args:
        path: Target file or directory to start detection from

    Returns:
        ProjectContext with detected values
    """
    # Run sync file operations in thread pool to avoid blocking event loop
    return await asyncio.to_thread(_detect_project_sync, path)


def _detect_project_sync(path: Path) -> ProjectContext:
    """
    Synchronous implementation of project detection.

    This is called via asyncio.to_thread() to avoid blocking the event loop
    during file I/O operations.

    Args:
        path: Target file or directory to start detection from

    Returns:
        ProjectContext with detected values
    """
    # Resolve to absolute path
    path = path.resolve()

    # If path is a file, start from its parent directory
    start_path = path if path.is_dir() else path.parent

    logger.debug(f"Detecting project context from: {start_path}")

    # Find project root and config file
    config_file = find_config_file(start_path)

    if config_file is not None:
        root = config_file.parent
        logger.info(f"Found project root: {root} (config: {config_file.name})")
    else:
        # No config found, use the start path as root
        root = start_path
        logger.debug(f"No config found, using path as root: {root}")

    # Detect virtual environment
    venv_path = detect_venv(root)
    if venv_path:
        logger.info(f"Detected virtual environment: {venv_path}")

    # Extract Python version from config
    python_version = None
    if config_file is not None:
        python_version = extract_python_version(config_file)
        if python_version:
            logger.info(f"Detected Python version from config: {python_version}")

    return ProjectContext(
        root=root,
        config_file=config_file,
        venv_path=venv_path,
        python_version=python_version,
    )


def find_config_file(directory: Path) -> Path | None:
    """
    Find Pyright configuration file by walking up directory tree.

    Searches for (in priority order):
    1. pyrightconfig.json (highest priority)
    2. pyproject.toml with [tool.pyright] section

    Args:
        directory: Directory to start search from

    Returns:
        Path to config file if found, None otherwise
    """
    current = directory.resolve()

    # Walk up directory tree until we hit the root
    while True:
        # Check for pyrightconfig.json first (highest priority)
        pyright_config = current / "pyrightconfig.json"
        if pyright_config.is_file():
            logger.debug(f"Found pyrightconfig.json at: {pyright_config}")
            return pyright_config

        # Check for pyproject.toml with [tool.pyright] section
        pyproject = current / "pyproject.toml"
        if pyproject.is_file():
            try:
                content = pyproject.read_text(encoding="utf-8")
                # Use proper TOML parsing to check for [tool.pyright] section
                try:
                    import tomllib
                except ImportError:
                    import tomli as tomllib  # type: ignore[import-not-found]

                data = tomllib.loads(content)
                if "tool" in data and "pyright" in data["tool"]:
                    logger.debug(f"Found pyproject.toml with [tool.pyright] at: {pyproject}")
                    return pyproject
            except (OSError, UnicodeDecodeError) as e:
                logger.warning(f"Failed to read {pyproject}: {e}")
            except Exception as e:
                logger.debug(f"Failed to parse {pyproject}: {e}")

        # Check if we've reached the filesystem root
        parent = current.parent
        if parent == current:
            # We've reached the root, stop searching
            break

        current = parent

    logger.debug("No config file found")
    return None


def detect_venv(directory: Path) -> Path | None:
    """
    Detect virtual environment for project.

    Checks (in order):
    1. VIRTUAL_ENV environment variable
    2. .venv/ directory in project root
    3. venv/ directory in project root

    Validates that venv has python executable.

    Args:
        directory: Project root directory to search

    Returns:
        Path to virtual environment if found and valid, None otherwise
    """
    # Check VIRTUAL_ENV environment variable first
    if venv_env := os.getenv("VIRTUAL_ENV"):
        venv_path = Path(venv_env).resolve()
        if _is_valid_venv(venv_path):
            logger.debug(f"Using venv from VIRTUAL_ENV: {venv_path}")
            return venv_path
        logger.warning(f"VIRTUAL_ENV points to invalid venv: {venv_path}")

    # Check for .venv directory (common convention)
    venv_path = directory / ".venv"
    if venv_path.is_dir() and _is_valid_venv(venv_path):
        logger.debug(f"Found .venv directory: {venv_path}")
        return venv_path

    # Check for venv directory
    venv_path = directory / "venv"
    if venv_path.is_dir() and _is_valid_venv(venv_path):
        logger.debug(f"Found venv directory: {venv_path}")
        return venv_path

    logger.debug("No virtual environment found")
    return None


def _is_valid_venv(venv_path: Path) -> bool:
    """
    Validate that a path is a valid virtual environment.

    Checks for presence of Python executable in expected locations.

    Args:
        venv_path: Path to potential virtual environment

    Returns:
        True if valid venv, False otherwise
    """
    # Check for python executable in bin/ (Unix) or Scripts/ (Windows)
    bin_dir = venv_path / "bin"
    scripts_dir = venv_path / "Scripts"

    python_paths = [
        bin_dir / "python",
        bin_dir / "python3",
        scripts_dir / "python.exe",
        scripts_dir / "python3.exe",
    ]

    for python_path in python_paths:
        if python_path.is_file():
            return True

    return False


def extract_python_version(config_file: Path) -> str | None:
    """
    Extract Python version from configuration file.

    Supports:
    - pyrightconfig.json: "pythonVersion" field
    - pyproject.toml: pythonVersion under [tool.pyright]

    Args:
        config_file: Path to pyrightconfig.json or pyproject.toml

    Returns:
        Python version string (e.g., "3.10") if found, None otherwise
    """
    try:
        if config_file.name == "pyrightconfig.json":
            return _extract_version_from_pyrightconfig(config_file)
        if config_file.name == "pyproject.toml":
            return _extract_version_from_pyproject(config_file)
        logger.warning(f"Unknown config file type: {config_file.name}")
        return None
    except Exception as e:
        logger.warning(f"Failed to extract Python version from {config_file}: {e}")
        return None


def _extract_version_from_pyrightconfig(config_file: Path) -> str | None:
    """Extract pythonVersion from pyrightconfig.json."""
    try:
        content = config_file.read_text(encoding="utf-8")
        config = json.loads(content)

        if "pythonVersion" in config:
            version = config["pythonVersion"]
            logger.debug(f"Found pythonVersion in pyrightconfig.json: {version}")
            return str(version)

        return None
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        logger.warning(f"Failed to parse pyrightconfig.json: {e}")
        return None


def _extract_version_from_pyproject(config_file: Path) -> str | None:
    """Extract pythonVersion from pyproject.toml [tool.pyright] section."""
    try:
        content = config_file.read_text(encoding="utf-8")

        # Use tomllib (Python 3.11+) or tomli (fallback)
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[import-not-found]

        data = tomllib.loads(content)
        pyright_config = data.get("tool", {}).get("pyright", {})

        if "pythonVersion" in pyright_config:
            version = str(pyright_config["pythonVersion"])
            logger.debug(f"Found pythonVersion in pyproject.toml: {version}")
            return version

        return None
    except Exception as e:
        logger.warning(f"Failed to parse pyproject.toml: {e}")
        return None
