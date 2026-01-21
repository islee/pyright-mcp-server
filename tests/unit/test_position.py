"""Unit tests for position and range utilities."""

import pytest

from pyright_mcp.utils.position import Position, Range


class TestPosition:
    """Tests for Position class."""

    def test_position_creation_zero_indexed(self):
        """Test Position is created with 0-indexed values."""
        pos = Position(line=0, column=0)
        assert pos.line == 0
        assert pos.column == 0

    def test_position_to_display_converts_to_one_indexed(self):
        """Test to_display() converts to 1-indexed format."""
        pos = Position(line=0, column=0)
        assert pos.to_display() == "1:1"

        pos = Position(line=9, column=4)
        assert pos.to_display() == "10:5"

    def test_position_to_display_format(self):
        """Test to_display() returns correct format."""
        pos = Position(line=42, column=15)
        display = pos.to_display()
        assert display == "43:16"
        assert isinstance(display, str)
        assert ":" in display

    def test_position_from_lsp(self):
        """Test creating Position from LSP position dict."""
        lsp_pos = {"line": 5, "character": 10}
        pos = Position.from_lsp(lsp_pos)
        assert pos.line == 5
        assert pos.column == 10

    def test_position_to_lsp(self):
        """Test converting Position to LSP position dict."""
        pos = Position(line=5, column=10)
        lsp_pos = pos.to_lsp()
        assert lsp_pos == {"line": 5, "character": 10}

    def test_position_from_lsp_to_lsp_round_trip(self):
        """Test from_lsp() and to_lsp() round-trip preserves values."""
        original = {"line": 42, "character": 17}
        pos = Position.from_lsp(original)
        result = pos.to_lsp()
        assert result == original

    def test_position_equality(self):
        """Test Position equality comparison."""
        pos1 = Position(line=5, column=10)
        pos2 = Position(line=5, column=10)
        pos3 = Position(line=5, column=11)
        assert pos1 == pos2
        assert pos1 != pos3


class TestRange:
    """Tests for Range class."""

    def test_range_creation(self):
        """Test Range is created with Position objects."""
        start = Position(line=0, column=0)
        end = Position(line=0, column=5)
        range_ = Range(start=start, end=end)
        assert range_.start == start
        assert range_.end == end

    def test_range_to_display(self):
        """Test to_display() returns 1-indexed format."""
        range_ = Range(
            start=Position(line=0, column=0), end=Position(line=0, column=5)
        )
        assert range_.to_display() == "1:1-1:6"

    def test_range_to_display_multiline(self):
        """Test to_display() with multi-line range."""
        range_ = Range(
            start=Position(line=5, column=0), end=Position(line=10, column=15)
        )
        assert range_.to_display() == "6:1-11:16"

    def test_range_to_display_format(self):
        """Test to_display() returns correct format."""
        range_ = Range(
            start=Position(line=42, column=7), end=Position(line=42, column=15)
        )
        display = range_.to_display()
        assert display == "43:8-43:16"
        assert isinstance(display, str)
        assert "-" in display

    def test_range_from_lsp(self):
        """Test creating Range from LSP range dict."""
        lsp_range = {
            "start": {"line": 5, "character": 0},
            "end": {"line": 5, "character": 10},
        }
        range_ = Range.from_lsp(lsp_range)
        assert range_.start.line == 5
        assert range_.start.column == 0
        assert range_.end.line == 5
        assert range_.end.column == 10

    def test_range_to_lsp(self):
        """Test converting Range to LSP range dict."""
        range_ = Range(
            start=Position(line=5, column=0), end=Position(line=5, column=10)
        )
        lsp_range = range_.to_lsp()
        assert lsp_range == {
            "start": {"line": 5, "character": 0},
            "end": {"line": 5, "character": 10},
        }

    def test_range_from_lsp_to_lsp_round_trip(self):
        """Test from_lsp() and to_lsp() round-trip preserves values."""
        original = {
            "start": {"line": 10, "character": 5},
            "end": {"line": 15, "character": 20},
        }
        range_ = Range.from_lsp(original)
        result = range_.to_lsp()
        assert result == original

    def test_range_equality(self):
        """Test Range equality comparison."""
        range1 = Range(
            start=Position(line=0, column=0), end=Position(line=0, column=5)
        )
        range2 = Range(
            start=Position(line=0, column=0), end=Position(line=0, column=5)
        )
        range3 = Range(
            start=Position(line=0, column=0), end=Position(line=0, column=6)
        )
        assert range1 == range2
        assert range1 != range3
