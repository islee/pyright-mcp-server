"""Runtime configuration management.

Environment Variables:
    PYRIGHT_MCP_ALLOWED_PATHS: Colon-separated list of allowed paths (default: None)
    PYRIGHT_MCP_CLI_TIMEOUT: CLI timeout in seconds (default: 30.0)
    PYRIGHT_MCP_LSP_TIMEOUT: LSP idle timeout in seconds (default: 300.0)
    PYRIGHT_MCP_LSP_COMMAND: LSP server command (default: pyright-langserver --stdio)
    PYRIGHT_MCP_LOG_LEVEL: Logging level (default: INFO)
    PYRIGHT_MCP_LOG_MODE: Logging mode: stderr, file, both (default: stderr)
    PYRIGHT_MCP_LOG_FILE: Log file path (optional, for file/both modes)
    PYRIGHT_MCP_ENABLE_HEALTH_CHECK: Enable health_check tool (default: true)
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast


@dataclass
class Config:
    """Runtime configuration for pyright-mcp."""

    allowed_paths: list[Path] | None  # Workspace restriction (None = allow all)
    cli_timeout: float  # CLI execution timeout (seconds)
    lsp_timeout: float  # LSP idle timeout (seconds)
    lsp_command: list[str]  # LSP server command
    log_level: str  # Logging level: DEBUG, INFO, WARNING, ERROR
    log_mode: Literal["stderr", "file", "both"]  # Logging mode
    log_file: Path | None  # Log file path (for file/both modes)
    enable_health_check: bool  # Enable health_check tool


_config: Config | None = None


def load_config() -> Config:
    """
    Load configuration from environment variables.

    Validates all configuration values and returns a Config instance with
    defaults applied.

    Returns:
        Config instance with validated values

    Raises:
        ValueError: If configuration values are invalid
    """
    # Parse allowed paths
    allowed_paths = None
    if allowed_paths_str := os.getenv("PYRIGHT_MCP_ALLOWED_PATHS"):
        allowed_paths = [Path(p).resolve() for p in allowed_paths_str.split(":")]

    # Parse CLI timeout
    cli_timeout_str = os.getenv("PYRIGHT_MCP_CLI_TIMEOUT", "30.0")
    try:
        cli_timeout = float(cli_timeout_str)
        if cli_timeout <= 0:
            raise ValueError(
                f"PYRIGHT_MCP_CLI_TIMEOUT must be positive, got: {cli_timeout}"
            )
    except ValueError as e:
        if "could not convert" in str(e):
            raise ValueError(
                f"PYRIGHT_MCP_CLI_TIMEOUT must be a number, got: {cli_timeout_str}"
            ) from e
        raise

    # Parse LSP timeout
    lsp_timeout_str = os.getenv("PYRIGHT_MCP_LSP_TIMEOUT", "300.0")
    try:
        lsp_timeout = float(lsp_timeout_str)
        if lsp_timeout <= 0:
            raise ValueError(
                f"PYRIGHT_MCP_LSP_TIMEOUT must be positive, got: {lsp_timeout}"
            )
    except ValueError as e:
        if "could not convert" in str(e):
            raise ValueError(
                f"PYRIGHT_MCP_LSP_TIMEOUT must be a number, got: {lsp_timeout_str}"
            ) from e
        raise

    # Parse LSP command
    lsp_command_str = os.getenv("PYRIGHT_MCP_LSP_COMMAND", "pyright-langserver --stdio")
    lsp_command = lsp_command_str.split()

    # Parse log level
    log_level = os.getenv("PYRIGHT_MCP_LOG_LEVEL", "INFO").upper()
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if log_level not in valid_levels:
        raise ValueError(
            f"PYRIGHT_MCP_LOG_LEVEL must be one of {valid_levels}, got: {log_level}"
        )

    # Parse log mode
    log_mode_str = os.getenv("PYRIGHT_MCP_LOG_MODE", "stderr").lower()
    valid_modes = {"stderr", "file", "both"}
    if log_mode_str not in valid_modes:
        raise ValueError(
            f"PYRIGHT_MCP_LOG_MODE must be one of {valid_modes}, got: {log_mode_str}"
        )
    # Type assertion: we validated above that log_mode_str is in valid_modes
    log_mode = cast(Literal["stderr", "file", "both"], log_mode_str)

    # Parse log file
    log_file = None
    if log_file_str := os.getenv("PYRIGHT_MCP_LOG_FILE"):
        log_file = Path(log_file_str).resolve()

    # Parse enable_health_check
    enable_health_check = os.getenv("PYRIGHT_MCP_ENABLE_HEALTH_CHECK", "true").lower() == "true"

    return Config(
        allowed_paths=allowed_paths,
        cli_timeout=cli_timeout,
        lsp_timeout=lsp_timeout,
        lsp_command=lsp_command,
        log_level=log_level,
        log_mode=log_mode,
        log_file=log_file,
        enable_health_check=enable_health_check,
    )


def get_config() -> Config:
    """
    Get singleton config instance.

    Loads configuration on first call and caches the result.

    Returns:
        Config instance (loads on first call)
    """
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config() -> None:
    """
    Reset cached config (for testing only).

    This clears the singleton config instance, forcing load_config() to be
    called again on the next get_config() call.
    """
    global _config
    _config = None
