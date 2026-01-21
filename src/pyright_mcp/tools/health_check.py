"""Health check tool implementation.

This module provides the health_check MCP tool, which verifies server health
and Pyright availability.
"""

import asyncio
import time
from typing import Any

from ..config import get_config
from ..logging_config import get_logger

logger = get_logger("tools.health_check")

# Track server start time (lazy initialization)
_server_start_time: float | None = None


async def health_check() -> dict[str, Any]:
    """
    Check server health and verify Pyright is available.

    Verifies that:
    - Pyright CLI is installed and accessible
    - Server configuration is valid
    - Runtime is healthy

    Returns:
        Success:
            {
                "status": "success",
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

        Error:
            {
                "status": "error",
                "error_code": "not_found" | "execution_error",
                "message": "Human-readable error message"
            }

    Example:
        >>> result = await health_check()
        >>> if result["status"] == "success":
        ...     print(f"Pyright {result['pyright_version']} is available")
    """
    logger.info("health_check called")

    config = get_config()

    # Check if Pyright is available by running --version
    pyright_version = None
    pyright_available = False

    try:
        logger.debug("Checking Pyright availability: pyright --version")
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
                pyright_available = True
                # Parse version from output (e.g., "pyright 1.1.350")
                # Output format: "pyright X.Y.Z"
                if stdout.startswith("pyright"):
                    pyright_version = stdout.split()[1] if len(stdout.split()) > 1 else stdout
                else:
                    pyright_version = stdout

                logger.info(f"Pyright is available: {pyright_version}")
            else:
                logger.warning(
                    f"Pyright returned non-zero exit code: {proc.returncode}. "
                    f"stdout: {stdout}, stderr: {stderr}"
                )
                return {
                    "status": "error",
                    "error_code": "execution_error",
                    "message": f"Pyright command failed: {stderr or stdout}",
                }

        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.error("Pyright --version command timed out")
            return {
                "status": "error",
                "error_code": "timeout",
                "message": "Pyright --version command timed out after 5s",
            }

    except FileNotFoundError:
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

    logger.info("Health check successful")
    return {
        "status": "success",
        "pyright_version": pyright_version,
        "pyright_available": pyright_available,
        "config": config_summary,
        "uptime_seconds": round(uptime_seconds, 2),
    }
