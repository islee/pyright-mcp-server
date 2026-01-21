"""Pyright CLI backend implementation.

This module provides the CLI-based backend for running Pyright type checking
using the `pyright --outputjson` command.

CRITICAL: Pyright CLI returns non-zero exit code when type errors are found,
but still outputs valid JSON. Always parse stdout regardless of return code.
"""

import asyncio
import json
from pathlib import Path
from typing import Literal, cast

from ..config import Config, get_config
from ..logging_config import get_logger
from ..utils.position import Range
from .base import BackendError, Diagnostic, DiagnosticsResult

logger = get_logger("backends.cli_runner")


class PyrightCLIRunner:
    """Pyright CLI backend using --outputjson flag.

    This backend invokes the Pyright CLI tool with --outputjson to get
    structured type checking results. It implements the Backend protocol
    for consistent error handling and testing.
    """

    def __init__(self, config: Config | None = None):
        """
        Initialize CLI runner with optional config.

        Args:
            config: Configuration instance (uses get_config() if not provided)
        """
        self.config = config or get_config()

    async def check(
        self,
        path: Path,
        *,
        project_root: Path | None = None,
        python_version: str | None = None,
    ) -> DiagnosticsResult:
        """
        Run type checking on the given path.

        Args:
            path: File or directory to analyze
            project_root: Optional project root for configuration
            python_version: Python version to target (e.g., "3.11")

        Returns:
            DiagnosticsResult with type checking results

        Raises:
            BackendError: If operation fails (timeout, parse error, etc.)
        """
        # Build command
        cmd = build_pyright_command(
            path, project_root=project_root, python_version=python_version
        )

        logger.info(
            "Running Pyright CLI",
            extra={"command": " ".join(cmd), "path": str(path)},
        )

        # Run pyright with timeout
        try:
            stdout, stderr, return_code = await run_pyright(
                cmd, timeout=self.config.cli_timeout
            )
        except BackendError:
            raise  # Re-raise timeout errors
        except Exception as e:
            logger.error(f"Unexpected error running Pyright: {e}", exc_info=True)
            raise BackendError(
                error_code="execution_error",
                message=f"Failed to execute Pyright: {e}",
                recoverable=False,
            )

        # Parse output (Pyright returns non-zero on type errors but output is still valid)
        logger.debug(
            "Pyright command completed",
            extra={"return_code": return_code, "stderr": stderr[:500] if stderr else ""},
        )

        try:
            result = parse_pyright_output(stdout, stderr, return_code)
        except BackendError:
            raise  # Re-raise parse errors
        except Exception as e:
            logger.error(f"Unexpected error parsing Pyright output: {e}", exc_info=True)
            raise BackendError(
                error_code="parse_error",
                message=f"Failed to parse Pyright output: {e}",
                recoverable=False,
            )

        logger.info(
            "Type checking complete",
            extra={
                "files_analyzed": result.files_analyzed,
                "diagnostics": len(result.diagnostics),
            },
        )

        return result

    async def shutdown(self) -> None:
        """
        Clean up backend resources.

        For the CLI backend, this is a no-op since each invocation is stateless.
        This method exists to satisfy the Backend protocol for Phase 2 compatibility.
        """
        # CLI backend is stateless, no cleanup needed


def build_pyright_command(
    path: Path,
    *,
    project_root: Path | None = None,
    python_version: str | None = None,
) -> list[str]:
    """
    Build Pyright CLI command with all relevant flags.

    Args:
        path: File or directory to analyze
        project_root: Optional project root for configuration
        python_version: Python version to target (e.g., "3.11")

    Returns:
        Command as list of strings for subprocess (safe from shell injection)

    Security:
        ALWAYS uses list args, never shell=True. This prevents shell injection
        attacks from malicious file paths.
    """
    cmd = ["pyright", "--outputjson"]

    # Add project root if provided
    if project_root:
        cmd.extend(["--project", str(project_root)])

    # Add Python version if provided
    if python_version:
        cmd.extend(["--pythonversion", python_version])

    # Target path (must be last positional argument)
    cmd.append(str(path))

    return cmd


