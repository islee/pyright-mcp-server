"""Health check tool implementation.

This module provides the health_check MCP tool, which verifies server health
and Pyright availability.
"""

import asyncio
import time
from typing import Any

from ..backends.selector import PooledSelector, get_selector
from ..config import get_config
from ..logging_config import get_logger
from ..metrics import get_metrics_collector

logger = get_logger("tools.health_check")

# Track server start time (lazy initialization)
_server_start_time: float | None = None

# Minimum Pyright version requirement
MINIMUM_PYRIGHT_VERSION = "1.1.350"


def _parse_version(version_str: str) -> tuple[int, int, int] | None:
    """Parse version string like '1.1.350' or '1.1.350-beta.1' into (major, minor, patch) tuple.

    Args:
        version_str: Version string (e.g., "1.1.350" or "1.1.350-beta.1")

    Returns:
        Tuple of (major, minor, patch) or None if parsing fails
    """
    try:
        # Remove prerelease suffix (e.g., "-beta.1")
        version_only = version_str.split("-")[0]
        parts = version_only.split(".")
        if len(parts) < 3:
            return None
        major = int(parts[0])
        minor = int(parts[1])
        patch = int(parts[2])
        return (major, minor, patch)
    except (ValueError, IndexError, AttributeError):
        return None


def _is_version_compatible(version: str | None) -> bool:
    """Check if Pyright version is compatible (>= minimum required).

    Args:
        version: Version string (e.g., "1.1.350")

    Returns:
        True if version is >= MINIMUM_PYRIGHT_VERSION, False otherwise
    """
    if not version:
        return False

    version_tuple = _parse_version(version)
    min_version_tuple = _parse_version(MINIMUM_PYRIGHT_VERSION)

    if not version_tuple or not min_version_tuple:
        return False

    return version_tuple >= min_version_tuple


