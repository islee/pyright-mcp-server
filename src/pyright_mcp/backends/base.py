"""Backend interface and shared data structures for Pyright operations."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from ..utils.position import Range


class BackendError(Exception):
    """Exception for backend operation errors."""

    def __init__(
        self,
        error_code: str,
        message: str,
        recoverable: bool = False,
        details: dict[str, Any] | None = None,
    ):
        """
        Initialize backend error.

        Args:
            error_code: One of: not_found, timeout, parse_error, invalid_path, execution_error
            message: Human-readable error description
            recoverable: Whether the operation can be retried
            details: Optional additional context
        """
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.recoverable = recoverable
        self.details = details or {}


@dataclass
class Diagnostic:
    """Single diagnostic from Pyright type checking.

    All positions are 0-indexed internally. Use to_dict() for 1-indexed display.
    """

    file: Path
    range: Range
    severity: Literal["error", "warning", "information", "hint"]
    message: str
    rule: str | None = None  # e.g., "reportArgumentType"

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary with 1-indexed positions for display.

        Returns:
            Dictionary with human-readable location (1-indexed)
        """
        return {
            "file": str(self.file),
            "location": self.range.to_display(),  # 1-indexed
            "severity": self.severity,
            "message": self.message,
            "rule": self.rule,
        }


@dataclass
class DiagnosticsResult:
    """Result from type checking operation."""

    diagnostics: list[Diagnostic]
    summary: str
    files_analyzed: int

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary with discriminated union pattern.

        Returns:
            Dictionary with status="success" and diagnostic data
        """
        # Count diagnostics by severity
        error_count = sum(1 for d in self.diagnostics if d.severity == "error")
        warning_count = sum(1 for d in self.diagnostics if d.severity == "warning")
        information_count = sum(
            1 for d in self.diagnostics if d.severity == "information"
        )
        hint_count = sum(1 for d in self.diagnostics if d.severity == "hint")

        return {
            "status": "success",
            "summary": self.summary,
            "files_analyzed": self.files_analyzed,
            "error_count": error_count,
            "warning_count": warning_count,
            "information_count": information_count,
            "hint_count": hint_count,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }


class Backend(Protocol):
    """Protocol for all Pyright backends (CLI and LSP).

    All backend implementations must provide check() for type checking
    and shutdown() for resource cleanup.
    """

    async def check(
        self, path: Path, *, project_root: Path | None = None
    ) -> DiagnosticsResult:
        """
        Run type checking on the given path.

        Args:
            path: File or directory to analyze
            project_root: Optional project root for configuration

        Returns:
            DiagnosticsResult with type checking results

        Raises:
            BackendError: If operation fails
        """
        ...

    async def shutdown(self) -> None:
        """Clean up backend resources.

        For stateless backends (CLI), this is a no-op.
        For stateful backends (LSP), this closes connections and processes.
        """
        ...
