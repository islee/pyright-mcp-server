"""Backend selector for choosing between CLI and LSP backends."""

from abc import ABC, abstractmethod
from pathlib import Path

from .base import Backend


class BackendSelector(ABC):
    """Abstract base for selecting appropriate backend."""

    @abstractmethod
    async def get_backend(self, path: Path) -> Backend:
        """
        Get the appropriate backend for the given path.

        Args:
            path: File or directory being analyzed

        Returns:
            Backend instance to use for operations
        """
        ...

    @abstractmethod
    async def shutdown_all(self) -> None:
        """Shutdown all managed backends."""
        ...


class CLIOnlySelector(BackendSelector):
    """Phase 1 selector - always uses CLI backend.

    This selector is used in Phase 1 when only the CLI backend is available.
    In Phase 2, this will be replaced with a smarter selector that can choose
    between CLI and LSP backends based on context.
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

    async def shutdown_all(self) -> None:
        """Shutdown all backends.

        Phase 1: CLI backend is stateless, no cleanup needed.
        """
        pass  # CLI backend is stateless
