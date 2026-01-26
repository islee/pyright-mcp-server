"""Backend selector for choosing between CLI and LSP backends.

Phase 1: CLI-only selector for type checking
Phase 2: Hybrid selector with CLI for type checking, LSP for hover/definition
Phase 3: Pooled selector with multi-workspace LSP pooling
"""

from abc import ABC, abstractmethod
from pathlib import Path

from .base import Backend, CompletionBackend, DefinitionBackend, HoverBackend, ReferencesBackend


class BackendSelector(ABC):
    """Abstract base for selecting appropriate backend."""

    @abstractmethod
    async def get_backend(self, path: Path) -> Backend:
        """
        Get the appropriate backend for type checking.

        Args:
            path: File or directory being analyzed

        Returns:
            Backend instance for check operations
        """
        ...

    @abstractmethod
    async def get_hover_backend(self, path: Path) -> HoverBackend:
        """
        Get backend for hover operations.

        Args:
            path: File being analyzed

        Returns:
            HoverBackend instance
        """
        ...

    @abstractmethod
    async def get_definition_backend(self, path: Path) -> DefinitionBackend:
        """
        Get backend for definition operations.

        Args:
            path: File being analyzed

        Returns:
            DefinitionBackend instance
        """
        ...

    @abstractmethod
    async def get_completion_backend(self, path: Path) -> CompletionBackend:
        """
        Get backend for completion operations.

        Args:
            path: File being analyzed

        Returns:
            CompletionBackend instance
        """
        ...

    @abstractmethod
    async def get_references_backend(self, path: Path) -> ReferencesBackend:
        """
        Get backend for references operations.

        Args:
            path: File being analyzed

        Returns:
            ReferencesBackend instance
        """
        ...

    @abstractmethod
    async def shutdown_all(self) -> None:
        """Shutdown all managed backends."""
        ...


class CLIOnlySelector(BackendSelector):
    """Phase 1 selector - always uses CLI backend.

    This selector is used in Phase 1 when only the CLI backend is available.
    It raises NotImplementedError for hover/definition operations.
    """

    def __init__(self) -> None:
        """Initialize with CLI backend."""
        from .cli_runner import PyrightCLIRunner

        self._cli = PyrightCLIRunner()

    async def get_backend(self, path: Path) -> Backend:
        """
        Return the CLI backend.

        Args:
            path: File or directory being analyzed (unused in Phase 1)

        Returns:
            PyrightCLIRunner instance
        """
        return self._cli

    async def get_hover_backend(self, path: Path) -> HoverBackend:
        """Not available in CLI-only mode."""
        raise NotImplementedError("Hover not available in CLI-only mode")

    async def get_definition_backend(self, path: Path) -> DefinitionBackend:
        """Not available in CLI-only mode."""
        raise NotImplementedError("Definition not available in CLI-only mode")

    async def get_completion_backend(self, path: Path) -> CompletionBackend:
        """Not available in CLI-only mode."""
        raise NotImplementedError("Completion not available in CLI-only mode")

    async def get_references_backend(self, path: Path) -> ReferencesBackend:
        """Not available in CLI-only mode."""
        raise NotImplementedError("References not available in CLI-only mode")

    async def shutdown_all(self) -> None:
        """Shutdown all backends.

        Phase 1: CLI backend is stateless, no cleanup needed.
        """
        # CLI backend is stateless