async def run_pyright(cmd: list[str], *, timeout: float) -> tuple[str, str, int]:
    """
    Execute Pyright CLI command asynchronously.

    Args:
        cmd: Command as list of strings
        timeout: Timeout in seconds

    Returns:
        Tuple of (stdout, stderr, return_code)

    Raises:
        BackendError: If command times out or executable not found
    """
    try:
        # Create subprocess
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Wait for completion with timeout
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            # Kill process on timeout
            proc.kill()
            await proc.wait()
            raise BackendError(
                error_code="timeout",
                message=f"Pyright command timed out after {timeout}s",
                recoverable=True,
            )

        stdout = stdout_bytes.decode("utf-8")
        stderr = stderr_bytes.decode("utf-8")
        return_code = proc.returncode or 0

        return (stdout, stderr, return_code)

    except BackendError:
        # Re-raise BackendError without wrapping
        raise
    except FileNotFoundError as e:
        # Pyright executable not found
        raise BackendError(
            error_code="not_found",
            message=f"Pyright executable not found. Is it installed? ({e})",
            recoverable=False,
        )
    except Exception as e:
        # Unexpected error during subprocess execution
        raise BackendError(
            error_code="execution_error",
            message=f"Failed to run Pyright: {e}",
            recoverable=False,
        )


def parse_pyright_output(stdout: str, stderr: str, return_code: int) -> DiagnosticsResult:
    """
    Parse Pyright JSON output into DiagnosticsResult.

    Args:
        stdout: JSON output from Pyright CLI
        stderr: Error output (for logging/debugging)
        return_code: Process exit code (non-zero when errors found, but output is still valid)

    Returns:
        DiagnosticsResult with parsed diagnostics

    Raises:
        BackendError: If JSON parsing fails or output format is invalid

    Note:
        Pyright returns non-zero exit code when type errors are found, but
        the JSON output is still valid and should be parsed.
    """
    # Parse JSON output
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Pyright JSON output: {e}")
        logger.debug(f"stdout: {stdout[:1000]}")
        logger.debug(f"stderr: {stderr[:1000]}")
        raise BackendError(
            error_code="parse_error",
            message=f"Invalid JSON from Pyright: {e}",
            recoverable=False,
        )

    # Extract diagnostics
    diagnostics: list[Diagnostic] = []
    general_diagnostics = data.get("generalDiagnostics", [])

    for diag in general_diagnostics:
        # Parse severity (Pyright uses integers: 1=error, 2=warning, 3=information)
        severity_map = {
            1: "error",
            2: "warning",
            3: "information",
            4: "hint",  # Not commonly used by Pyright but included for completeness
        }
        severity_code = diag.get("severity", 1)
        severity_str = severity_map.get(severity_code, "error")
        severity = cast("Literal['error', 'warning', 'information', 'hint']", severity_str)

        # Parse range (0-indexed positions from Pyright)
        range_data = diag.get("range", {})
        try:
            range_obj = Range.from_lsp(range_data)
        except (KeyError, TypeError) as e:
            logger.warning(f"Invalid range in diagnostic: {e}, skipping diagnostic")
            continue

        # Parse file path
        file_path = Path(diag.get("file", ""))

        # Create diagnostic
        diagnostic = Diagnostic(
            file=file_path,
            range=range_obj,
            severity=severity,
            message=diag.get("message", ""),
            rule=diag.get("rule"),
        )
        diagnostics.append(diagnostic)

    # Extract summary information
    summary_data = data.get("summary", {})
    files_analyzed = summary_data.get("filesAnalyzed", 0)
    error_count = summary_data.get("errorCount", 0)
    warning_count = summary_data.get("warningCount", 0)
    information_count = summary_data.get("informationCount", 0)
    time_sec = summary_data.get("timeInSec", 0.0)

    # Build human-readable summary
    parts = [f"Analyzed {files_analyzed} file(s) in {time_sec:.2f}s"]
    if error_count > 0:
        parts.append(f"Found {error_count} error(s)")
    if warning_count > 0:
        parts.append(f"{warning_count} warning(s)")
    if information_count > 0:
        parts.append(f"{information_count} info(s)")

    if error_count == 0 and warning_count == 0:
        parts.append("No issues found")

    summary = ". ".join(parts) + "."

    return DiagnosticsResult(
        diagnostics=diagnostics,
        summary=summary,
        files_analyzed=files_analyzed,
    )
