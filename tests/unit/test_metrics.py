"""Tests for metrics collection infrastructure."""

import asyncio
from pathlib import Path

import pytest

from pyright_mcp.metrics import MetricsCollector, WorkspaceMetrics


@pytest.fixture
def metrics_collector():
    """Create a fresh metrics collector for each test."""
    return MetricsCollector()


@pytest.fixture
def workspace_path():
    """Return a test workspace path."""
    return Path("/workspace/test")


class TestWorkspaceMetrics:
    """Test WorkspaceMetrics data structure."""

    def test_workspace_metrics_initialization(self, workspace_path):
        """Test WorkspaceMetrics initializes with zeros."""
        metrics = WorkspaceMetrics(workspace_root=workspace_path)

        assert metrics.workspace_root == workspace_path
        assert metrics.hover_count == 0
        assert metrics.definition_count == 0
        assert metrics.completion_count == 0
        assert metrics.references_count == 0
        assert metrics.hover_times == []
        assert metrics.definition_times == []
        assert metrics.completion_times == []
        assert metrics.references_times == []
        assert metrics.hover_errors == 0
        assert metrics.definition_errors == 0
        assert metrics.completion_errors == 0
        assert metrics.references_errors == 0

    def test_avg_hover_ms_empty(self, workspace_path):
        """Test average hover latency with no data."""
        metrics = WorkspaceMetrics(workspace_root=workspace_path)
        assert metrics.avg_hover_ms() == 0.0

    def test_avg_hover_ms_with_data(self, workspace_path):
        """Test average hover latency calculation."""
        metrics = WorkspaceMetrics(workspace_root=workspace_path)
        metrics.hover_times = [100.0, 200.0, 300.0]
        assert metrics.avg_hover_ms() == 200.0

    def test_avg_definition_ms(self, workspace_path):
        """Test average definition latency calculation."""
        metrics = WorkspaceMetrics(workspace_root=workspace_path)
        metrics.definition_times = [50.0, 150.0]
        assert metrics.avg_definition_ms() == 100.0

    def test_avg_completion_ms(self, workspace_path):
        """Test average completion latency calculation."""
        metrics = WorkspaceMetrics(workspace_root=workspace_path)
        metrics.completion_times = [75.0, 125.0]
        assert metrics.avg_completion_ms() == 100.0

    def test_avg_references_ms(self, workspace_path):
        """Test average references latency calculation."""
        metrics = WorkspaceMetrics(workspace_root=workspace_path)
        metrics.references_times = [60.0, 140.0]
        assert metrics.avg_references_ms() == 100.0

    def test_to_dict(self, workspace_path):
        """Test conversion to dictionary."""
        metrics = WorkspaceMetrics(workspace_root=workspace_path)
        metrics.hover_count = 10
        metrics.hover_times = [100.0, 110.0]
        metrics.hover_errors = 1
        metrics.definition_count = 5
        metrics.completion_count = 0

        result = metrics.to_dict()

        assert result["workspace"] == str(workspace_path)
        assert result["operations"]["hover"]["count"] == 10
        assert result["operations"]["hover"]["avg_ms"] == 105.0
        assert result["operations"]["hover"]["errors"] == 1
        assert result["operations"]["definition"]["count"] == 5
        assert result["operations"]["completion"]["count"] == 0