class HybridSelector(BackendSelector):
    """Phase 2 selector - CLI for type checking, LSP for hover/definition.

    This selector uses:
    - CLI backend for check_types (synchronous, reliable)
    - LSP client for get_hover, go_to_definition (interactive, stateful)

    The LSP client is lazily initialized on first hover/definition request
    and automatically shuts down after idle timeout.
    """

    def __init__(self) -> None:
        """Initialize with CLI backend; LSP client is lazy-loaded."""
        from .cli_runner import PyrightCLIRunner

        self._cli = PyrightCLIRunner()
        self._lsp: LSPClient | None = None

    def _get_lsp(self) -> "LSPClient":
        """Get or create LSP client instance (lazy initialization)."""
        if self._lsp is None:
            from .lsp_client import LSPClient

            self._lsp = LSPClient()
        return self._lsp

    async def get_backend(self, path: Path) -> Backend:
        """
        Return CLI backend for type checking.

        Args:
            path: File or directory being analyzed

        Returns:
            PyrightCLIRunner instance
        """
        return self._cli

    async def get_hover_backend(self, path: Path) -> HoverBackend:
        """
        Return LSP client for hover operations.

        Args:
            path: File being analyzed

        Returns:
            LSPClient instance
        """
        return self._get_lsp()

    async def get_definition_backend(self, path: Path) -> DefinitionBackend:
        """
        Return LSP client for definition operations.

        Args:
            path: File being analyzed

        Returns:
            LSPClient instance
        """
        return self._get_lsp()

    async def get_completion_backend(self, path: Path) -> CompletionBackend:
        """
        Return LSP client for completion operations.

        Args:
            path: File being analyzed

        Returns:
            LSPClient instance
        """
        return self._get_lsp()

    async def get_references_backend(self, path: Path) -> ReferencesBackend:
        """
        Return LSP client for references operations.

        Args:
            path: File being analyzed

        Returns:
            LSPClient instance
        """
        return self._get_lsp()

    async def shutdown_all(self) -> None:
        """Shutdown all backends.

        Shuts down LSP client if initialized. CLI backend is stateless.
        """
        if self._lsp is not None:
            await self._lsp.shutdown()
            self._lsp = None


class PooledSelector(BackendSelector):
    """Phase 3 selector - CLI for type checking, pooled LSP for IDE features.

    This selector uses:
    - CLI backend for check_types (synchronous, reliable)
    - LSP pool for hover, definition, completion, references (multi-workspace)

    The LSP pool maintains up to N clients (configurable, default 3) with LRU
    eviction for multi-workspace support. This enables efficient handling of
    multiple workspaces without unbounded resource growth.
    """

    def __init__(self, pool: "LSPPool" | None = None) -> None:
        """Initialize with CLI backend and optional LSP pool.

        Args:
            pool: LSPPool instance (creates default if not provided)
        """
        from .cli_runner import PyrightCLIRunner
        from .lsp_pool import LSPPool

        self._cli = PyrightCLIRunner()
        self._pool = pool or LSPPool()

    async def get_backend(self, path: Path) -> Backend:
        """
        Return CLI backend for type checking.

        Args:
            path: File or directory being analyzed

        Returns:
            PyrightCLIRunner instance
        """
        return self._cli

    async def get_hover_backend(self, path: Path) -> HoverBackend:
        """
        Return pooled LSP client for hover operations.

        Args:
            path: File being analyzed

        Returns:
            LSPClient from pool
        """
        # In Phase 3, we need context to determine workspace
        # For now, use parent directory as heuristic
        workspace = path.parent if path.is_file() else path
        return await self._pool.get_client(workspace)

    async def get_definition_backend(self, path: Path) -> DefinitionBackend:
        """
        Return pooled LSP client for definition operations.

        Args:
            path: File being analyzed

        Returns:
            LSPClient from pool
        """
        workspace = path.parent if path.is_file() else path
        return await self._pool.get_client(workspace)

    async def get_completion_backend(self, path: Path) -> CompletionBackend:
        """
        Return pooled LSP client for completion operations.

        Args:
            path: File being analyzed

        Returns:
            LSPClient from pool
        """
        workspace = path.parent if path.is_file() else path
        return await self._pool.get_client(workspace)

    async def get_references_backend(self, path: Path) -> ReferencesBackend:
        """
        Return pooled LSP client for references operations.

        Args:
            path: File being analyzed

        Returns:
            LSPClient from pool
        """
        workspace = path.parent if path.is_file() else path
        return await self._pool.get_client(workspace)

    async def shutdown_all(self) -> None:
        """Shutdown all backends.

        Shuts down all LSP clients in the pool. CLI backend is stateless.
        """
        await self._pool.shutdown_all()


# Import for type checking only
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .lsp_pool import LSPPool


# Singleton selector instance
_selector: BackendSelector | None = None


def get_selector() -> BackendSelector:
    """Get the singleton backend selector.

    Returns HybridSelector for Phase 2 (CLI + LSP).

    Returns:
        BackendSelector instance
    """
    global _selector
    if _selector is None:
        _selector = HybridSelector()
    return _selector


def reset_selector() -> None:
    """Reset the singleton selector (for testing only)."""
    global _selector
    _selector = None