async def _get_pyright_version() -> tuple[str | None, str | None, str | None]:
    """Get installed Pyright version by running 'pyright --version'.

    Returns:
        Tuple of (version_string, error_code, error_message) where:
        - version_string is the parsed version (e.g., "1.1.350") or None
        - error_code is one of: None (success), "timeout", "not_found", "execution_error"
        - error_message is the error detail if error_code is not None
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "pyright",
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=5.0
            )
            stdout = stdout_bytes.decode("utf-8").strip()
            stderr = stderr_bytes.decode("utf-8").strip()

            if proc.returncode == 0:
                # Parse version from output (e.g., "pyright 1.1.350")
                if stdout.startswith("pyright"):
                    parts = stdout.split()
                    if len(parts) > 1:
                        return (parts[1], None, None)
                return (stdout, None, None)

            # Non-zero exit code
            return (None, "execution_error", stderr or stdout)

        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return (None, "timeout", "Pyright --version command timed out after 5s")

    except FileNotFoundError:
        return (None, "not_found", "Pyright executable not found")
    except Exception as e:
        logger.debug(f"Error getting Pyright version: {e}")
        return (None, "execution_error", str(e))


async def health_check() -> dict[str, Any]:
    """
    Check server health and verify Pyright is available.

    Verifies that:
    - Pyright CLI is installed and accessible
    - Pyright version is compatible (>= 1.1.350)
    - Server configuration is valid
    - Runtime is healthy

    Returns:
        Success:
            {
                "status": "healthy",
                "pyright_version": "1.1.350",
                "pyright_available": true,
                "config": {
                    "log_level": "INFO",
                    "log_mode": "stderr",
                    "cli_timeout": 30.0,
                    "allowed_paths_count": 1,
                    "enable_health_check": true
                },
                "uptime_seconds": 123.45
            }

        Degraded (version incompatible):
            {
                "status": "degraded",
                "pyright_version": "1.1.100",
                "pyright_available": true,
                "diagnostics": ["Pyright version 1.1.100 may be incompatible. Tested with 1.1.350+"],
                "config": {...},
                "uptime_seconds": 123.45
            }

        Error:
            {
                "status": "error",
                "error_code": "not_found" | "execution_error",
                "message": "Human-readable error message"
            }

    Example:
        >>> result = await health_check()
        >>> if result["status"] == "healthy":
        ...     print(f"Pyright {result['pyright_version']} is available")
    """
    logger.info("health_check called")

    config = get_config()

    # Check if Pyright is available
    pyright_version = None
    pyright_available = False

    try:
        logger.debug("Checking Pyright availability: pyright --version")
        pyright_version, error_code, error_message = await _get_pyright_version()

        # Handle errors from version check
        if error_code == "timeout":
            logger.error("Pyright --version command timed out")
            return {
                "status": "error",
                "error_code": "timeout",
                "message": error_message or "Pyright --version command timed out after 5s",
            }
        if error_code == "not_found":
            logger.error("Pyright executable not found")
            return {
                "status": "error",
                "error_code": "not_found",
                "message": (
                    "Pyright executable not found. Please install it: "
                    "pip install pyright"
                ),
            }
        if error_code == "execution_error":
            logger.error(f"Pyright command failed: {error_message}")
            return {
                "status": "error",
                "error_code": "execution_error",
                "message": f"Pyright command failed: {error_message}",
            }

        if pyright_version:
            pyright_available = True
            logger.info(f"Pyright is available: {pyright_version}")
        else:
            logger.error("Pyright executable not found")
            return {
                "status": "error",
                "error_code": "not_found",
                "message": (
                    "Pyright executable not found. Please install it: "
                    "pip install pyright"
                ),
            }

    except Exception as e:
        logger.error(f"Unexpected error checking Pyright availability: {e}", exc_info=True)
        return {
            "status": "error",
            "error_code": "execution_error",
            "message": f"Failed to check Pyright availability: {e}",
        }

    # Check version compatibility
    is_compatible = _is_version_compatible(pyright_version)
    health_status = "healthy" if is_compatible else "degraded"
    diagnostics: list[str] = []

    if not is_compatible:
        msg = f"Pyright version {pyright_version} may be incompatible. Tested with {MINIMUM_PYRIGHT_VERSION}+"
        diagnostics.append(msg)
        logger.warning(msg)

    # Build config summary (sanitize sensitive data)
    allowed_paths_count = len(config.allowed_paths) if config.allowed_paths else 0
    config_summary = {
        "log_level": config.log_level,
        "log_mode": config.log_mode,
        "cli_timeout": config.cli_timeout,
        "allowed_paths_count": allowed_paths_count,
        "enable_health_check": config.enable_health_check,
    }

    # Calculate uptime (initialize on first call)
    global _server_start_time
    if _server_start_time is None:
        _server_start_time = time.time()
    uptime_seconds = time.time() - _server_start_time

    # Add LSP pool statistics if using PooledSelector (Phase 3)
    selector = get_selector()
    if isinstance(selector, PooledSelector):
        pool_stats = selector._pool.get_pool_stats()
        response_with_pool: dict[str, Any] = {
            "status": health_status,
            "pyright_version": pyright_version,
            "pyright_available": pyright_available,
            "config": config_summary,
            "uptime_seconds": round(uptime_seconds, 2),
            "lsp_pool": pool_stats,
        }
        if diagnostics:
            response_with_pool["diagnostics"] = diagnostics

        # Add metrics summary
        metrics_collector = get_metrics_collector()
        all_metrics = metrics_collector.get_all_metrics()
        response_with_pool["metrics"] = {
            "uptime_seconds": round(metrics_collector.uptime_seconds(), 2),
            "workspaces": [m.to_dict() for m in all_metrics],
        }

        logger.info("Health check completed (with pool stats and metrics)")
        return response_with_pool

    # Standard response without pool stats (Phase 1-2)
    logger.info("Health check completed")
    response: dict[str, Any] = {
        "status": health_status,
        "pyright_version": pyright_version,
        "pyright_available": pyright_available,
        "config": config_summary,
        "uptime_seconds": round(uptime_seconds, 2),
    }

    if diagnostics:
        response["diagnostics"] = diagnostics

    return response
