"""Logging configuration for pyright-mcp.

This module provides JSON-formatted logging to stderr (default for production)
and optional human-readable file logging for development.

IMPORTANT: No logging at import time. All logging setup must happen explicitly
via setup_logging().
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Config

# Request ID for correlation across async operations
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    """Format log records as JSON lines for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """
        Format a log record as a JSON line.

        Args:
            record: Log record to format

        Returns:
            JSON-formatted log line
        """
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add request ID if present
        if request_id := request_id_var.get():
            log_obj["request_id"] = request_id

        # Add extra fields from record
        for key in ["path", "command", "duration", "error_code"]:
            if hasattr(record, key):
                log_obj[key] = getattr(record, key)

        # Add exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


class RequestIdFilter(logging.Filter):
    """Inject request_id into log records from context variable."""

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Add request_id to log record if present in context.

        Args:
            record: Log record to filter

        Returns:
            True (always pass through)
        """
        if request_id := request_id_var.get():
            record.request_id = request_id  # type: ignore[attr-defined]
        return True


def setup_logging(config: "Config") -> None:
    """
    Configure logging based on config.log_mode.

    Args:
        config: Configuration instance with logging settings

    Logging Modes:
        - "stderr": JSON formatter to stderr (default for production)
        - "file": Human-readable format to config.log_file
        - "both": Both outputs

    The root logger level is set from config.log_level.
    A logger under the pyright_mcp namespace is configured for the server.

    IMPORTANT: This function should be called once at application startup,
    NOT at module import time.
    """
    # Get or create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(config.log_level)

    # Clear any existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Create formatters
    json_formatter = JsonFormatter()
    human_formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Add request ID filter
    request_id_filter = RequestIdFilter()

    # Configure stderr handler (JSON format for production)
    if config.log_mode in ("stderr", "both"):
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(json_formatter)
        stderr_handler.addFilter(request_id_filter)
        root_logger.addHandler(stderr_handler)

    # Configure file handler (human-readable format for development)
    if config.log_mode in ("file", "both"):
        log_file = _get_log_file(config)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        file_handler.setFormatter(human_formatter)
        file_handler.addFilter(request_id_filter)
        root_logger.addHandler(file_handler)

        # Create symlink to current.log for easy tailing
        _create_current_log_symlink(log_file)

    # Configure pyright_mcp logger
    pyright_mcp_logger = logging.getLogger("pyright_mcp")
    pyright_mcp_logger.setLevel(config.log_level)

    # Log initialization complete
    logging.info(
        "Logging initialized",
        extra={
            "log_mode": config.log_mode,
            "log_level": config.log_level,
        },
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger under the pyright_mcp namespace.

    Args:
        name: Logger name (e.g., "cli_runner")

    Returns:
        Logger instance for "pyright_mcp.<name>"

    Example:
        >>> logger = get_logger("cli_runner")
        >>> logger.name
        'pyright_mcp.cli_runner'
    """
    return logging.getLogger(f"pyright_mcp.{name}")


def _get_log_file(config: "Config") -> Path:
    """
    Get log file path, auto-determining if not specified.

    Args:
        config: Configuration instance

    Returns:
        Path to log file
    """
    if config.log_file:
        return config.log_file

    # Auto-determine log directory based on platform
    log_dir = _get_log_directory()
    log_dir.mkdir(parents=True, exist_ok=True)

    # Use timestamp in filename for uniqueness
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return log_dir / f"pyright-mcp-{timestamp}.log"


def _get_log_directory() -> Path:
    """
    Get platform-appropriate log directory.

    Returns:
        Path to log directory
    """
    if sys.platform == "win32":
        return Path.home() / "AppData" / "Local" / "pyright-mcp" / "logs"
    return Path.home() / ".pyright-mcp" / "logs"


def _create_current_log_symlink(log_file: Path) -> None:
    """
    Create or update symlink to current log file.

    Args:
        log_file: Path to current log file
    """
    current_link = log_file.parent / "current.log"

    # Remove existing symlink or file
    if current_link.exists() or current_link.is_symlink():
        current_link.unlink()

    # Create new symlink
    try:
        current_link.symlink_to(log_file.name)
    except OSError:
        # Symlinks may not be supported on some systems
        pass
