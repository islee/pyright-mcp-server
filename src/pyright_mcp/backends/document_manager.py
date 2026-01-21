"""Document lifecycle management for LSP client.

Tracks opened documents with didOpen/didClose notifications to ensure
proper LSP document synchronization. This is necessary because LSP requires
explicit document lifecycle management.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ..logging_config import get_logger
from ..utils.uri import path_to_uri

if TYPE_CHECKING:
    from .lsp_client import LSPClient

logger = get_logger("backends.document_manager")


@dataclass
class OpenDocument:
    """Tracked state of an opened document.

    Attributes:
        uri: LSP document URI (file:// format)
        version: Document version number (increments on changes)
        opened_at: Timestamp when document was opened
    """

    uri: str
    version: int
    opened_at: float = field(default_factory=time.time)


class DocumentManager:
    """Track opened documents for LSP lifecycle management.

    This class ensures that:
    - Documents are opened with didOpen before any LSP requests
    - Each document is opened only once (idempotent)
    - All documents can be closed on shutdown or workspace change

    Usage:
        manager = DocumentManager()
        await manager.ensure_open(lsp_client, file_path)
        # Now safe to make LSP requests for this file
    """

    def __init__(self) -> None:
        """Initialize document manager with empty tracking."""
        self._opened: dict[Path, OpenDocument] = {}

    def is_open(self, path: Path) -> bool:
        """Check if a document is currently tracked as open.

        Args:
            path: File path to check

        Returns:
            True if document is open, False otherwise
        """
        # Normalize path for consistent lookup
        normalized = path.resolve()
        return normalized in self._opened

    async def ensure_open(self, lsp: LSPClient, path: Path) -> None:
        """Ensure a document is open in the LSP server.

        If the document is already open, this is a no-op.
        Otherwise, reads the file content and sends didOpen notification.

        Args:
            lsp: LSP client to send notification to
            path: Path to the file to open

        Raises:
            FileNotFoundError: If file doesn't exist
            OSError: If file cannot be read
        """
        # Normalize path
        normalized = path.resolve()

        # Skip if already open
        if normalized in self._opened:
            logger.debug(f"Document already open: {normalized}")
            return

        # Read file content
        content = normalized.read_text(encoding="utf-8")
        uri = path_to_uri(normalized)

        logger.info(f"Opening document: {normalized}")

        # Send didOpen notification
        await lsp.send_notification(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": "python",
                    "version": 1,
                    "text": content,
                }
            },
        )

        # Track as opened
        self._opened[normalized] = OpenDocument(
            uri=uri,
            version=1,
        )

    async def close_all(self, lsp: LSPClient) -> None:
        """Close all tracked documents in the LSP server.

        Sends didClose notification for each tracked document.
        Call this on LSP shutdown or workspace change.

        Args:
            lsp: LSP client to send notifications to
        """
        logger.info(f"Closing {len(self._opened)} document(s)")

        for path, doc in self._opened.items():
            logger.debug(f"Closing document: {path}")
            await lsp.send_notification(
                "textDocument/didClose",
                {"textDocument": {"uri": doc.uri}},
            )

        self._opened.clear()

    def clear(self) -> None:
        """Clear tracking without sending notifications.

        Use this after LSP crash when the server has lost state
        and didClose notifications would fail.
        """
        count = len(self._opened)
        self._opened.clear()
        logger.info(f"Cleared {count} document(s) from tracking (no notifications)")

    @property
    def open_count(self) -> int:
        """Number of currently tracked open documents."""
        return len(self._opened)
