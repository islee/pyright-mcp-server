"""Tests for document manager."""

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from pyright_mcp.backends.document_manager import DocumentManager, OpenDocument


class TestOpenDocument:
    """Tests for OpenDocument dataclass."""

    def test_open_document_creation(self):
        """Test OpenDocument is created with correct fields."""
        doc = OpenDocument(uri="file:///test.py", version=1)
        assert doc.uri == "file:///test.py"
        assert doc.version == 1
        assert doc.opened_at > 0  # Should have a timestamp

    def test_open_document_with_explicit_timestamp(self):
        """Test OpenDocument with explicit timestamp."""
        timestamp = time.time() - 100
        doc = OpenDocument(uri="file:///test.py", version=2, opened_at=timestamp)
        assert doc.opened_at == timestamp


class TestDocumentManager:
    """Tests for DocumentManager class."""

    def test_document_manager_initialization(self):
        """Test DocumentManager initializes with empty state."""
        manager = DocumentManager()
        assert manager.open_count == 0

    def test_is_open_returns_false_for_unopened_document(self, tmp_path: Path):
        """Test is_open returns False for document not yet opened."""
        manager = DocumentManager()
        file_path = tmp_path / "test.py"
        file_path.write_text("x: int = 1")

        assert manager.is_open(file_path) is False

    @pytest.mark.asyncio
    async def test_ensure_open_sends_didopen_notification(self, tmp_path: Path):
        """Test ensure_open sends didOpen notification."""
        manager = DocumentManager()
        file_path = tmp_path / "test.py"
        file_path.write_text("x: int = 1")

        # Mock LSP client
        mock_lsp = MagicMock()
        mock_lsp.send_notification = AsyncMock()

        await manager.ensure_open(mock_lsp, file_path)

        # Verify notification was sent
        mock_lsp.send_notification.assert_called_once()
        call_args = mock_lsp.send_notification.call_args
        assert call_args[0][0] == "textDocument/didOpen"
        params = call_args[0][1]
        assert "textDocument" in params
        assert params["textDocument"]["languageId"] == "python"
        assert params["textDocument"]["version"] == 1
        assert params["textDocument"]["text"] == "x: int = 1"

    @pytest.mark.asyncio
    async def test_ensure_open_tracks_document(self, tmp_path: Path):
        """Test ensure_open adds document to tracking."""
        manager = DocumentManager()
        file_path = tmp_path / "test.py"
        file_path.write_text("x: int = 1")

        mock_lsp = MagicMock()
        mock_lsp.send_notification = AsyncMock()

        await manager.ensure_open(mock_lsp, file_path)

        assert manager.is_open(file_path) is True
        assert manager.open_count == 1

    @pytest.mark.asyncio
    async def test_ensure_open_is_idempotent(self, tmp_path: Path):
        """Test ensure_open only sends notification once per file."""
        manager = DocumentManager()
        file_path = tmp_path / "test.py"
        file_path.write_text("x: int = 1")

        mock_lsp = MagicMock()
        mock_lsp.send_notification = AsyncMock()

        # Open twice
        await manager.ensure_open(mock_lsp, file_path)
        await manager.ensure_open(mock_lsp, file_path)

        # Should only send one notification
        assert mock_lsp.send_notification.call_count == 1
        assert manager.open_count == 1

    @pytest.mark.asyncio
    async def test_ensure_open_handles_multiple_files(self, tmp_path: Path):
        """Test ensure_open tracks multiple files."""
        manager = DocumentManager()

        file1 = tmp_path / "file1.py"
        file1.write_text("x: int = 1")
        file2 = tmp_path / "file2.py"
        file2.write_text("y: str = 'hello'")

        mock_lsp = MagicMock()
        mock_lsp.send_notification = AsyncMock()

        await manager.ensure_open(mock_lsp, file1)
        await manager.ensure_open(mock_lsp, file2)

        assert manager.is_open(file1) is True
        assert manager.is_open(file2) is True
        assert manager.open_count == 2
        assert mock_lsp.send_notification.call_count == 2

    @pytest.mark.asyncio
    async def test_close_all_sends_didclose_notifications(self, tmp_path: Path):
        """Test close_all sends didClose for all tracked documents."""
        manager = DocumentManager()

        file1 = tmp_path / "file1.py"
        file1.write_text("x: int = 1")
        file2 = tmp_path / "file2.py"
        file2.write_text("y: str = 'hello'")

        mock_lsp = MagicMock()
        mock_lsp.send_notification = AsyncMock()

        # Open files
        await manager.ensure_open(mock_lsp, file1)
        await manager.ensure_open(mock_lsp, file2)

        # Reset mock to track close calls
        mock_lsp.send_notification.reset_mock()

        # Close all
        await manager.close_all(mock_lsp)

        # Should send didClose for each file
        assert mock_lsp.send_notification.call_count == 2
        for call in mock_lsp.send_notification.call_args_list:
            assert call[0][0] == "textDocument/didClose"

        assert manager.open_count == 0

    @pytest.mark.asyncio
    async def test_close_all_clears_tracking(self, tmp_path: Path):
        """Test close_all clears internal tracking."""
        manager = DocumentManager()
        file_path = tmp_path / "test.py"
        file_path.write_text("x: int = 1")

        mock_lsp = MagicMock()
        mock_lsp.send_notification = AsyncMock()

        await manager.ensure_open(mock_lsp, file_path)
        await manager.close_all(mock_lsp)

        assert manager.is_open(file_path) is False

    def test_clear_removes_tracking_without_notifications(self, tmp_path: Path):
        """Test clear removes tracking without sending notifications."""
        manager = DocumentManager()

        # Manually add to tracking (simulating opened state)
        file_path = (tmp_path / "test.py").resolve()
        manager._opened[file_path] = OpenDocument(
            uri=f"file://{file_path}",
            version=1,
        )

        assert manager.open_count == 1

        # Clear without sending notifications
        manager.clear()

        assert manager.open_count == 0
        assert manager.is_open(file_path) is False

    @pytest.mark.asyncio
    async def test_ensure_open_normalizes_path(self, tmp_path: Path):
        """Test ensure_open normalizes paths for consistent lookup."""
        manager = DocumentManager()

        # Create file
        file_path = tmp_path / "test.py"
        file_path.write_text("x: int = 1")

        mock_lsp = MagicMock()
        mock_lsp.send_notification = AsyncMock()

        # Open with relative-like path
        await manager.ensure_open(mock_lsp, file_path)

        # Check with resolved path
        assert manager.is_open(file_path.resolve()) is True

    @pytest.mark.asyncio
    async def test_ensure_open_raises_for_nonexistent_file(self, tmp_path: Path):
        """Test ensure_open raises FileNotFoundError for missing file."""
        manager = DocumentManager()
        nonexistent = tmp_path / "nonexistent.py"

        mock_lsp = MagicMock()
        mock_lsp.send_notification = AsyncMock()

        with pytest.raises(FileNotFoundError):
            await manager.ensure_open(mock_lsp, nonexistent)

        assert manager.open_count == 0
