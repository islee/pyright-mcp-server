"""Backend interface and shared data structures for Pyright operations."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from ..utils.position import Position, Range


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
            error_code: One of: not_found, timeout, parse_error, invalid_path,
                        execution_error, validation_error, disabled,
                        lsp_not_ready, lsp_crash
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


# ============================================================================
# Phase 2/3: LSP-specific data structures and protocols
# ============================================================================


@dataclass
class HoverResult:
    """Result from hover operation.

    Attributes:
        type_info: Type signature of the symbol (e.g., "(x: int, y: int) -> int")
        documentation: Documentation string or docstring
        range: Source range of the symbol in the file (0-indexed)
    """

    type_info: str | None
    documentation: str | None
    range: Range | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for MCP response.

        Returns:
            Dictionary with status="success" and hover data.
            None values indicate no information available at position.
        """
        return {
            "status": "success",
            "symbol": self.type_info.split("(")[0].strip() if self.type_info else None,
            "type": self.type_info,
            "documentation": self.documentation,
        }


@dataclass
class Location:
    """A location in a file.

    Attributes:
        file: Path to the file
        position: 0-indexed position within the file
    """

    file: Path
    position: Position

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with 1-indexed positions for display.

        Returns:
            Dictionary with file path and 1-indexed line/column
        """
        return {
            "file": str(self.file),
            "line": self.position.line + 1,  # Convert to 1-indexed
            "column": self.position.column + 1,  # Convert to 1-indexed
        }


@dataclass
class DefinitionResult:
    """Result from go_to_definition operation.

    Attributes:
        definitions: List of locations where the symbol is defined.
                    Empty list means no definition found.
    """

    definitions: list[Location]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for MCP response.

        Returns:
            Dictionary with status="success" and definitions list
        """
        return {
            "status": "success",
            "definitions": [d.to_dict() for d in self.definitions],
        }


@dataclass
class CompletionItem:
    """A single completion suggestion.

    Attributes:
        label: Display text for the completion
        kind: Type of completion (function, variable, class, etc.)
        detail: Additional details (e.g., type signature)
        documentation: Documentation string
        insert_text: Text to insert (may differ from label)
    """

    label: str
    kind: str  # "function", "variable", "class", "method", "property", "module", "keyword"
    detail: str | None = None
    documentation: str | None = None
    insert_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for MCP response."""
        return {
            "label": self.label,
            "kind": self.kind,
            "detail": self.detail,
            "documentation": self.documentation,
            "insert_text": self.insert_text or self.label,
        }


@dataclass
class CompletionResult:
    """Result from completion operation.

    Attributes:
        items: List of completion suggestions
        is_incomplete: Whether more items may be available
    """

    items: list[CompletionItem]
    is_incomplete: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for MCP response."""
        return {
            "status": "success",
            "items": [item.to_dict() for item in self.items],
            "is_incomplete": self.is_incomplete,
        }


class HoverBackend(Protocol):
    """Protocol for backends that support hover information."""

    async def hover(
        self,
        file: Path,
        line: int,
        column: int,
        *,
        project_root: Path | None = None,
    ) -> HoverResult:
        """
        Get hover information at a position.

        Args:
            file: Path to the file
            line: 0-indexed line number
            column: 0-indexed column number
            project_root: Optional project root for configuration

        Returns:
            HoverResult with type and documentation info

        Raises:
            BackendError: If operation fails
        """
        ...


class DefinitionBackend(Protocol):
    """Protocol for backends that support go-to-definition."""

    async def definition(
        self,
        file: Path,
        line: int,
        column: int,
        *,
        project_root: Path | None = None,
    ) -> DefinitionResult:
        """
        Get definition locations for a symbol at a position.

        Args:
            file: Path to the file
            line: 0-indexed line number
            column: 0-indexed column number
            project_root: Optional project root for configuration

        Returns:
            DefinitionResult with list of definition locations

        Raises:
            BackendError: If operation fails
        """
        ...


class CompletionBackend(Protocol):
    """Protocol for backends that support code completion."""

    async def complete(
        self,
        file: Path,
        line: int,
        column: int,
        *,
        project_root: Path | None = None,
        trigger_character: str | None = None,
    ) -> CompletionResult:
        """
        Get completion suggestions at a position.

        Args:
            file: Path to the file
            line: 0-indexed line number
            column: 0-indexed column number
            project_root: Optional project root for configuration
            trigger_character: Character that triggered completion (e.g., ".")

        Returns:
            CompletionResult with completion suggestions

        Raises:
            BackendError: If operation fails
        """
        ...


@dataclass
class ReferencesResult:
    """Result from find_references operation.

    Attributes:
        references: List of locations where symbol is referenced
    """

    references: list[Location]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for MCP response.

        Returns:
            Dictionary with status="success" and references list
        """
        return {
            "status": "success",
            "references": [ref.to_dict() for ref in self.references],
            "count": len(self.references),
        }


class ReferencesBackend(Protocol):
    """Protocol for backends that support find references."""

    async def references(
        self,
        file: Path,
        line: int,
        column: int,
        *,
        project_root: Path | None = None,
        include_declaration: bool = True,
    ) -> ReferencesResult:
        """
        Find all references to symbol at a position.

        Args:
            file: Path to the file
            line: 0-indexed line number
            column: 0-indexed column number
            project_root: Optional project root for configuration
            include_declaration: Include declaration in results

        Returns:
            ReferencesResult with list of reference locations

        Raises:
            BackendError: If operation fails
        """
        ...
