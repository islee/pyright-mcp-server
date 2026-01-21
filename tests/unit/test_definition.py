"""Tests for definition tool."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pyright_mcp.backends.base import BackendError, DefinitionResult, Location
from pyright_mcp.tools.definition import go_to_definition
from pyright_mcp.utils.position import Position
from pyright_mcp.validation import ValidationError

# Note: validate_position_input tests are in test_hover.py since the function
# is now shared. These tests focus on go_to_definition behavior.


class TestGoToDefinition:
    """Tests for go_to_definition function."""

    @pytest.mark.asyncio
    async def test_go_to_definition_validation_error_response(self, tmp_path: Path):
        """Test go_to_definition returns error for invalid input."""
        result = await go_to_definition("", line=1, column=1)

        assert result["status"] == "error"
        assert result["error_code"] == "validation_error"

    @pytest.mark.asyncio
    async def test_go_to_definition_file_not_found_response(self, tmp_path: Path):
        """Test go_to_definition returns error for nonexistent file."""
        nonexistent = tmp_path / "nonexistent.py"

        result = await go_to_definition(str(nonexistent), line=1, column=1)

        assert result["status"] == "error"
        assert "error_code" in result

    @pytest.mark.asyncio
    async def test_go_to_definition_success_with_mock_backend(self, tmp_path: Path):
        """Test go_to_definition returns success with mocked backend."""
        file_path = tmp_path / "test.py"
        file_path.write_text("x: int = 1")

        target_file = tmp_path / "module.py"

        mock_definition_result = DefinitionResult(
            definitions=[
                Location(
                    file=target_file,
                    position=Position(line=5, column=4),
                ),
            ]
        )

        mock_backend = MagicMock()
        mock_backend.definition = AsyncMock(return_value=mock_definition_result)

        mock_selector = MagicMock()
        mock_selector.get_definition_backend = AsyncMock(return_value=mock_backend)

        with patch("pyright_mcp.tools.definition.get_selector", return_value=mock_selector):
            result = await go_to_definition(str(file_path), line=1, column=1)

        assert result["status"] == "success"
        assert len(result["definitions"]) == 1
        # Positions in result are 1-indexed
        assert result["definitions"][0]["line"] == 6  # 5 + 1
        assert result["definitions"][0]["column"] == 5  # 4 + 1

    @pytest.mark.asyncio
    async def test_go_to_definition_backend_error_response(self, tmp_path: Path):
        """Test go_to_definition returns error when backend fails."""
        file_path = tmp_path / "test.py"
        file_path.write_text("x: int = 1")

        mock_backend = MagicMock()
        mock_backend.definition = AsyncMock(
            side_effect=BackendError(
                error_code="timeout",
                message="LSP request timed out",
                recoverable=True,
            )
        )

        mock_selector = MagicMock()
        mock_selector.get_definition_backend = AsyncMock(return_value=mock_backend)

        with patch("pyright_mcp.tools.definition.get_selector", return_value=mock_selector):
            result = await go_to_definition(str(file_path), line=1, column=1)

        assert result["status"] == "error"
        assert result["error_code"] == "timeout"

    @pytest.mark.asyncio
    async def test_go_to_definition_converts_positions(self, tmp_path: Path):
        """Test go_to_definition converts 1-indexed input to 0-indexed for backend."""
        file_path = tmp_path / "test.py"
        file_path.write_text("x: int = 1\ny: str = 'hello'")

        mock_definition_result = DefinitionResult(definitions=[])

        mock_backend = MagicMock()
        mock_backend.definition = AsyncMock(return_value=mock_definition_result)

        mock_selector = MagicMock()
        mock_selector.get_definition_backend = AsyncMock(return_value=mock_backend)

        with patch("pyright_mcp.tools.definition.get_selector", return_value=mock_selector):
            await go_to_definition(str(file_path), line=2, column=5)

        # Verify backend was called with 0-indexed positions
        mock_backend.definition.assert_called_once()
        call_args = mock_backend.definition.call_args
        # line=2 (1-indexed) -> line=1 (0-indexed)
        assert call_args[0][1] == 1
        # column=5 (1-indexed) -> column=4 (0-indexed)
        assert call_args[0][2] == 4

    @pytest.mark.asyncio
    async def test_go_to_definition_no_definition_found(self, tmp_path: Path):
        """Test go_to_definition returns empty definitions when none found."""
        file_path = tmp_path / "test.py"
        file_path.write_text("# just a comment")

        mock_definition_result = DefinitionResult(definitions=[])

        mock_backend = MagicMock()
        mock_backend.definition = AsyncMock(return_value=mock_definition_result)

        mock_selector = MagicMock()
        mock_selector.get_definition_backend = AsyncMock(return_value=mock_backend)

        with patch("pyright_mcp.tools.definition.get_selector", return_value=mock_selector):
            result = await go_to_definition(str(file_path), line=1, column=1)

        assert result["status"] == "success"
        assert result["definitions"] == []

    @pytest.mark.asyncio
    async def test_go_to_definition_multiple_definitions(self, tmp_path: Path):
        """Test go_to_definition handles multiple definitions."""
        file_path = tmp_path / "test.py"
        file_path.write_text("x: int = 1")

        mock_definition_result = DefinitionResult(
            definitions=[
                Location(
                    file=Path("/path/to/module1.py"),
                    position=Position(line=10, column=0),
                ),
                Location(
                    file=Path("/path/to/module2.py"),
                    position=Position(line=20, column=4),
                ),
            ]
        )

        mock_backend = MagicMock()
        mock_backend.definition = AsyncMock(return_value=mock_definition_result)

        mock_selector = MagicMock()
        mock_selector.get_definition_backend = AsyncMock(return_value=mock_backend)

        with patch("pyright_mcp.tools.definition.get_selector", return_value=mock_selector):
            result = await go_to_definition(str(file_path), line=1, column=1)

        assert result["status"] == "success"
        assert len(result["definitions"]) == 2
        # First definition
        assert result["definitions"][0]["file"] == "/path/to/module1.py"
        assert result["definitions"][0]["line"] == 11  # 10 + 1
        # Second definition
        assert result["definitions"][1]["file"] == "/path/to/module2.py"
        assert result["definitions"][1]["line"] == 21  # 20 + 1