class TestMetricsCollector:
    """Test MetricsCollector functionality."""

    @pytest.mark.asyncio
    async def test_collector_initialization(self, metrics_collector):
        """Test MetricsCollector initializes with no metrics."""
        assert metrics_collector.get_all_metrics() == []
        assert metrics_collector.get_workspace_metrics(Path("/workspace")) is None
        assert metrics_collector.uptime_seconds() > 0

    @pytest.mark.asyncio
    async def test_record_hover_success(self, metrics_collector, workspace_path):
        """Test recording successful hover operation."""
        await metrics_collector.record(
            workspace_root=workspace_path,
            operation="hover",
            duration_ms=100.0,
            success=True,
        )

        metrics = metrics_collector.get_workspace_metrics(workspace_path)
        assert metrics is not None
        assert metrics.hover_count == 1
        assert metrics.hover_times == [100.0]
        assert metrics.hover_errors == 0

    @pytest.mark.asyncio
    async def test_record_hover_error(self, metrics_collector, workspace_path):
        """Test recording failed hover operation."""
        await metrics_collector.record(
            workspace_root=workspace_path,
            operation="hover",
            duration_ms=50.0,
            success=False,
        )

        metrics = metrics_collector.get_workspace_metrics(workspace_path)
        assert metrics is not None
        assert metrics.hover_count == 1
        assert metrics.hover_errors == 1

    @pytest.mark.asyncio
    async def test_record_multiple_operations(self, metrics_collector, workspace_path):
        """Test recording multiple different operations."""
        await metrics_collector.record(workspace_path, "hover", 100.0, True)
        await metrics_collector.record(workspace_path, "definition", 150.0, True)
        await metrics_collector.record(workspace_path, "completion", 200.0, True)
        await metrics_collector.record(workspace_path, "references", 125.0, True)

        metrics = metrics_collector.get_workspace_metrics(workspace_path)
        assert metrics.hover_count == 1
        assert metrics.definition_count == 1
        assert metrics.completion_count == 1
        assert metrics.references_count == 1

    @pytest.mark.asyncio
    async def test_record_multiple_workspaces(self, metrics_collector):
        """Test metrics isolation between workspaces."""
        ws1 = Path("/workspace1")
        ws2 = Path("/workspace2")

        await metrics_collector.record(ws1, "hover", 100.0, True)
        await metrics_collector.record(ws2, "hover", 200.0, True)

        metrics1 = metrics_collector.get_workspace_metrics(ws1)
        metrics2 = metrics_collector.get_workspace_metrics(ws2)

        assert metrics1.hover_count == 1
        assert metrics1.avg_hover_ms() == 100.0
        assert metrics2.hover_count == 1
        assert metrics2.avg_hover_ms() == 200.0

    @pytest.mark.asyncio
    async def test_get_all_metrics(self, metrics_collector):
        """Test retrieving all metrics."""
        ws1 = Path("/workspace1")
        ws2 = Path("/workspace2")

        await metrics_collector.record(ws1, "hover", 100.0, True)
        await metrics_collector.record(ws2, "definition", 150.0, True)

        all_metrics = metrics_collector.get_all_metrics()
        assert len(all_metrics) == 2
        assert all_metrics[0].workspace_root in (ws1, ws2)
        assert all_metrics[1].workspace_root in (ws1, ws2)

    @pytest.mark.asyncio
    async def test_thread_safety(self, metrics_collector, workspace_path):
        """Test concurrent access to metrics collector."""
        tasks = [
            metrics_collector.record(workspace_path, "hover", float(i), True)
            for i in range(100)
        ]

        await asyncio.gather(*tasks)

        metrics = metrics_collector.get_workspace_metrics(workspace_path)
        assert metrics.hover_count == 100
        assert len(metrics.hover_times) == 100

    @pytest.mark.asyncio
    async def test_invalid_operation(self, metrics_collector, workspace_path):
        """Test recording with invalid operation name."""
        with pytest.raises(ValueError):
            await metrics_collector.record(
                workspace_root=workspace_path,
                operation="invalid",
                duration_ms=100.0,
                success=True,
            )

    @pytest.mark.asyncio
    async def test_uptime_seconds(self, metrics_collector):
        """Test uptime calculation."""
        initial_uptime = metrics_collector.uptime_seconds()
        await asyncio.sleep(0.1)
        updated_uptime = metrics_collector.uptime_seconds()

        assert updated_uptime > initial_uptime
        assert updated_uptime - initial_uptime >= 0.1
