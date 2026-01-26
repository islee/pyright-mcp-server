"""Integration tests for Phase 3 multi-workspace features.

Tests end-to-end scenarios including:
- LSP pool management with LRU eviction
- Multi-workspace completions and references
- Per-workspace metrics tracking
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pyright_mcp.backends.lsp_pool import LSPPool
from pyright_mcp.backends.selector import PooledSelector
from pyright_mcp.metrics import MetricsCollector, reset_metrics_collector


@pytest.fixture
def temp_workspaces():
    """Create temporary workspace directories for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)
        workspaces = [
            base_path / "workspace_1",
            base_path / "workspace_2",
            base_path / "workspace_3",
            base_path / "workspace_4",
        ]
        for ws in workspaces:
            ws.mkdir(parents=True)
            # Create a simple Python file in each workspace
            (ws / "test.py").write_text("def hello():\n    pass\n")

        yield workspaces


@pytest.fixture
def reset_metrics():
    """Reset metrics collector before and after each test."""
    reset_metrics_collector()
    yield
    reset_metrics_collector()


class TestLSPPoolMultiWorkspace:
    """Test LSP pool behavior with multiple workspaces."""

    @pytest.mark.asyncio
    async def test_pool_creates_clients_for_new_workspaces(self, temp_workspaces):
        """Test that pool creates a new client for each workspace."""
        pool = LSPPool(max_instances=3)

        # Get clients for first 3 workspaces
        client1 = await pool.get_client(temp_workspaces[0])
        client2 = await pool.get_client(temp_workspaces[1])
        client3 = await pool.get_client(temp_workspaces[2])

        # Verify pool has 3 active instances
        stats = pool.get_pool_stats()
        assert stats["active_instances"] == 3
        assert stats["workspace_switches"] == 3  # 3 cache misses
        assert stats["cache_hit_rate"] == 0.0  # No cache hits yet

        await pool.shutdown_all()

    @pytest.mark.asyncio
    async def test_pool_cache_hits_on_repeated_access(self, temp_workspaces):
        """Test that repeated access to same workspace results in cache hits."""
        pool = LSPPool(max_instances=3)

        # Access workspace 1 multiple times
        client1a = await pool.get_client(temp_workspaces[0])
        client1b = await pool.get_client(temp_workspaces[0])
        client1c = await pool.get_client(temp_workspaces[0])

        # Should be the same instance
        assert client1a is client1b
        assert client1b is client1c

        # Check stats: 1 workspace switch, 2 cache hits
        stats = pool.get_pool_stats()
        assert stats["workspace_switches"] == 1
        assert stats["cache_hit_rate"] == pytest.approx(0.667, abs=0.01)

        await pool.shutdown_all()

    @pytest.mark.asyncio
    async def test_pool_lru_eviction_on_capacity(self, temp_workspaces):
        """Test that LRU eviction happens when pool reaches capacity."""
        pool = LSPPool(max_instances=3)

        # Fill pool with 3 workspaces
        client1 = await pool.get_client(temp_workspaces[0])
        client2 = await pool.get_client(temp_workspaces[1])
        client3 = await pool.get_client(temp_workspaces[2])

        stats = pool.get_pool_stats()
        assert stats["active_instances"] == 3
        assert stats["eviction_count"] == 0

        # Access 4th workspace - should evict workspace 1 (LRU)
        client4 = await pool.get_client(temp_workspaces[3])

        stats = pool.get_pool_stats()
        assert stats["active_instances"] == 3  # Still 3 (one was evicted)
        assert stats["eviction_count"] == 1
        assert len(stats["workspaces"]) == 3
        # Workspace 1 should be evicted
        assert str(temp_workspaces[0]) not in stats["workspaces"]
        # Workspaces 2, 3, 4 should be in pool
        assert str(temp_workspaces[1]) in stats["workspaces"]
        assert str(temp_workspaces[2]) in stats["workspaces"]
        assert str(temp_workspaces[3]) in stats["workspaces"]

        await pool.shutdown_all()

    @pytest.mark.asyncio
    async def test_pool_reinitializes_evicted_workspace(self, temp_workspaces):
        """Test that accessing evicted workspace reinitializes it."""
        pool = LSPPool(max_instances=3)

        # Fill pool
        await pool.get_client(temp_workspaces[0])
        await pool.get_client(temp_workspaces[1])
        await pool.get_client(temp_workspaces[2])

        # Evict workspace 1 by adding workspace 4
        await pool.get_client(temp_workspaces[3])

        # Access workspace 1 again - should reinitialize
        client1_new = await pool.get_client(temp_workspaces[0])

        stats = pool.get_pool_stats()
        assert stats["workspace_switches"] == 4  # 4 cache misses (re-access is a miss)
        assert stats["eviction_count"] == 1
        assert stats["active_instances"] == 3

        await pool.shutdown_all()

    @pytest.mark.asyncio
    async def test_pool_lru_order_updates_on_access(self, temp_workspaces):
        """Test that LRU order updates correctly on repeated access."""
        pool = LSPPool(max_instances=3)

        # Fill pool with 3 workspaces
        await pool.get_client(temp_workspaces[0])  # ws0 is oldest
        await pool.get_client(temp_workspaces[1])  # ws1 is middle
        await pool.get_client(temp_workspaces[2])  # ws2 is newest

        # Access ws0 again - should move to end (making ws1 oldest)
        await pool.get_client(temp_workspaces[0])

        # Add workspace 4 - should evict ws1 (now oldest)
        await pool.get_client(temp_workspaces[3])

        stats = pool.get_pool_stats()
        assert stats["eviction_count"] == 1
        # ws1 should be evicted, not ws0
        assert str(temp_workspaces[1]) not in stats["workspaces"]
        assert str(temp_workspaces[0]) in stats["workspaces"]
        assert str(temp_workspaces[2]) in stats["workspaces"]
        assert str(temp_workspaces[3]) in stats["workspaces"]

        await pool.shutdown_all()


