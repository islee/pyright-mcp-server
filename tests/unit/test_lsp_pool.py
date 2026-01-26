"""Tests for LSP client pooling."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pyright_mcp.backends.lsp_pool import LSPPool


@pytest.fixture
def mock_lsp_client():
    """Create a mock LSP client."""
    client = AsyncMock()
    client.shutdown = AsyncMock()
    return client


@pytest.fixture
def pool():
    """Create an LSP pool with small size for testing."""
    return LSPPool(max_instances=3)


class TestLSPPool:
    """Test LSP pool functionality."""

    @pytest.mark.asyncio
    async def test_pool_initialization(self):
        """Test LSP pool initializes correctly."""
        pool = LSPPool(max_instances=2)

        assert pool._max_instances == 2
        assert len(pool._clients) == 0
        assert pool._access_order == []
        assert pool._stats["evictions"] == 0
        assert pool._stats["workspace_switches"] == 0
        assert pool._stats["cache_hits"] == 0

    @pytest.mark.asyncio
    async def test_pool_create_on_demand(self, pool):
        """Test pool creates clients on demand."""
        ws1 = Path("/workspace1")

        client1 = await pool.get_client(ws1)

        assert client1 is not None
        assert ws1 in pool._clients
        assert len(pool._clients) == 1

    @pytest.mark.asyncio
    async def test_pool_cache_hit(self, pool):
        """Test pool returns same client for same workspace."""
        ws1 = Path("/workspace1")

        client1 = await pool.get_client(ws1)
        client2 = await pool.get_client(ws1)

        assert client1 is client2
        assert pool._stats["cache_hits"] == 1
        assert pool._stats["workspace_switches"] == 1  # Initial creation

    @pytest.mark.asyncio
    async def test_pool_workspace_switch(self, pool):
        """Test pool tracks workspace switches."""
        ws1 = Path("/workspace1")
        ws2 = Path("/workspace2")

        await pool.get_client(ws1)
        await pool.get_client(ws2)

        assert pool._stats["workspace_switches"] == 2
        assert pool._stats["cache_hits"] == 0

    @pytest.mark.asyncio
    async def test_pool_lru_eviction(self, pool):
        """Test pool evicts least recently used client."""
        ws1 = Path("/workspace1")
        ws2 = Path("/workspace2")
        ws3 = Path("/workspace3")
        ws4 = Path("/workspace4")

        # Fill pool to capacity
        await pool.get_client(ws1)
        await pool.get_client(ws2)
        await pool.get_client(ws3)

        assert len(pool._clients) == 3

        # Request new workspace - should evict ws1 (least recently used)
        with patch(
            "pyright_mcp.backends.lsp_client.LSPClient.shutdown", new_callable=AsyncMock
        ):
            await pool.get_client(ws4)

        assert len(pool._clients) == 3
        assert ws1 not in pool._clients
        assert ws4 in pool._clients
        assert pool._stats["evictions"] == 1

    @pytest.mark.asyncio
    async def test_pool_lru_order(self, pool):
        """Test pool maintains correct LRU order."""
        ws1 = Path("/workspace1")
        ws2 = Path("/workspace2")
        ws3 = Path("/workspace3")

        await pool.get_client(ws1)
        await pool.get_client(ws2)
        await pool.get_client(ws3)

        # Access ws1 again - should move to end
        await pool.get_client(ws1)

        # Expected order: ws2, ws3, ws1 (oldest to newest)
        assert pool._access_order == [ws2, ws3, ws1]

    @pytest.mark.asyncio
    async def test_pool_shutdown_all(self, pool):
        """Test pool shutdown closes all clients."""
        ws1 = Path("/workspace1")
        ws2 = Path("/workspace2")

        with patch(
            "pyright_mcp.backends.lsp_client.LSPClient.shutdown", new_callable=AsyncMock
        ):
            client1 = await pool.get_client(ws1)
            client2 = await pool.get_client(ws2)

            await pool.shutdown_all()

            assert len(pool._clients) == 0
            assert pool._access_order == []

    @pytest.mark.asyncio
    async def test_pool_stats_basic(self, pool):
        """Test pool statistics reporting."""
        ws1 = Path("/workspace1")

        await pool.get_client(ws1)
        stats = pool.get_pool_stats()

        assert stats["active_instances"] == 1
        assert stats["max_instances"] == 3
        assert stats["cache_hit_rate"] == 0.0
        assert stats["eviction_count"] == 0
        assert stats["workspace_switches"] == 1
        assert ws1.as_posix() in stats["workspaces"]

    @pytest.mark.asyncio
    async def test_pool_stats_cache_hit_rate(self, pool):
        """Test cache hit rate calculation."""
        ws1 = Path("/workspace1")

        await pool.get_client(ws1)
        await pool.get_client(ws1)
        await pool.get_client(ws1)

        stats = pool.get_pool_stats()

        # 1 switch, 2 hits
        assert stats["workspace_switches"] == 1
        expected_hit_rate = 2.0 / 3.0
        assert abs(stats["cache_hit_rate"] - expected_hit_rate) < 0.01

    @pytest.mark.asyncio
    async def test_pool_concurrent_access(self, pool):
        """Test pool handles concurrent access safely."""
        ws = Path("/workspace")

        # Create multiple concurrent requests for same workspace
        tasks = [pool.get_client(ws) for _ in range(10)]
        clients = await asyncio.gather(*tasks)

        # All should get same client
        assert all(c is clients[0] for c in clients)
        assert len(pool._clients) == 1

    @pytest.mark.asyncio
    async def test_pool_max_instances_from_env(self, monkeypatch):
        """Test pool size can be set via environment variable."""
        monkeypatch.setenv("PYRIGHT_MCP_LSP_POOL_SIZE", "5")

        # Reset config to pick up env var
        from pyright_mcp.config import reset_config

        reset_config()

        pool = LSPPool()
        assert pool._max_instances == 5

    @pytest.mark.asyncio
    async def test_pool_with_custom_timeout(self):
        """Test pool passes timeout to LSP clients."""
        pool = LSPPool(max_instances=2, idle_timeout=60.0)

        ws = Path("/workspace")

        # Get client - it will be created with the pool's timeout
        client = await pool.get_client(ws)

        # Verify client was created
        assert client is not None
        assert client.config.lsp_timeout == 60.0

    @pytest.mark.asyncio
    async def test_pool_graceful_eviction_error(self, pool):
        """Test pool handles shutdown errors gracefully."""
        ws1 = Path("/workspace1")
        ws2 = Path("/workspace2")
        ws3 = Path("/workspace3")
        ws4 = Path("/workspace4")

        await pool.get_client(ws1)
        await pool.get_client(ws2)
        await pool.get_client(ws3)

        # Patch shutdown to fail for ws1
        original_shutdown = pool._clients[ws1].shutdown

        async def failing_shutdown():
            raise RuntimeError("Shutdown failed")

        pool._clients[ws1].shutdown = failing_shutdown

        # Pool should handle the error and evict anyway
        with patch(
            "pyright_mcp.backends.lsp_client.LSPClient.shutdown", new_callable=AsyncMock
        ):
            await pool.get_client(ws4)

        # Should still evict despite error
        assert ws1 not in pool._clients
        assert pool._stats["evictions"] == 1
