# Implementation Plan: Phase 1 MVP

## Overview

Phase 1 delivers a working `check_types` MCP tool that Claude Code can use to verify Python code has no type errors.

**References:**
- [PRD](./PRD.md) - Product requirements and user stories
- [TDD](./TDD.md) - Technical design decisions and architecture

---

## File Structure

```
pyright-mcp/
├── src/
│   └── pyright_mcp/
│       ├── __init__.py
│       ├── __main__.py              # Entry point (initializes logging)
│       ├── server.py                # FastMCP server setup
│       ├── config.py                # Configuration management
│       ├── logging_config.py        # Logging configuration (TDD 8.2)
│       ├── context/                 # Project context detection (TDD 5.2)
│       │   ├── __init__.py
│       │   └── project.py           # ProjectContext, detect_project()
│       ├── utils/
│       │   ├── __init__.py
│       │   ├── position.py          # Position/Range utilities (TDD 4.1)
│       │   └── uri.py               # Path/URI conversion (TDD 4.2)
│       ├── validation/              # Input validation and security
│       │   ├── __init__.py
│       │   ├── paths.py             # Path validation and normalization
│       │   └── inputs.py            # Input parameter validation
│       ├── backends/
│       │   ├── __init__.py
│       │   ├── base.py              # BackendError, PyrightBackend protocol (TDD 5.3)
│       │   └── cli_runner.py        # Pyright CLI wrapper (TDD 5.4)
│       └── tools/
│           ├── __init__.py
│           ├── check_types.py       # check_types tool (TDD 5.8)
│           └── health_check.py      # Health check tool
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_project_detection.py
│   │   ├── test_cli_runner.py
│   │   ├── test_position.py
│   │   └── test_uri.py              # URI utility tests
│   ├── integration/
│   │   ├── __init__.py
│   │   └── test_check_types.py
│   └── fixtures/
│       ├── valid_project/
│       │   ├── pyproject.toml
│       │   └── src/example.py
│       └── sample_files/
│           ├── valid.py
│           ├── with_errors.py
│           └── syntax_error.py
├── pyproject.toml
├── README.md
└── docs/
    ├── PRD.md
    ├── TDD.md
    └── IMPLEMENTATION.md
```

---

## Implementation Steps

### Step 1: Project Setup

**pyproject.toml:**
```toml
[project]
name = "pyright-mcp"
version = "0.1.0"
description = "MCP server for Pyright type checking - Claude Code companion"
requires-python = ">=3.10"
dependencies = [
    "mcp>=1.1.0",
    "pyright>=1.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pyright_mcp"]

[tool.pyright]
pythonVersion = "3.10"
typeCheckingMode = "strict"

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Note:** The `mcp[cli]` extra is deprecated. Use `mcp>=1.1.0` directly.

**Commands:**
```bash
uv init
uv add mcp pyright
uv add --dev pytest pytest-asyncio ruff
```

---

### Step 2: Utility Modules (TDD Section 4)

**src/pyright_mcp/utils/__init__.py:**
```python
"""Utility modules for pyright-mcp."""

from .position import Position, Range
from .uri import path_to_uri, uri_to_path, normalize_path

__all__ = ["Position", "Range", "path_to_uri", "uri_to_path", "normalize_path"]
```

**src/pyright_mcp/utils/position.py:** (TDD 4.1)
```python
"""Position and range utilities with 0-indexed internal representation."""

from dataclasses import dataclass


@dataclass
class Position:
    """A 0-indexed position in a file."""
    line: int    # 0-indexed
    column: int  # 0-indexed

    def to_display(self) -> str:
        """Convert to 1-indexed human-readable format."""
        return f"{self.line + 1}:{self.column + 1}"

    @classmethod
    def from_lsp(cls, lsp_position: dict) -> "Position":
        """Create from LSP position dict."""
        return cls(line=lsp_position["line"], column=lsp_position["character"])

    def to_lsp(self) -> dict:
        """Convert to LSP position dict."""
        return {"line": self.line, "character": self.column}


@dataclass
class Range:
    """A 0-indexed range in a file."""
    start: Position
    end: Position

    def to_display(self) -> str:
        """Convert to human-readable format."""
        return f"{self.start.to_display()}-{self.end.to_display()}"

    @classmethod
    def from_lsp(cls, lsp_range: dict) -> "Range":
        """Create from LSP range dict."""
        return cls(
            start=Position.from_lsp(lsp_range["start"]),
            end=Position.from_lsp(lsp_range["end"]),
        )

    def to_lsp(self) -> dict:
        """Convert to LSP range dict."""
        return {"start": self.start.to_lsp(), "end": self.end.to_lsp()}
```

**src/pyright_mcp/utils/uri.py:** (TDD 4.2)
```python
"""Path and URI conversion utilities."""

from pathlib import Path
from urllib.parse import quote, unquote, urlparse
import sys


def path_to_uri(path: Path) -> str:
    """
    Convert filesystem path to file:// URI.

    Handles platform differences (Windows drive letters, etc.)
    """
    path = path.resolve()
    if sys.platform == "win32":
        # Windows: file:///C:/path/to/file
        return f"file:///{quote(str(path), safe='/:')}"
    else:
        # Unix: file:///path/to/file
        return f"file://{quote(str(path), safe='/')}"


def uri_to_path(uri: str) -> Path:
    """
    Convert file:// URI to filesystem path.

    Raises ValueError if URI is not a file:// URI.
    """
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"Expected file:// URI, got: {uri}")

    path_str = unquote(parsed.path)

    # Handle Windows drive letters (e.g., /C:/path)
    if sys.platform == "win32" and path_str.startswith("/") and len(path_str) > 2 and path_str[2] == ":":
        path_str = path_str[1:]

    return Path(path_str)


def normalize_path(path: str | Path) -> Path:
    """
    Normalize a path for consistent handling.

    - Resolves to absolute path
    - Resolves symlinks
    - Normalizes separators
    """
    return Path(path).resolve()