class TestCompletionsMultiWorkspace:
    """Test completions across multiple workspaces."""

    @pytest.mark.asyncio
    async def test_completions_separate_contexts(self, temp_workspaces):
        """Test that completions from different workspaces have separate contexts."""
        from pyright_mcp.tools.completions import get_completions

        pool = LSPPool(max_instances=2)
        selector = PooledSelector(pool=pool)

        # Create a mock completion backend
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "status": "success",
            "items": [{"label": "test", "kind": "function"}],
        }

        # Mock the selector to return our mock backend
        async def mock_get_completion_backend(path):
            backend = AsyncMock()
            backend.complete = AsyncMock(return_value=mock_result)
            return backend

        with patch("pyright_mcp.tools.completions.get_selector", return_value=selector):
            with patch.object(selector, "get_completion_backend", side_effect=mock_get_completion_backend):
                with patch("pyright_mcp.tools.completions.detect_project") as mock_detect:
                    # Create mock projects
                    project1 = MagicMock()
                    project1.root = temp_workspaces[0]
                    project2 = MagicMock()
                    project2.root = temp_workspaces[1]

                    # First completion request
                    mock_detect.side_effect = [project1, project2]
                    result1 = await get_completions(str(temp_workspaces[0] / "test.py"), 1, 1)
                    result2 = await get_completions(str(temp_workspaces[1] / "test.py"), 1, 1)

        assert result1["status"] == "success"
        assert result2["status"] == "success"
        assert pool.get_pool_stats()["active_instances"] == 2

        await pool.shutdown_all()

    @pytest.mark.asyncio
    async def test_completions_with_trigger_character(self, temp_workspaces):
        """Test completions with different trigger characters."""
        from pyright_mcp.tools.completions import get_completions

        pool = LSPPool()
        selector = PooledSelector(pool=pool)

        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "status": "success",
            "items": [],
        }

        async def mock_get_completion_backend(path):
            backend = AsyncMock()
            backend.complete = AsyncMock(return_value=mock_result)
            return backend

        with patch("pyright_mcp.tools.completions.get_selector", return_value=selector):
            with patch.object(selector, "get_completion_backend", side_effect=mock_get_completion_backend):
                with patch("pyright_mcp.tools.completions.detect_project") as mock_detect:
                    project = MagicMock()
                    project.root = temp_workspaces[0]
                    mock_detect.return_value = project

                    result = await get_completions(
                        str(temp_workspaces[0] / "test.py"),
                        1,
                        1,
                        trigger_character=".",
                    )

        assert result["status"] == "success"

        await pool.shutdown_all()


