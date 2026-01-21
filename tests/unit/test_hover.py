"""Tests for hover tool."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pyright_mcp.backends.base import BackendError, HoverResult
from pyright_mcp.tools.hover import get_hover
from pyright_mcp.utils.position import Position, Range
from pyright_mcp.validation import ValidationError, validate_position_input


class TestValidatePositionInputForHover:
    """Tests for validate_position_input function (hover tool context)."""

    def test_validate_position_input_success(self, tmp_path: Path):
        """Test successful validation with valid inputs."""
        file_path = tmp_path / "test.py"
        file_path.write_text("x: int = 1")

        validated_path, line, column = validate_position_input(
            str(file_path), line=10, column=5
        )

        assert validated_path == file_path.resolve()
        # Converted from 1-indexed to 0-indexed
        assert line == 9
        assert column == 4

    def test_validate_position_input_none_file(self):
        """Test validation fails for None file."""
        with pytest.raises(ValidationError) as exc_info:
            validate_position_input(None, line=1, column=1)
        assert exc_info.value.field == "file"

    def test_validate_position_input_empty_file(self):
        """Test validation fails for empty file string."""
        with pytest.raises(ValidationError) as exc_info:
            validate_position_input("", line=1, column=1)
        assert exc_info.value.field == "file"

    def test_validate_position_input_whitespace_file(self):
        """Test validation fails for whitespace-only file string."""
        with pytest.raises(ValidationError) as exc_info:
            validate_position_input("   ", line=1, column=1)
        assert exc_info.value.field == "file"

    def test_validate_position_input_none_line(self, tmp_path: Path):
        """Test validation fails for None line."""
        file_path = tmp_path / "test.py"
        file_path.write_text("x: int = 1")

        with pytest.raises(ValidationError) as exc_info:
            validate_position_input(str(file_path), line=None, column=1)
        assert exc_info.value.field == "line"

    def test_validate_position_input_zero_line(self, tmp_path: Path):
        """Test validation fails for line < 1."""
        file_path = tmp_path / "test.py"
        file_path.write_text("x: int = 1")

        with pytest.raises(ValidationError) as exc_info:
            validate_position_input(str(file_path), line=0, column=1)
        assert exc_info.value.field == "line"

    def test_validate_position_input_negative_line(self, tmp_path: Path):
        """Test validation fails for negative line."""
        file_path = tmp_path / "test.py"
        file_path.write_text("x: int = 1")

        with pytest.raises(ValidationError) as exc_info:
            validate_position_input(str(file_path), line=-1, column=1)
        assert exc_info.value.field == "line"

    def test_validate_position_input_none_column(self, tmp_path: Path):
        """Test validation fails for None column."""
        file_path = tmp_path / "test.py"
        file_path.write_text("x: int = 1")

        with pytest.raises(ValidationError) as exc_info:
            validate_position_input(str(file_path), line=1, column=None)
        assert exc_info.value.field == "column"

    def test_validate_position_input_zero_column(self, tmp_path: Path):
        """Test validation fails for column < 1."""
        file_path = tmp_path / "test.py"
        file_path.write_text("x: int = 1")

        with pytest.raises(ValidationError) as exc_info:
            validate_position_input(str(file_path), line=1, column=0)
        assert exc_info.value.field == "column"

    def test_validate_position_input_nonexistent_file(self, tmp_path: Path):
        """Test validation fails for nonexistent file."""
        nonexistent = tmp_path / "nonexistent.py"

        with pytest.raises(ValidationError) as exc_info:
            validate_position_input(str(nonexistent), line=1, column=1)
        assert "does not exist" in exc_info.value.message


class TestGetHover:
    """Tests for get_hover function."""

    @pytest.mark.asyncio
    async def test_get_hover_validation_error_response(self, tmp_path: Path):
        """Test get_hover returns error for invalid input."""
        result = await get_hover("", line=1, column=1)

        assert result["status"] == "error"
        assert result["error_code"] == "validation_error"

    @pytest.mark.asyncio
    async def test_get_hover_file_not_found_response(self, tmp_path: Path):
        """Test get_hover returns error for nonexistent file."""
        nonexistent = tmp_path / "nonexistent.py"

        result = await get_hover(str(nonexistent), line=1, column=1)

        assert result["status"] == "error"
        assert "error_code" in result

    @pytest.mark.asyncio
    async def test_get_hover_success_with_mock_backend(self, tmp_path: Path):
        """Test get_hover returns success with mocked backend."""
        file_path = tmp_path / "test.py"
        file_path.write_text("x: int = 1")

        # Mock the selector and backend
        mock_hover_result = HoverResult(
            type_info="int",
            documentation="An integer variable.",
            range=Range(
                start=Position(line=0, column=0),
                end=Position(line=0, column=1),
            ),
        )

        mock_backend = MagicMock()
        mock_backend.hover = AsyncMock(return_value=mock_hover_result)

        mock_selector = MagicMock()
        mock_selector.get_hover_backend = AsyncMock(return_value=mock_backend)

        with patch("pyright_mcp.tools.hover.get_selector", return_value=mock_selector):
            result = await get_hover(str(file_path), line=1, column=1)

        assert result["status"] == "success"
        assert result["type"] == "int"
        assert result["documentation"] == "An integer variable."

    @pytest.mark.asyncio
    async def test_get_hover_backend_error_response(self, tmp_path: Path):
        """Test get_hover returns error when backend fails."""
        file_path = tmp_path / "test.py"
        file_path.write_text("x: int = 1")

        mock_backend = MagicMock()
        mock_backend.hover = AsyncMock(
            side_effect=BackendError(
                error_code="lsp_crash",
                message="LSP server crashed",
                recoverable=True,
            )
        )

        mock_selector = MagicMock()
        mock_selector.get_hover_backend = AsyncMock(return_value=mock_backend)

        with patch("pyright_mcp.tools.hover.get_selector", return_value=mock_selector):
            result = await get_hover(str(file_path), line=1, column=1)

        assert result["status"] == "error"
        assert result["error_code"] == "lsp_crash"
        assert "crashed" in result["message"]

    @pytest.mark.asyncio
    async def test_get_hover_converts_positions(self, tmp_path: Path):
        """Test get_hover converts 1-indexed input to 0-indexed for backend."""
        file_path = tmp_path / "test.py"
        file_path.write_text("x: int = 1\ny: str = 'hello'")

        mock_hover_result = HoverResult(
            type_info="str", documentation=None, range=None
        )

        mock_backend = MagicMock()
        mock_backend.hover = AsyncMock(return_value=mock_hover_result)

        mock_selector = MagicMock()
        mock_selector.get_hover_backend = AsyncMock(return_value=mock_backend)

        with patch("pyright_mcp.tools.hover.get_selector", return_value=mock_selector):
            await get_hover(str(file_path), line=2, column=5)

        # Verify backend was called with 0-indexed positions
        mock_backend.hover.assert_called_once()
        call_args = mock_backend.hover.call_args
        # line=2 (1-indexed) -> line=1 (0-indexed)
        assert call_args[0][1] == 1
        # column=5 (1-indexed) -> column=4 (0-indexed)
        assert call_args[0][2] == 4

    @pytest.mark.asyncio
    async def test_get_hover_no_info_at_position(self, tmp_path: Path):
        """Test get_hover returns success with null fields when no info."""
        file_path = tmp_path / "test.py"
        file_path.write_text("# just a comment")

        mock_hover_result = HoverResult(
            type_info=None, documentation=None, range=None
        )

        mock_backend = MagicMock()
        mock_backend.hover = AsyncMock(return_value=mock_hover_result)

        mock_selector = MagicMock()
        mock_selector.get_hover_backend = AsyncMock(return_value=mock_backend)

        with patch("pyright_mcp.tools.hover.get_selector", return_value=mock_selector):
            result = await get_hover(str(file_path), line=1, column=1)

        assert result["status"] == "success"
        assert result["type"] is None
        assert result["documentation"] is None
        assert result["symbol"] is None