```

---

### Step 2.5: Configuration Module

**src/pyright_mcp/config.py:**
```python
"""Configuration management for pyright-mcp."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os


@dataclass
class Config:
    """Server configuration loaded from environment variables."""
    allowed_paths: list[Path] = field(default_factory=list)
    cli_timeout: float = 30.0
    lsp_timeout: float = 300.0
    lsp_command: list[str] = field(default_factory=lambda: ["pyright-langserver", "--stdio"])
    log_mode: str = "stderr"
    log_level: str = "INFO"
    enable_health_check: bool = True


_config: Config | None = None


def load_config() -> Config:
    """Load configuration from environment variables."""
    global _config
    if _config is not None:
        return _config

    allowed_paths_str = os.getenv("PYRIGHT_MCP_ALLOWED_PATHS", "*")
    if allowed_paths_str == "*":
        allowed_paths = []
    else:
        allowed_paths = [Path(p.strip()).resolve() for p in allowed_paths_str.split(",") if p.strip()]

    _config = Config(
        allowed_paths=allowed_paths,
        cli_timeout=float(os.getenv("PYRIGHT_MCP_CLI_TIMEOUT", "30")),
        lsp_timeout=float(os.getenv("PYRIGHT_MCP_LSP_TIMEOUT", "300")),
        lsp_command=os.getenv("PYRIGHT_MCP_LSP_COMMAND", "pyright-langserver --stdio").split(),
        log_mode=os.getenv("PYRIGHT_MCP_LOG_MODE", "stderr"),
        log_level=os.getenv("PYRIGHT_MCP_LOG_LEVEL", "INFO"),
        enable_health_check=os.getenv("PYRIGHT_MCP_ENABLE_HEALTH_CHECK", "true").lower() == "true",
    )
    return _config


def get_config() -> Config:
    """Get current configuration."""
    return load_config()
```

---

### Step 3: Logging Configuration (TDD Section 8.2)

**src/pyright_mcp/logging_config.py:**
```python
"""Logging configuration with dual-mode support."""

import logging
import json
import os
import sys
from datetime import datetime, timezone
from enum import Enum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from contextvars import ContextVar

# Request ID for correlation across async operations
request_id_ctx: ContextVar[str | None] = ContextVar('request_id', default=None)


class LogMode(Enum):
    STDERR = 'stderr'  # JSON to stderr (production)
    FILE = 'file'      # Human-readable to file (development)
    BOTH = 'both'      # Both modes simultaneously


class JSONFormatter(logging.Formatter):
    """Format log records as JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }

        if request_id := request_id_ctx.get():
            log_obj['request_id'] = request_id

        # Include extra fields if present
        for attr in ('path', 'command', 'duration', 'tool_name'):
            if hasattr(record, attr):
                log_obj[attr] = getattr(record, attr)

        if record.exc_info:
            log_obj['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


def setup_logging(
    level: str | None = None,
    mode: LogMode | None = None,
) -> None:
    """Configure logging based on environment and mode."""
    level = level or os.getenv('PYRIGHT_MCP_LOG_LEVEL', 'INFO')
    if mode is None:
        mode_str = os.getenv('PYRIGHT_MCP_LOG_MODE', 'stderr').lower()
        mode = LogMode(mode_str)

    root_logger = logging.getLogger('pyright_mcp')
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    human_formatter = logging.Formatter(
        '%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Stderr JSON logging (for stderr/both modes)
    if mode in (LogMode.STDERR, LogMode.BOTH):
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(stderr_handler)

    # File logging (for file/both modes)
    if mode in (LogMode.FILE, LogMode.BOTH):
        log_dir = _get_log_directory()
        log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        log_file = log_dir / f'pyright-mcp-{timestamp}.log'

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(human_formatter)
        root_logger.addHandler(file_handler)

        # Symlink to current.log for easy tailing
        current_link = log_dir / 'current.log'
        if current_link.exists() or current_link.is_symlink():
            current_link.unlink()
        current_link.symlink_to(log_file.name)

    # For file-only mode, also log errors to stderr
    if mode == LogMode.FILE:
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.ERROR)
        stderr_handler.setFormatter(human_formatter)
        root_logger.addHandler(stderr_handler)

    root_logger.info(f'Logging initialized (mode={mode.value}, level={level})')


def _get_log_directory() -> Path:
    """Get platform-appropriate log directory."""
    if sys.platform == 'win32':
        return Path.home() / 'AppData' / 'Local' / 'pyright-mcp' / 'logs'
    return Path.home() / '.pyright-mcp' / 'logs'


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the pyright_mcp prefix."""
    return logging.getLogger(f'pyright_mcp.{name}')
```

---

### Step 3.5: Validation Module

**src/pyright_mcp/validation/__init__.py:**
```python
"""Input validation and security utilities."""

from .paths import validate_path, is_path_allowed
from .inputs import validate_file_path, validate_python_version

__all__ = ["validate_path", "is_path_allowed", "validate_file_path", "validate_python_version"]
```

**src/pyright_mcp/validation/paths.py:**
```python
"""Path validation and normalization."""

from pathlib import Path
from typing import Optional

from ..config import get_config
from ..logging_config import get_logger

logger = get_logger('validation.paths')


def validate_path(path: str | Path) -> Path:
    """
    Validate and normalize a file path.

    Raises ValueError if:
    - Path contains suspicious patterns (../)
    - Path is not allowed (if allowed_paths configured)

    Returns normalized absolute Path.
    """
    path_obj = Path(path).resolve()

    # Check for path traversal attempts
    if ".." in path_obj.parts:
        raise ValueError(f"Path traversal detected: {path}")

    # Check against allowed paths if configured
    if not is_path_allowed(path_obj):
        raise ValueError(f"Path not in allowed list: {path}")

    return path_obj


def is_path_allowed(path: Path) -> bool:
    """Check if path is within allowed paths (if configured)."""
    config = get_config()

    # Empty allowed_paths list means all paths allowed
    if not config.allowed_paths:
        return True

    # Check if path is within any allowed directory
    for allowed in config.allowed_paths:
        try:
            path.relative_to(allowed)
            return True
        except ValueError:
            continue

    return False
```

**src/pyright_mcp/validation/inputs.py:**
```python
"""Input parameter validation."""

from pathlib import Path
import re

from .paths import validate_path
from ..logging_config import get_logger

logger = get_logger('validation.inputs')


def validate_file_path(path: str) -> Path:
    """
    Validate and normalize a file/directory path from tool input.

    Raises ValueError if path is invalid or not allowed.
    """
    if not path:
        raise ValueError("Path cannot be empty")

    if len(path) > 4096:
        raise ValueError("Path too long (max 4096 characters)")

    return validate_path(path)


def validate_python_version(version: str | None) -> str | None:
    """
    Validate Python version string format.

    Accepts formats like: "3.10", "3.11", "3.12"
    Raises ValueError if format is invalid.
    """
    if version is None:
        return None

    if not version.strip():
        raise ValueError("Python version cannot be empty")

    # Validate format: X.Y (e.g., 3.10, 3.11)
    if not re.match(r"^\d+\.\d+$", version.strip()):
        raise ValueError(f"Invalid Python version format: {version}. Use X.Y (e.g., 3.10)")

    return version.strip()
```

---

### Step 3.5: Configuration Module (TDD Section 5.1.1)

**src/pyright_mcp/config.py:**
```python
"""Runtime configuration management."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    """Runtime configuration for pyright-mcp."""
    allowed_paths: list[Path] | None  # Workspace restriction (None = allow all)
    cli_timeout: float                # CLI execution timeout (seconds)
    lsp_timeout: float                # LSP idle timeout (seconds)
    lsp_command: list[str]            # LSP server command
    log_mode: str                     # Logging mode: stderr, file, both
    log_level: str                    # Logging level
    enable_health_check: bool         # Enable health_check tool


_config: Config | None = None


def load_config() -> Config:
    """Load configuration from environment variables."""
    # Parse allowed paths
    allowed_paths = None
    if allowed_paths_str := os.getenv("PYRIGHT_MCP_ALLOWED_PATHS"):
        allowed_paths = [Path(p).resolve() for p in allowed_paths_str.split(":")]

    # Parse LSP command
    lsp_command_str = os.getenv("PYRIGHT_MCP_LSP_COMMAND", "pyright-langserver")
    lsp_command = lsp_command_str.split() if lsp_command_str else ["pyright-langserver", "--stdio"]

    return Config(
        allowed_paths=allowed_paths,
        cli_timeout=float(os.getenv("PYRIGHT_MCP_CLI_TIMEOUT", "30")),
        lsp_timeout=float(os.getenv("PYRIGHT_MCP_LSP_TIMEOUT", "300")),
        lsp_command=lsp_command,
        log_mode=os.getenv("PYRIGHT_MCP_LOG_MODE", "stderr"),
        log_level=os.getenv("PYRIGHT_MCP_LOG_LEVEL", "INFO"),
        enable_health_check=os.getenv("PYRIGHT_MCP_ENABLE_HEALTH_CHECK", "true").lower() == "true",
    )


def get_config() -> Config:
    """Get singleton config instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
```

---

### Step 3.6: Input Validation Module (TDD Section 4.4)

**src/pyright_mcp/validation/__init__.py:**
```python
"""Input validation utilities."""

from .paths import validate_path, is_path_allowed, PathValidationError
from .inputs import validate_position, validate_python_version, InputValidationError

__all__ = [
    "validate_path",
    "is_path_allowed",
    "PathValidationError",
    "validate_position",
    "validate_python_version",
    "InputValidationError",
]
```

**src/pyright_mcp/validation/paths.py:**
```python
"""Path validation and workspace restriction."""

from pathlib import Path

from ..config import get_config
from ..logging_config import get_logger

logger = get_logger('validation.paths')


class PathValidationError(Exception):
    """Raised when a path fails validation."""
    pass


def validate_path(path: Path) -> None:
    """
    Validate a path for security and correctness.

    Raises:
        PathValidationError: If path is invalid or not allowed
    """
    if not path.is_absolute():
        raise PathValidationError(f"Path must be absolute: {path}")

    if not is_path_allowed(path):
        config = get_config()
        allowed = config.allowed_paths or ["(all paths allowed)"]
        raise PathValidationError(
            f"Path not in allowed workspace: {path}\n"
            f"Allowed paths: {', '.join(str(p) for p in allowed)}"
        )


def is_path_allowed(path: Path) -> bool:
    """Check if path is within allowed workspace."""
    config = get_config()

    if config.allowed_paths is None:
        return True

    path = path.resolve()
    for allowed_root in config.allowed_paths:
        try:
            path.relative_to(allowed_root)
            return True
        except ValueError:
            continue

    return False
```

**src/pyright_mcp/validation/inputs.py:**
```python
"""Input validation for MCP tool parameters."""

from typing import Tuple


class InputValidationError(Exception):
    """Raised when input parameters are invalid."""
    pass


def validate_position(line: int, column: int) -> Tuple[int, int]:
    """Validate line and column position."""
    if line < 0:
        raise InputValidationError(f"Line must be >= 0, got: {line}")
    if column < 0:
        raise InputValidationError(f"Column must be >= 0, got: {column}")
    return (line, column)


def validate_python_version(version: str | None) -> str | None:
    """Validate Python version string."""
    if version is None:
        return None

    import re
    if not re.match(r"^\d+\.\d+$", version):
        raise InputValidationError(
            f"Invalid Python version format: {version}. "
            f"Expected format: '3.10', '3.11', etc."
        )

    return version
```

---

### Step 4: Project Detection Module (TDD Section 5.2)

**src/pyright_mcp/context/__init__.py:**
```python
"""Project context detection."""

from .project import ProjectContext, detect_project, find_project_root, find_venv

__all__ = ["ProjectContext", "detect_project", "find_project_root", "find_venv"]
```

**src/pyright_mcp/context/project.py:**
```python
"""Detect Python project root and virtual environment."""

from dataclasses import dataclass
from pathlib import Path
import os

from ..logging_config import get_logger

logger = get_logger('context.project')


@dataclass
class ProjectContext:
    """Detected project configuration."""
    root: Path                    # Project root directory
    venv: Path | None             # Virtual environment path
    pyright_config: Path | None   # pyrightconfig.json path
    pyproject: Path | None        # pyproject.toml path
    python_version: str | None    # Detected Python version


async def detect_project(target_path: Path) -> ProjectContext:
    """
    Detect project context from a target file or directory.

    Detection order:
    1. Walk up from target_path looking for config files
    2. Find venv in project root
    3. Extract Python version from config if present
    """
    root = find_project_root(target_path)
    pyright_config = await _find_pyright_config(root)
    pyproject = root / "pyproject.toml" if (root / "pyproject.toml").exists() else None
    venv = await find_venv(root)
    python_version = await _get_python_version(pyright_config, pyproject)

    context = ProjectContext(
        root=root,
        venv=venv,
        pyright_config=pyright_config,
        pyproject=pyproject,
        python_version=python_version,
    )

    logger.debug(f"Detected project context: root={root}, venv={venv}")
    return context


def find_project_root(start_path: Path) -> Path:
    """
    Find project root by looking for config files.

    Detection order:
    1. pyrightconfig.json
    2. pyproject.toml
    3. Fall back to start_path directory
    """
    current = start_path.resolve()
    if current.is_file():
        current = current.parent

    for directory in [current, *current.parents]:
        # Check for pyrightconfig.json
        if (directory / "pyrightconfig.json").exists():
            return directory
        # Check for pyproject.toml
        if (directory / "pyproject.toml").exists():
            return directory

    return current


async def find_venv(project_root: Path) -> Path | None:
    """
    Find virtual environment for project.

    Detection order:
    1. VIRTUAL_ENV environment variable
    2. .venv/ directory
    3. venv/ directory
    """
    # Check VIRTUAL_ENV
    if venv := os.environ.get("VIRTUAL_ENV"):
        venv_path = Path(venv)
        if venv_path.exists():
            return venv_path

    # Check common venv directories
    for venv_name in [".venv", "venv"]:
        venv_path = project_root / venv_name
        if venv_path.is_dir():
            # Check for bin/python (Unix) or Scripts/python.exe (Windows)
            if (venv_path / "bin" / "python").exists():
                return venv_path
            if (venv_path / "Scripts" / "python.exe").exists():
                return venv_path

    return None


async def _find_pyright_config(project_root: Path) -> Path | None:
    """Find pyrightconfig.json in project root."""
    config_path = project_root / "pyrightconfig.json"
    return config_path if config_path.exists() else None


async def _get_python_version(
    pyright_config: Path | None,
    pyproject: Path | None,
) -> str | None:
    """Extract Python version from project config files."""
    import json
    import tomllib

    # Try pyrightconfig.json first
    if pyright_config:
        try:
            with open(pyright_config) as f:
                config = json.load(f)
                if version := config.get("pythonVersion"):
                    return version
        except (json.JSONDecodeError, OSError):
            pass

    # Try pyproject.toml
    if pyproject:
        try:
            with open(pyproject, "rb") as f:
                config = tomllib.load(f)
                # Check [tool.pyright] section
                if version := config.get("tool", {}).get("pyright", {}).get("pythonVersion"):
                    return version
                # Check requires-python
                if requires := config.get("project", {}).get("requires-python"):
                    # Parse ">=3.10" to "3.10"
                    import re
                    if match := re.search(r"(\d+\.\d+)", requires):
                        return match.group(1)
        except (tomllib.TOMLDecodeError, OSError):
            pass

    return None
```

---

### Step 5: Backend Interface (TDD Section 5.3)

**src/pyright_mcp/backends/base.py:**
```python
"""Backend interface protocol and unified error type."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..context import ProjectContext
    from .cli_runner import DiagnosticsResult


class ErrorCode(str, Enum):
    """Error codes for backend operations."""
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    PARSE_ERROR = "parse_error"
    LSP_CRASH = "lsp_crash"
    INVALID_PATH = "invalid_path"
    PERMISSION_DENIED = "permission_denied"
    CANCELLED = "cancelled"


@dataclass
class BackendError:
    """Unified error type for all backends (CLI and LSP)."""
    code: str  # ErrorCode value: "not_found", "timeout", "parse_error", "lsp_crash", etc.
    message: str
    recoverable: bool = False  # Can operation be retried?

    @classmethod
    def not_found(cls, message: str) -> "BackendError":
        return cls(code=ErrorCode.NOT_FOUND.value, message=message, recoverable=False)

    @classmethod
    def timeout(cls, message: str) -> "BackendError":
        return cls(code=ErrorCode.TIMEOUT.value, message=message, recoverable=True)

    @classmethod
    def parse_error(cls, message: str) -> "BackendError":
        return cls(code=ErrorCode.PARSE_ERROR.value, message=message, recoverable=False)

    @classmethod
    def lsp_crash(cls, message: str) -> "BackendError":
        return cls(code=ErrorCode.LSP_CRASH.value, message=message, recoverable=True)

    @classmethod
    def invalid_path(cls, message: str) -> "BackendError":
        return cls(code=ErrorCode.INVALID_PATH.value, message=message, recoverable=False)

    @classmethod
    def permission_denied(cls, message: str) -> "BackendError":
        return cls(code=ErrorCode.PERMISSION_DENIED.value, message=message, recoverable=False)

    @classmethod
    def cancelled(cls, message: str) -> "BackendError":
        return cls(code=ErrorCode.CANCELLED.value, message=message, recoverable=False)


@runtime_checkable
class PyrightBackend(Protocol):
    """Protocol for Pyright backend implementations."""

    async def check(
        self,
        path: Path,
        context: "ProjectContext",
        python_version: str | None = None,
    ) -> "DiagnosticsResult | BackendError":
        """Run type checking on path."""
        ...

    async def shutdown(self) -> None:
        """Clean up resources."""
        ...
```

---

### Step 6: Pyright CLI Runner (TDD Section 5.4)

**src/pyright_mcp/backends/__init__.py:**
```python
"""Backend adapters for Pyright."""

from .base import BackendError, PyrightBackend
from .cli_runner import run_check, Diagnostic, DiagnosticsResult

__all__ = ["BackendError", "PyrightBackend", "run_check", "Diagnostic", "DiagnosticsResult"]
```

**src/pyright_mcp/backends/cli_runner.py:**
```python
"""Wrapper for invoking Pyright CLI."""

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..context import ProjectContext
from ..utils.position import Position, Range
from ..logging_config import get_logger, request_id_ctx
from .base import BackendError

logger = get_logger('backends.cli_runner')

# Severity mapping from Pyright CLI (integers) to strings
SEVERITY_MAP = {
    1: "error",
    2: "warning",
    3: "information",
}


@dataclass
class Diagnostic:
    """Single diagnostic from Pyright."""
    file: str
    range: Range
    severity: Literal["error", "warning", "information"]
    message: str
    rule: str | None = None

    @property
    def start(self) -> Position:
        """Start position of the diagnostic."""
        return self.range.start

    @property
    def end(self) -> Position:
        """End position of the diagnostic."""
        return self.range.end


@dataclass
class DiagnosticsResult:
    """Result from check_types operation."""
    diagnostics: list[Diagnostic]
    files_analyzed: int
    error_count: int
    warning_count: int
    information_count: int
    time_sec: float


def build_pyright_command(
    path: Path,
    context: ProjectContext,
    python_version: str | None = None,
    output_json: bool = True,
) -> list[str]:
    """
    Build Pyright CLI command with all relevant flags.

    Precedence for options:
    1. Explicit function arguments (highest)
    2. pyrightconfig.json settings
    3. Auto-detected values from ProjectContext (lowest)
    """
    cmd = ["pyright"]

    if output_json:
        cmd.append("--outputjson")

    # Python version: explicit arg > context detection
    version = python_version or context.python_version
    if version:
        cmd.extend(["--pythonversion", version])

    # Virtual environment path
    if context.venv:
        cmd.extend(["--venvpath", str(context.venv.parent)])

    # Project root for config resolution
    if context.root:
        cmd.extend(["--project", str(context.root)])

    # Target path (must be last)
    cmd.append(str(path))

    return cmd


async def run_check(
    path: Path,
    context: ProjectContext,
    python_version: str | None = None,
    timeout: float | None = None,
    cancellation_token: "CancellationToken | None" = None,
) -> DiagnosticsResult | BackendError:
    """
    Run Pyright CLI and return structured diagnostics.

    Invokes: pyright --outputjson [options] <path>

    Args:
        path: Path to file or directory to check
        context: Project context with configuration
        python_version: Python version to target (optional)
        timeout: Timeout in seconds (default from env or 30s)
        cancellation_token: CancellationToken to support cancellation
    """
    # Read timeout from environment variable if not provided
    if timeout is None:
        timeout = float(os.getenv("PYRIGHT_MCP_CLI_TIMEOUT", "30"))
    cmd = build_pyright_command(path, context, python_version)

    logger.debug(
        "Running Pyright",
        extra={"command": " ".join(cmd), "path": str(path)},
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYRIGHT_PYTHON_FORCE_VERSION": "0"},
        )

        # Support cancellation via token
        if cancellation_token:
            cancellation_token.mark_operation(proc.pid)

        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        logger.error(f"Pyright timed out after {timeout}s")
        return BackendError.timeout(f"Pyright timed out after {timeout}s")
    except asyncio.CancelledError:
        proc.kill()
        logger.warning("Pyright check was cancelled")
        return BackendError.cancelled("Check was cancelled by user")
    except FileNotFoundError:
        logger.error("Pyright not found")
        return BackendError.not_found("Pyright not found. Install with: pip install pyright")

    # Log stderr if present
    if stderr:
        stderr_text = stderr.decode().strip()
        if stderr_text:
            logger.debug(f"Pyright stderr: {stderr_text}")

    # Pyright returns non-zero exit code when there are errors, but still outputs JSON
    try:
        result = json.loads(stdout.decode())
    except json.JSONDecodeError as e:
        stderr_text = stderr.decode() if stderr else "No stderr"
        logger.error(f"Failed to parse Pyright output: {e}")
        return BackendError.parse_error(f"Failed to parse Pyright output: {e}\nStderr: {stderr_text}")

    # Parse diagnostics
    diagnostics = []
    for diag in result.get("generalDiagnostics", []):
        range_data = diag.get("range", {})
        start = range_data.get("start", {})
        end = range_data.get("end", {})

        # Convert severity integer to string
        severity_int = diag.get("severity", 1)
        severity = SEVERITY_MAP.get(severity_int, "error")

        diagnostics.append(Diagnostic(
            file=diag.get("file", ""),
            range=Range(
                start=Position(
                    line=start.get("line", 0),
                    column=start.get("character", 0),
                ),
                end=Position(
                    line=end.get("line", 0),
                    column=end.get("character", 0),
                ),
            ),
            severity=severity,
            message=diag.get("message", ""),
            rule=diag.get("rule"),
        ))

    summary = result.get("summary", {})
    return DiagnosticsResult(
        diagnostics=diagnostics,
        files_analyzed=summary.get("filesAnalyzed", 0),
        error_count=summary.get("errorCount", 0),
        warning_count=summary.get("warningCount", 0),
        information_count=summary.get("informationCount", 0),
        time_sec=summary.get("timeInSec", 0.0),
    )
```

---

### Step 7: MCP Tool Implementation (TDD Section 5.8)

**src/pyright_mcp/tools/__init__.py:**
```python
"""MCP tool implementations."""

from .check_types import check_types

__all__ = ["check_types"]
```

**src/pyright_mcp/tools/check_types.py:**
```python
"""check_types MCP tool implementation."""

import time
import uuid
from pathlib import Path

from ..backends import run_check, DiagnosticsResult, BackendError
from ..context import detect_project
from ..utils import normalize_path
from ..logging_config import get_logger, request_id_ctx

logger = get_logger('tools.check_types')


async def check_types(
    path: str,
    python_version: str | None = None,
) -> dict:
    """
    Run Pyright type checking on a file or directory.

    Args:
        path: Absolute path to file or directory to check
        python_version: Python version (e.g., "3.11"). Auto-detected if not specified.

    Returns:
        Discriminated union response with status field:

        Success:
        {
            "status": "success",
            "summary": "Analyzed 5 files in 0.45s. Found 1 error(s).",
            "error_count": 1,
            "warning_count": 0,
            "diagnostics": [...]
        }

        Error:
        {
            "status": "error",
            "error_code": "file_not_found",
            "message": "Path not found: /path/to/file.py"
        }
    """
    # Set request ID for log correlation
    request_id = str(uuid.uuid4())[:8]
    request_id_ctx.set(request_id)

    start_time = time.monotonic()
    logger.info(f"check_types called", extra={"tool_name": "check_types", "path": path})

    try:
        target_path = normalize_path(path)
    except Exception as e:
        return _error_response("invalid_path", f"Invalid path: {e}")

    if not target_path.exists():
        return _error_response("file_not_found", f"Path not found: {path}")

    # Detect project context
    context = detect_project(target_path)

    # Run Pyright
    result = await run_check(
        path=target_path,
        context=context,
        python_version=python_version,
    )

    duration = time.monotonic() - start_time
    logger.info(f"check_types completed", extra={"duration": duration})

    if isinstance(result, BackendError):
        return _error_response(result.code, result.message)

    return _format_result(result)


def _error_response(error_code: str, message: str) -> dict:
    """Format error response with discriminated union pattern (TDD Section 5.8)."""
    return {
        "status": "error",
        "error_code": error_code,
        "message": message,
    }


def _format_result(result: DiagnosticsResult) -> dict:
    """Format DiagnosticsResult with discriminated union pattern."""
    diagnostics = []
    for d in result.diagnostics:
        diagnostics.append({
            "file": d.file,
            "location": d.start.to_display(),  # 1-indexed for human readability
            "severity": d.severity,
            "message": d.message,
            "rule": d.rule,
        })

    # Build summary text
    summary_text = f"Analyzed {result.files_analyzed} files in {result.time_sec:.2f}s. "
    if result.error_count == 0 and result.warning_count == 0:
        summary_text += "No type errors found."
    else:
        parts = []
        if result.error_count > 0:
            parts.append(f"{result.error_count} error(s)")
        if result.warning_count > 0:
            parts.append(f"{result.warning_count} warning(s)")
        summary_text += f"Found {', '.join(parts)}."

    return {
        "status": "success",
        "summary": summary_text,
        "error_count": result.error_count,
        "warning_count": result.warning_count,
        "diagnostics": diagnostics,
    }
```

---

### Step 7.5: Health Check Tool

**src/pyright_mcp/tools/health_check.py:**
```python
"""Health check tool for server status."""

import shutil
from pathlib import Path

from ..config import get_config
from ..logging_config import get_logger

logger = get_logger('tools.health_check')


async def health_check() -> dict:
    """
    Check server health and readiness.

    Returns status information:
    - server_ready: Overall readiness (bool)
    - pyright_available: Whether Pyright CLI is found
    - config_loaded: Whether configuration loaded successfully
    - diagnostics: List of any issues found
    """
    config = get_config()
    diagnostics = []

    # Check Pyright CLI availability
    pyright_available = shutil.which("pyright") is not None
    if not pyright_available:
        diagnostics.append("Pyright CLI not found in PATH")

    # Check configuration
    try:
        _ = get_config()
        config_loaded = True
    except Exception as e:
        config_loaded = False
        diagnostics.append(f"Configuration error: {e}")

    # Check allowed paths if configured
    if config.allowed_paths:
        for path in config.allowed_paths:
            if not path.exists():
                diagnostics.append(f"Configured path does not exist: {path}")

    # Determine overall readiness
    server_ready = pyright_available and config_loaded and len(diagnostics) == 0

    return {
        "status": "healthy" if server_ready else "degraded",
        "server_ready": server_ready,
        "pyright_available": pyright_available,
        "config_loaded": config_loaded,
        "diagnostics": diagnostics,
    }
```

---

### Step 8: MCP Server Setup

**src/pyright_mcp/server.py:**
```python
"""FastMCP server for pyright-mcp."""

from mcp.server.fastmcp import FastMCP

from .tools.check_types import check_types as _check_types

# NOTE: Do NOT initialize logging here at import time.
# Logging is initialized in __main__.py to avoid import side effects.


def create_mcp_server() -> FastMCP:
    """Create and configure the MCP server."""
    mcp = FastMCP("pyright-mcp")

    @mcp.tool()
    async def check_types(
        path: str,
        python_version: str | None = None,
    ) -> dict:
        """
        Run Pyright type checking on a Python file or directory.

        Use this tool to verify Python code has no type errors before suggesting changes.
        Returns diagnostics with file locations, severity, and error messages.

        Args:
            path: Absolute path to the file or directory to check
            python_version: Python version to check against (e.g., "3.11").
                           Auto-detected from project config if not specified.

        Returns:
            Dictionary with status field indicating success or error.
            Success includes summary, error_count, warning_count, diagnostics.
            Error includes error_code and message.
        """
        return await _check_types(path, python_version)

    return mcp
```

**src/pyright_mcp/__main__.py:**
```python
"""Entry point for pyright-mcp server."""

from .logging_config import setup_logging
from .server import create_mcp_server


def main() -> None:
    """Initialize logging and run MCP server."""
    setup_logging()  # Explicit initialization, not at import time
    mcp = create_mcp_server()
    mcp.run()


if __name__ == "__main__":
    main()
```

**src/pyright_mcp/__init__.py:**
```python
"""pyright-mcp: MCP server for Pyright type checking."""

__version__ = "0.1.0"
```

---

### Step 9: Test Fixtures

**tests/fixtures/valid_project/pyproject.toml:**
```toml
[project]
name = "test-project"
version = "0.1.0"
requires-python = ">=3.10"

[tool.pyright]
pythonVersion = "3.10"
```

**tests/fixtures/valid_project/src/example.py:**
```python
"""Example module with valid type hints."""


def add(x: int, y: int) -> int:
    """Add two integers."""
    return x + y


def greet(name: str) -> str:
    """Return a greeting."""
    return f"Hello, {name}!"
```

**tests/fixtures/sample_files/valid.py:**
```python
"""Valid Python file with no type errors."""


def multiply(a: int, b: int) -> int:
    return a * b
```

**tests/fixtures/sample_files/with_errors.py:**
```python
"""Python file with intentional type errors."""


def add(x: int, y: int) -> int:
    return "not an int"  # Type error: return type mismatch


def divide(a: int, b: int) -> float:
    result: str = a / b  # Type error: assigning float to str
    return result
```

**tests/fixtures/sample_files/syntax_error.py:**
```python
"""Python file with syntax error."""

def broken(
    # Missing closing parenthesis and body
```

---

### Step 10: Unit Tests

**tests/unit/__init__.py:**
```python
"""Unit tests for pyright-mcp."""
```

**tests/unit/test_position.py:**
```python
"""Tests for position utilities."""

import pytest

from pyright_mcp.utils.position import Position, Range


class TestPosition:
    def test_to_display_converts_to_1_indexed(self):
        pos = Position(line=0, column=0)
        assert pos.to_display() == "1:1"

        pos = Position(line=10, column=5)
        assert pos.to_display() == "11:6"

    def test_from_lsp(self):
        lsp_pos = {"line": 5, "character": 10}
        pos = Position.from_lsp(lsp_pos)
        assert pos.line == 5
        assert pos.column == 10

    def test_to_lsp(self):
        pos = Position(line=5, column=10)
        lsp_pos = pos.to_lsp()
        assert lsp_pos == {"line": 5, "character": 10}


class TestRange:
    def test_to_display(self):
        range_ = Range(
            start=Position(line=0, column=0),
            end=Position(line=0, column=5),
        )
        assert range_.to_display() == "1:1-1:6"

    def test_from_lsp(self):
        lsp_range = {
            "start": {"line": 5, "character": 0},
            "end": {"line": 5, "character": 10},
        }
        range_ = Range.from_lsp(lsp_range)
        assert range_.start.line == 5
        assert range_.start.column == 0
        assert range_.end.line == 5
        assert range_.end.column == 10
```

**tests/unit/test_uri.py:**
```python
"""Tests for URI utilities."""

from pathlib import Path
import sys

import pytest

from pyright_mcp.utils.uri import path_to_uri, uri_to_path, normalize_path


class TestPathToUri:
    def test_converts_unix_path(self):
        if sys.platform == "win32":
            pytest.skip("Unix-specific test")
        path = Path("/home/user/project/file.py")
        uri = path_to_uri(path)
        assert uri.startswith("file://")
        assert "/home/user/project/file.py" in uri

    def test_handles_spaces_in_path(self):
        if sys.platform == "win32":
            pytest.skip("Unix-specific test")
        path = Path("/home/user/my project/file.py")
        uri = path_to_uri(path)
        assert "%20" in uri or "my%20project" in uri


class TestUriToPath:
    def test_converts_file_uri(self):
        if sys.platform == "win32":
            pytest.skip("Unix-specific test")
        uri = "file:///home/user/project/file.py"
        path = uri_to_path(uri)
        assert path == Path("/home/user/project/file.py")

    def test_raises_on_non_file_uri(self):
        with pytest.raises(ValueError, match="Expected file://"):
            uri_to_path("https://example.com/file.py")

    def test_handles_encoded_spaces(self):
        if sys.platform == "win32":
            pytest.skip("Unix-specific test")
        uri = "file:///home/user/my%20project/file.py"
        path = uri_to_path(uri)
        assert "my project" in str(path)


class TestNormalizePath:
    def test_returns_absolute_path(self):
        path = normalize_path("relative/path.py")
        assert path.is_absolute()

    def test_handles_path_object(self):
        path = normalize_path(Path("/some/path"))
        assert isinstance(path, Path)
```

**tests/unit/test_project_detection.py:**
```python
"""Tests for project detection."""

import os
from pathlib import Path
import tempfile

import pytest

from pyright_mcp.context import (
    find_project_root,
    find_venv,
    detect_project,
    ProjectContext,
)


class TestFindProjectRoot:
    def test_finds_pyrightconfig(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyrightconfig.json").write_text("{}")
            subdir = root / "src" / "pkg"
            subdir.mkdir(parents=True)

            assert find_project_root(subdir) == root

    def test_finds_pyproject(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text("[project]\nname = 'test'")
            subdir = root / "src"
            subdir.mkdir()

            assert find_project_root(subdir) == root

    def test_pyrightconfig_takes_precedence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyrightconfig.json").write_text("{}")
            (root / "pyproject.toml").write_text("[project]")
            subdir = root / "src"
            subdir.mkdir()

            assert find_project_root(subdir) == root

    def test_fallback_to_start_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            assert find_project_root(path) == path

    def test_handles_file_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text("[project]")
            file_path = root / "test.py"
            file_path.touch()

            assert find_project_root(file_path) == root


class TestFindVenv:
    def test_finds_venv_from_env(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            venv = Path(tmpdir) / ".venv"
            venv.mkdir()
            (venv / "bin").mkdir()
            (venv / "bin" / "python").touch()

            monkeypatch.setenv("VIRTUAL_ENV", str(venv))
            assert find_venv(Path(tmpdir)) == venv

    def test_finds_dot_venv_directory(self, monkeypatch):
        monkeypatch.delenv("VIRTUAL_ENV", raising=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            venv = root / ".venv"
            venv.mkdir()
            (venv / "bin").mkdir()
            (venv / "bin" / "python").touch()

            assert find_venv(root) == venv

    def test_finds_venv_directory(self, monkeypatch):
        monkeypatch.delenv("VIRTUAL_ENV", raising=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            venv = root / "venv"
            venv.mkdir()
            (venv / "bin").mkdir()
            (venv / "bin" / "python").touch()

            assert find_venv(root) == venv

    def test_returns_none_when_no_venv(self, monkeypatch):
        monkeypatch.delenv("VIRTUAL_ENV", raising=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            assert find_venv(Path(tmpdir)) is None


class TestDetectProject:
    def test_returns_project_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "test"\nrequires-python = ">=3.11"'
            )

            context = detect_project(root)

            assert isinstance(context, ProjectContext)
            assert context.root == root
            assert context.pyproject == root / "pyproject.toml"
```

**tests/unit/test_cli_runner.py:**
```python
"""Tests for Pyright CLI runner."""

from pathlib import Path
import pytest

from pyright_mcp.backends.cli_runner import (
    build_pyright_command,
    SEVERITY_MAP,
)
from pyright_mcp.context import ProjectContext


class TestBuildPyrightCommand:
    def test_basic_command(self):
        context = ProjectContext(
            root=Path("/project"),
            venv=None,
            pyright_config=None,
            pyproject=None,
            python_version=None,
        )

        cmd = build_pyright_command(Path("/project/test.py"), context)

        assert cmd[0] == "pyright"
        assert "--outputjson" in cmd
        assert "/project/test.py" in cmd

    def test_includes_python_version(self):
        context = ProjectContext(
            root=Path("/project"),
            venv=None,
            pyright_config=None,
            pyproject=None,
            python_version="3.11",
        )

        cmd = build_pyright_command(Path("/project/test.py"), context)

        assert "--pythonversion" in cmd
        assert "3.11" in cmd

    def test_explicit_version_overrides_context(self):
        context = ProjectContext(
            root=Path("/project"),
            venv=None,
            pyright_config=None,
            pyproject=None,
            python_version="3.10",
        )

        cmd = build_pyright_command(
            Path("/project/test.py"),
            context,
            python_version="3.12",
        )

        version_idx = cmd.index("--pythonversion")
        assert cmd[version_idx + 1] == "3.12"

    def test_includes_venv_path(self):
        context = ProjectContext(
            root=Path("/project"),
            venv=Path("/project/.venv"),
            pyright_config=None,
            pyproject=None,
            python_version=None,
        )

        cmd = build_pyright_command(Path("/project/test.py"), context)

        assert "--venvpath" in cmd
        assert "/project" in cmd


class TestSeverityMap:
    def test_maps_integers_to_strings(self):
        assert SEVERITY_MAP[1] == "error"
        assert SEVERITY_MAP[2] == "warning"
        assert SEVERITY_MAP[3] == "information"
```

---

### Step 11: Integration Tests

**tests/integration/__init__.py:**
```python
"""Integration tests for pyright-mcp."""
```

**tests/integration/test_check_types.py:**
```python
"""Integration tests for check_types tool."""

from pathlib import Path
import tempfile

import pytest

from pyright_mcp.tools.check_types import check_types


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class TestCheckTypesValidFile:
    @pytest.mark.asyncio
    async def test_returns_success_status_for_valid_file(self):
        result = await check_types(str(FIXTURES_DIR / "sample_files" / "valid.py"))

        assert result["status"] == "success"
        assert result["error_count"] == 0
        assert "No type errors found" in result["summary"]

    @pytest.mark.asyncio
    async def test_returns_diagnostics_for_file_with_errors(self):
        result = await check_types(str(FIXTURES_DIR / "sample_files" / "with_errors.py"))

        assert result["status"] == "success"
        assert result["error_count"] > 0
        assert len(result["diagnostics"]) > 0

        # Check diagnostic format
        diag = result["diagnostics"][0]
        assert "file" in diag
        assert "location" in diag
        assert "severity" in diag
        assert "message" in diag

    @pytest.mark.asyncio
    async def test_location_is_1_indexed(self):
        result = await check_types(str(FIXTURES_DIR / "sample_files" / "with_errors.py"))

        # Locations should be 1-indexed for display
        for diag in result["diagnostics"]:
            line, col = diag["location"].split(":")
            assert int(line) >= 1
            assert int(col) >= 1


class TestCheckTypesErrorCases:
    @pytest.mark.asyncio
    async def test_file_not_found_returns_error_status(self):
        result = await check_types("/nonexistent/path/file.py")

        assert result["status"] == "error"
        assert result["error_code"] == "file_not_found"
        assert "not found" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_invalid_python_syntax(self):
        result = await check_types(str(FIXTURES_DIR / "sample_files" / "syntax_error.py"))

        # Pyright should still return, possibly with syntax error diagnostics
        assert result is not None
        assert result["status"] == "success"


class TestCheckTypesProjectDetection:
    @pytest.mark.asyncio
    async def test_uses_project_config(self):
        project_file = FIXTURES_DIR / "valid_project" / "src" / "example.py"
        result = await check_types(str(project_file))

        assert result["status"] == "success"
        assert result["error_count"] == 0
        assert result["summary"] is not None
```

---

## Verification Checklist

- [ ] `uv sync` installs all dependencies
- [ ] `uv run python -m pyright_mcp` starts server without errors
- [ ] `uv run pytest` passes all tests
- [ ] `uv run pyright` shows no type errors
- [ ] `uv run ruff check .` shows no lint errors
- [ ] `uv run ruff format --check .` shows no formatting issues
- [ ] Claude Code can connect and invoke `check_types`

---

## Configuration Reference

### Environment Variables (TDD Section 8.1)

| Variable | Default | Description |
|----------|---------|-------------|
| `PYRIGHT_MCP_ALLOWED_PATHS` | (none) | Colon-separated list of allowed workspace paths. If not set, all paths allowed. |
| `PYRIGHT_MCP_LOG_MODE` | `stderr` | `stderr`, `file`, or `both` |
| `PYRIGHT_MCP_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `PYRIGHT_MCP_CLI_TIMEOUT` | `30` | CLI execution timeout (seconds) |
| `PYRIGHT_MCP_LSP_TIMEOUT` | `300` | LSP idle timeout (seconds, Phase 2+) |
| `PYRIGHT_MCP_LSP_COMMAND` | `pyright-langserver` | LSP server binary (Phase 2+) |
| `PYRIGHT_MCP_ENABLE_HEALTH_CHECK` | `true` | Enable health_check tool |
| `PYRIGHT_MCP_TRANSPORT` | (none) | Transport mode (Phase 3: stdio, http, sse) |

### Claude Code Configuration

Add to `~/.config/claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pyright": {
      "command": "uv",
      "args": ["--directory", "/path/to/pyright-mcp", "run", "python", "-m", "pyright_mcp"]
    }
  }
}
```

---

## Next Steps (Phase 2)

### Phase 2: LSP Integration for ALL Tools

**Goal:** Add hover and go-to-definition using Pyright LSP server

**Key Architectural Decision:** LSP backend for ALL tools (including check_types)
- `check_types` will use `textDocument/publishDiagnostics` from LSP
- Hover uses `textDocument/hover`
- Go-to-definition uses `textDocument/definition`
- CLI becomes fallback only when LSP not initialized
- Prefer LSP for warm operations (< 200ms), fall back to CLI for cold start

**Phase 2 Implementation Tasks:**

1. **LSP Client Infrastructure** (`src/pyright_mcp/backends/lsp_client.py`)
   - Subprocess management for `pyright-langserver --stdio`
   - Lazy initialization: start on first request (avoid cold start)
   - Idle timeout: shutdown after 5 minutes of inactivity
   - Crash recovery: restart on next request if crashed
   - Workspace switching: reinitialize if project root changes
   - JSON-RPC communication over stdin/stdout (no pygls dependency)
   - Request/response correlation with message IDs

2. **Document Manager** (`src/pyright_mcp/backends/document_manager.py`)
   - Track opened documents for `didOpen`/`didClose` lifecycle
   - Send `didOpen` once per unique file with file content
   - Read file content from disk (Pyright watches for changes)
   - Send `didClose` on idle timeout or workspace change
   - Clear tracking on LSP crash (don't send didClose)

3. **Backend Selector** (`src/pyright_mcp/backends/backend_selector.py`)
   - Choose between CLI and LSP based on state
   - Prefer LSP if already running (warm path, < 200ms)
   - Fall back to CLI if LSP not initialized (avoid cold start delay)
   - Use CLI for initial `check_types` in new workspace
   - Subsequent operations use LSP (warm and fast)
   - Handle workspace switching (reinit LSP)

4. **Hover Tool** (`src/pyright_mcp/tools/hover.py`)
   - `textDocument/hover` LSP request
   - Return type info and documentation
   - Use DocumentManager for didOpen tracking
   - Format: `{"status": "success", "type": "...", "documentation": "..."}`

5. **Definition Tool** (`src/pyright_mcp/tools/definition.py`)
   - `textDocument/definition` LSP request
   - Return definition location(s)
   - Handle multiple definitions (list)
   - Format: `{"status": "success", "definitions": [{"file": "...", "line": 0, "column": 0}]}`

6. **Update check_types Tool**
   - Add LSP backend support via backend_selector
   - Use `textDocument/publishDiagnostics` from LSP
   - Fall back to CLI backend when cold
   - Maintain same external interface (backwards compatible)

7. **LSP Tests**
   - Mock LSP responses for unit tests
   - Record real LSP interactions for integration tests (recorded responses)
   - Test LSP crash recovery and restart
   - Test workspace switching and reinitialization
   - Test document lifecycle (didOpen/didClose)

**LSP Communication Details:**
- Raw JSON-RPC over stdin/stdout (no pygls)
- Initialize sequence: `initialize` → `initialized` → ready
- Document sync: `didOpen` (with content) → watch files → `didClose`
- Requests: `textDocument/hover`, `textDocument/definition`, `textDocument/publishDiagnostics`

**Deliverables:**
- `get_hover` tool
- `go_to_definition` tool
- LSP client with lifecycle management
- Document manager
- Backend selection logic
- LSP integration tests
- Updated `check_types` with dual backend support

---

## Next Steps (Phase 3)

### Phase 3: Polish and Optimization

**Goal:** Completions, caching, performance optimization, alternative transports

**Phase 3 Implementation Tasks:**

1. **get_completions Tool** (`src/pyright_mcp/tools/completions.py`)
   - Use `textDocument/completion` LSP request
   - Return completion items with type info and documentation
   - Support trigger characters (`.`, `(`, etc.)
   - Format: `{"status": "success", "completions": [{"label": "...", "type": "...", "documentation": "..."}]}`

2. **Result Caching** (`src/pyright_mcp/cache/`)
   - Cache diagnostics by file content hash
   - Cache hover results by (file, position)
   - Invalidate on file changes (use LSP file watching)
   - LRU eviction policy
   - Configurable cache size and TTL

3. **Rate Limiting** (`src/pyright_mcp/rate_limit/limiter.py`)
   - Per-tool rate limits (configurable, e.g., 10 requests/second)
   - Prevent abuse from runaway clients
   - Token bucket algorithm
   - Configurable via `PYRIGHT_MCP_RATE_LIMIT` env var

4. **Alternative Transports** (`src/pyright_mcp/transports/`)
   - HTTP transport: RESTful API for diagnostics
   - SSE transport: Server-sent events for streaming diagnostics
   - Configured via `PYRIGHT_MCP_TRANSPORT` env var
   - stdio remains default for Claude Code

5. **Performance Metrics**
   - Track operation latencies (p50, p95, p99)
   - Count cache hits/misses
   - Log slow operations (> 1s)
   - Export metrics via `health_check` tool
   - Per-tool breakdown

6. **Multi-Project LSP Pooling**
   - Run separate LSP instance per workspace root
   - Pool management: limit max instances (e.g., 5)
   - LRU eviction when pool full
   - Share common dependencies across workspaces
   - Configurable via `PYRIGHT_MCP_LSP_POOL_SIZE`

**Environment Variables:**
```bash
PYRIGHT_MCP_TRANSPORT=stdio|http|sse  # Transport mode
PYRIGHT_MCP_CACHE_ENABLED=true        # Enable result caching
PYRIGHT_MCP_RATE_LIMIT=10             # Requests per second
PYRIGHT_MCP_LSP_POOL_SIZE=5           # Max LSP instances
```

**Deliverables:**
- `get_completions` tool
- Result caching infrastructure with file watching
- Rate limiting per tool
- HTTP and SSE transports
- Performance metrics and monitoring
- Multi-project LSP pooling

---

## Post-Implementation Note

After Phase 1 implementation is complete and validated, this document should be reduced to architectural guidance only. The inline code samples should be replaced with references to actual source files to avoid dual maintenance burden.

**Recommended post-implementation structure:**
- Keep file structure diagram
- Keep step descriptions (without code blocks)
- Replace code blocks with: "See `src/pyright_mcp/backends/cli_runner.py`"
- Keep verification checklist
- Keep configuration reference