class TestReferencesMultiWorkspace:
    """Test references across multiple workspaces."""

    @pytest.mark.asyncio
    async def test_references_separate_contexts(self, temp_workspaces):
        """Test that references from different workspaces have separate contexts."""
        from pyright_mcp.tools.references import find_references

        pool = LSPPool(max_instances=2)
        selector = PooledSelector(pool=pool)

        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "status": "success",
            "references": [],
            "count": 0,
        }

        async def mock_get_references_backend(path):
            backend = AsyncMock()
            backend.references = AsyncMock(return_value=mock_result)
            return backend

        with patch("pyright_mcp.tools.references.get_selector", return_value=selector):
            with patch.object(selector, "get_references_backend", side_effect=mock_get_references_backend):
                with patch("pyright_mcp.tools.references.detect_project") as mock_detect:
                    project1 = MagicMock()
                    project1.root = temp_workspaces[0]
                    project2 = MagicMock()
                    project2.root = temp_workspaces[1]

                    mock_detect.side_effect = [project1, project2]
                    result1 = await find_references(str(temp_workspaces[0] / "test.py"), 1, 1)
                    result2 = await find_references(str(temp_workspaces[1] / "test.py"), 1, 1)

        assert result1["status"] == "success"
        assert result2["status"] == "success"
        assert pool.get_pool_stats()["active_instances"] == 2

        await pool.shutdown_all()


