"""Tests for backend selector."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pyright_mcp.backends.cli_runner import PyrightCLIRunner
from pyright_mcp.backends.selector import (
    CLIOnlySelector,
    HybridSelector,
    get_selector,
    reset_selector,
)


class TestCLIOnlySelector:
    """Tests for CLIOnlySelector (Phase 1)."""

    def test_cli_only_selector_initialization(self):
        """Test CLIOnlySelector creates CLI backend."""
        selector = CLIOnlySelector()
        assert hasattr(selector, "_cli")
        assert isinstance(selector._cli, PyrightCLIRunner)

    @pytest.mark.asyncio
    async def test_cli_only_selector_get_backend(self, tmp_path: Path):
        """Test get_backend returns CLI backend."""
        selector = CLIOnlySelector()
        backend = await selector.get_backend(tmp_path)
        assert isinstance(backend, PyrightCLIRunner)

    @pytest.mark.asyncio
    async def test_cli_only_selector_get_hover_backend_raises(self, tmp_path: Path):
        """Test get_hover_backend raises NotImplementedError."""
        selector = CLIOnlySelector()
        with pytest.raises(NotImplementedError):
            await selector.get_hover_backend(tmp_path)

    @pytest.mark.asyncio
    async def test_cli_only_selector_get_definition_backend_raises(self, tmp_path: Path):
        """Test get_definition_backend raises NotImplementedError."""
        selector = CLIOnlySelector()
        with pytest.raises(NotImplementedError):
            await selector.get_definition_backend(tmp_path)

    @pytest.mark.asyncio
    async def test_cli_only_selector_shutdown_all(self):
        """Test shutdown_all is safe (CLI is stateless)."""
        selector = CLIOnlySelector()
        # Should not raise
        await selector.shutdown_all()


class TestHybridSelector:
    """Tests for HybridSelector (Phase 2)."""

    def test_hybrid_selector_initialization(self):
        """Test HybridSelector creates CLI backend, LSP is None."""
        selector = HybridSelector()
        assert hasattr(selector, "_cli")
        assert isinstance(selector._cli, PyrightCLIRunner)
        assert selector._lsp is None

    @pytest.mark.asyncio
    async def test_hybrid_selector_get_backend_returns_cli(self, tmp_path: Path):
        """Test get_backend returns CLI backend for type checking."""
        selector = HybridSelector()
        backend = await selector.get_backend(tmp_path)
        assert isinstance(backend, PyrightCLIRunner)

    @pytest.mark.asyncio
    async def test_hybrid_selector_get_hover_backend_lazy_loads_lsp(self, tmp_path: Path):
        """Test get_hover_backend lazily creates LSP client."""
        selector = HybridSelector()
        assert selector._lsp is None

        backend = await selector.get_hover_backend(tmp_path)

        # LSP client should now be created
        assert selector._lsp is not None
        assert backend is selector._lsp

    @pytest.mark.asyncio
    async def test_hybrid_selector_get_definition_backend_lazy_loads_lsp(self, tmp_path: Path):
        """Test get_definition_backend lazily creates LSP client."""
        selector = HybridSelector()
        assert selector._lsp is None

        backend = await selector.get_definition_backend(tmp_path)

        # LSP client should now be created
        assert selector._lsp is not None
        assert backend is selector._lsp

    @pytest.mark.asyncio
    async def test_hybrid_selector_reuses_lsp_client(self, tmp_path: Path):
        """Test HybridSelector reuses same LSP client."""
        selector = HybridSelector()

        hover_backend = await selector.get_hover_backend(tmp_path)
        definition_backend = await selector.get_definition_backend(tmp_path)

        # Should be the same instance
        assert hover_backend is definition_backend

    @pytest.mark.asyncio
    async def test_hybrid_selector_shutdown_all_with_lsp(self, tmp_path: Path):
        """Test shutdown_all shuts down LSP client."""
        selector = HybridSelector()

        # Force LSP creation
        await selector.get_hover_backend(tmp_path)
        assert selector._lsp is not None

        # Save reference before shutdown
        lsp_client = selector._lsp

        # Mock the shutdown method
        lsp_client.shutdown = AsyncMock()

        await selector.shutdown_all()

        # Verify shutdown was called
        lsp_client.shutdown.assert_called_once()
        # After shutdown, _lsp should be None
        assert selector._lsp is None

    @pytest.mark.asyncio
    async def test_hybrid_selector_shutdown_all_without_lsp(self):
        """Test shutdown_all is safe when LSP not initialized."""
        selector = HybridSelector()
        # Should not raise
        await selector.shutdown_all()


class TestGetSelector:
    """Tests for get_selector singleton function."""

    def test_get_selector_returns_hybrid_selector(self):
        """Test get_selector returns HybridSelector."""
        reset_selector()
        selector = get_selector()
        assert isinstance(selector, HybridSelector)

    def test_get_selector_is_singleton(self):
        """Test get_selector returns same instance."""
        reset_selector()
        selector1 = get_selector()
        selector2 = get_selector()
        assert selector1 is selector2

    def test_reset_selector_clears_singleton(self):
        """Test reset_selector clears the singleton."""
        reset_selector()
        selector1 = get_selector()
        reset_selector()
        selector2 = get_selector()
        assert selector1 is not selector2
