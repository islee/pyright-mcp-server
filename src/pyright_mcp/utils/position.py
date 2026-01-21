"""Position and range utilities with 0-indexed internal representation.

All positions in pyright-mcp use 0-indexed line and column numbers internally,
matching Pyright CLI and LSP specifications. This eliminates conversion errors
and provides consistent handling across all backends.

For human-readable output, use the to_display() methods which convert to 1-indexed format.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class Position:
    """A 0-indexed position in a file.

    Attributes:
        line: 0-indexed line number
        column: 0-indexed column number (character offset)
    """
    line: int
    column: int

    def to_display(self) -> str:
        """Convert to 1-indexed human-readable format.

        Returns:
            String in format "line:column" with 1-indexed values

        Example:
            >>> pos = Position(line=0, column=0)
            >>> pos.to_display()
            '1:1'
        """
        return f"{self.line + 1}:{self.column + 1}"

    @classmethod
    def from_lsp(cls, lsp_position: dict[str, Any]) -> "Position":
        """Create Position from LSP position dict.

        Args:
            lsp_position: Dict with 'line' and 'character' keys (0-indexed)

        Returns:
            Position instance

        Example:
            >>> lsp_pos = {"line": 5, "character": 10}
            >>> pos = Position.from_lsp(lsp_pos)
            >>> pos.line
            5
        """
        return cls(line=lsp_position["line"], column=lsp_position["character"])

    def to_lsp(self) -> dict[str, Any]:
        """Convert to LSP position dict.

        Returns:
            Dict with 'line' and 'character' keys (0-indexed)

        Example:
            >>> pos = Position(line=5, column=10)
            >>> pos.to_lsp()
            {'line': 5, 'character': 10}
        """
        return {"line": self.line, "character": self.column}


@dataclass
class Range:
    """A 0-indexed range in a file.

    Attributes:
        start: Start position (inclusive)
        end: End position (exclusive)
    """
    start: Position
    end: Position

    def to_display(self) -> str:
        """Convert to human-readable format.

        Returns:
            String in format "start_line:start_col-end_line:end_col" with 1-indexed values

        Example:
            >>> range_ = Range(
            ...     start=Position(line=0, column=0),
            ...     end=Position(line=0, column=5)
            ... )
            >>> range_.to_display()
            '1:1-1:6'
        """
        return f"{self.start.to_display()}-{self.end.to_display()}"

    @classmethod
    def from_lsp(cls, lsp_range: dict[str, Any]) -> "Range":
        """Create Range from LSP range dict.

        Args:
            lsp_range: Dict with 'start' and 'end' position dicts (0-indexed)

        Returns:
            Range instance

        Example:
            >>> lsp_range = {
            ...     "start": {"line": 5, "character": 0},
            ...     "end": {"line": 5, "character": 10}
            ... }
            >>> range_ = Range.from_lsp(lsp_range)
            >>> range_.start.line
            5
        """
        return cls(
            start=Position.from_lsp(lsp_range["start"]),
            end=Position.from_lsp(lsp_range["end"]),
        )

    def to_lsp(self) -> dict[str, Any]:
        """Convert to LSP range dict.

        Returns:
            Dict with 'start' and 'end' position dicts (0-indexed)

        Example:
            >>> range_ = Range(
            ...     start=Position(line=5, column=0),
            ...     end=Position(line=5, column=10)
            ... )
            >>> range_.to_lsp()
            {'start': {'line': 5, 'character': 0}, 'end': {'line': 5, 'character': 10}}
        """
        return {"start": self.start.to_lsp(), "end": self.end.to_lsp()}