class TestMetricsTracking:
    """Test per-workspace metrics tracking."""

    @pytest.mark.asyncio
    async def test_metrics_tracked_per_workspace(self, reset_metrics):
        """Test that metrics are tracked separately for each workspace."""
        metrics_collector = MetricsCollector()

        ws1 = Path("/workspace1")
        ws2 = Path("/workspace2")

        # Record operations for workspace 1
        await metrics_collector.record(ws1, "hover", 25.5, True)
        await metrics_collector.record(ws1, "definition", 35.2, True)
        await metrics_collector.record(ws1, "hover", 20.0, True)

        # Record operations for workspace 2
        await metrics_collector.record(ws2, "completion", 45.0, True)
        await metrics_collector.record(ws2, "references", 50.0, False)

        # Get metrics
        all_metrics = metrics_collector.get_all_metrics()
        assert len(all_metrics) == 2

        # Find metrics for each workspace
        ws1_metrics = next((m for m in all_metrics if m.workspace_root == ws1), None)
        ws2_metrics = next((m for m in all_metrics if m.workspace_root == ws2), None)

        assert ws1_metrics is not None
        assert ws2_metrics is not None

        # Check workspace 1 metrics
        assert ws1_metrics.hover_count == 2
        assert ws1_metrics.definition_count == 1
        assert ws1_metrics.completion_count == 0
        assert ws1_metrics.references_count == 0
        assert ws1_metrics.hover_errors == 0
        assert pytest.approx(ws1_metrics.avg_hover_ms(), abs=0.1) == 22.75

        # Check workspace 2 metrics
        assert ws2_metrics.hover_count == 0
        assert ws2_metrics.definition_count == 0
        assert ws2_metrics.completion_count == 1
        assert ws2_metrics.references_count == 1
        assert ws2_metrics.hover_errors == 0
        assert ws2_metrics.references_errors == 1

    @pytest.mark.asyncio
    async def test_metrics_in_health_check_response(self, reset_metrics, temp_workspaces):
        """Test that metrics appear in health_check response for PooledSelector."""
        from pyright_mcp.tools.health_check import health_check

        pool = LSPPool()
        selector = PooledSelector(pool=pool)

        # Create metrics
        metrics_collector = MetricsCollector()
        await metrics_collector.record(
            temp_workspaces[0],
            "hover",
            25.0,
            True,
        )
        await metrics_collector.record(
            temp_workspaces[1],
            "completion",
            40.0,
            True,
        )

        # Mock subprocess
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"pyright 1.1.350\n", b""))

        with patch("pyright_mcp.tools.health_check.asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("pyright_mcp.tools.health_check.get_selector", return_value=selector):
                with patch(
                    "pyright_mcp.tools.health_check.get_metrics_collector",
                    return_value=metrics_collector,
                ):
                    result = await health_check()

        assert "metrics" in result
        assert "workspaces" in result["metrics"]
        assert len(result["metrics"]["workspaces"]) == 2

        # Verify metrics content
        workspaces_metrics = result["metrics"]["workspaces"]
        assert any(m["workspace"] == str(temp_workspaces[0]) for m in workspaces_metrics)
        assert any(m["workspace"] == str(temp_workspaces[1]) for m in workspaces_metrics)

        await pool.shutdown_all()

    @pytest.mark.asyncio
    async def test_metrics_calculate_averages_correctly(self, reset_metrics):
        """Test that metrics correctly calculate operation averages."""
        metrics_collector = MetricsCollector()

        ws = Path("/workspace")

        # Record multiple operations with different durations
        await metrics_collector.record(ws, "hover", 10.0, True)
        await metrics_collector.record(ws, "hover", 20.0, True)
        await metrics_collector.record(ws, "hover", 30.0, True)

        metrics = metrics_collector.get_workspace_metrics(ws)
        assert metrics is not None
        assert metrics.hover_count == 3
        assert metrics.avg_hover_ms() == 20.0  # (10 + 20 + 30) / 3

    @pytest.mark.asyncio
    async def test_metrics_track_error_rates(self, reset_metrics):
        """Test that metrics correctly track error rates per operation."""
        metrics_collector = MetricsCollector()

        ws = Path("/workspace")

        # Record some successful and failing operations
        await metrics_collector.record(ws, "definition", 10.0, True)
        await metrics_collector.record(ws, "definition", 15.0, False)
        await metrics_collector.record(ws, "definition", 12.0, True)

        metrics = metrics_collector.get_workspace_metrics(ws)
        assert metrics is not None
        assert metrics.definition_count == 3
        assert metrics.definition_errors == 1


class TestMetricsIntegration:
    """Integration tests for metrics with actual tool execution."""

    @pytest.mark.asyncio
    async def test_hover_records_metrics(self, reset_metrics, temp_workspaces):
        """Test that get_hover records metrics for operations."""
        from pyright_mcp.tools.hover import get_hover

        metrics_collector = MetricsCollector()

        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "status": "success",
            "symbol": "test",
            "type": "str",
        }

        async def mock_get_hover_backend(path):
            backend = AsyncMock()
            backend.hover = AsyncMock(return_value=mock_result)
            return backend

        selector = PooledSelector()
        with patch("pyright_mcp.tools.hover.get_selector", return_value=selector):
            with patch.object(selector, "get_hover_backend", side_effect=mock_get_hover_backend):
                with patch("pyright_mcp.tools.hover.detect_project") as mock_detect:
                    project = MagicMock()
                    project.root = temp_workspaces[0]
                    mock_detect.return_value = project
                    with patch(
                        "pyright_mcp.tools.hover.get_metrics_collector",
                        return_value=metrics_collector,
                    ):
                        result = await get_hover(str(temp_workspaces[0] / "test.py"), 1, 1)

        assert result["status"] == "success"

        # Verify metrics were recorded
        metrics = metrics_collector.get_workspace_metrics(temp_workspaces[0])
        assert metrics is not None
        assert metrics.hover_count == 1
        assert metrics.hover_errors == 0

        await selector.shutdown_all()

    @pytest.mark.asyncio
    async def test_definition_records_metrics(self, reset_metrics, temp_workspaces):
        """Test that go_to_definition records metrics for operations."""
        from pyright_mcp.tools.definition import go_to_definition

        metrics_collector = MetricsCollector()

        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "status": "success",
            "definitions": [],
        }

        async def mock_get_definition_backend(path):
            backend = AsyncMock()
            backend.definition = AsyncMock(return_value=mock_result)
            return backend

        selector = PooledSelector()
        with patch("pyright_mcp.tools.definition.get_selector", return_value=selector):
            with patch.object(selector, "get_definition_backend", side_effect=mock_get_definition_backend):
                with patch("pyright_mcp.tools.definition.detect_project") as mock_detect:
                    project = MagicMock()
                    project.root = temp_workspaces[0]
                    mock_detect.return_value = project
                    with patch(
                        "pyright_mcp.tools.definition.get_metrics_collector",
                        return_value=metrics_collector,
                    ):
                        result = await go_to_definition(str(temp_workspaces[0] / "test.py"), 1, 1)

        assert result["status"] == "success"

        # Verify metrics were recorded
        metrics = metrics_collector.get_workspace_metrics(temp_workspaces[0])
        assert metrics is not None
        assert metrics.definition_count == 1
        assert metrics.definition_errors == 0

        await selector.shutdown_all()
