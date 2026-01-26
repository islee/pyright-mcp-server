"""Per-workspace metrics collection and tracking.

This module provides infrastructure for collecting performance metrics for
each workspace, including operation counts, latencies, and error tracking.
"""

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WorkspaceMetrics:
    """Metrics for a single workspace.

    Tracks per-operation counts, latencies, and errors across all operations.
    All latency times are stored as milliseconds.
    """

    workspace_root: Path

    # Per-operation counts
    hover_count: int = 0
    definition_count: int = 0
    completion_count: int = 0
    references_count: int = 0

    # Per-operation latencies (for averaging) - stored in milliseconds
    hover_times: list[float] = field(default_factory=list)
    definition_times: list[float] = field(default_factory=list)
    completion_times: list[float] = field(default_factory=list)
    references_times: list[float] = field(default_factory=list)

    # Per-operation error counts
    hover_errors: int = 0
    definition_errors: int = 0
    completion_errors: int = 0
    references_errors: int = 0

    def avg_hover_ms(self) -> float:
        """Calculate average hover latency in milliseconds."""
        return sum(self.hover_times) / len(self.hover_times) if self.hover_times else 0.0

    def avg_definition_ms(self) -> float:
        """Calculate average definition latency in milliseconds."""
        return (
            sum(self.definition_times) / len(self.definition_times)
            if self.definition_times
            else 0.0
        )

    def avg_completion_ms(self) -> float:
        """Calculate average completion latency in milliseconds."""
        return (
            sum(self.completion_times) / len(self.completion_times)
            if self.completion_times
            else 0.0
        )

    def avg_references_ms(self) -> float:
        """Calculate average references latency in milliseconds."""
        return (
            sum(self.references_times) / len(self.references_times)
            if self.references_times
            else 0.0
        )

    def to_dict(self) -> dict:
        """Convert metrics to dictionary format.

        Returns:
            Dictionary representation of metrics suitable for JSON serialization
        """
        return {
            "workspace": str(self.workspace_root),
            "operations": {
                "hover": {
                    "count": self.hover_count,
                    "avg_ms": self.avg_hover_ms(),
                    "errors": self.hover_errors,
                },
                "definition": {
                    "count": self.definition_count,
                    "avg_ms": self.avg_definition_ms(),
                    "errors": self.definition_errors,
                },
                "completion": {
                    "count": self.completion_count,
                    "avg_ms": self.avg_completion_ms(),
                    "errors": self.completion_errors,
                },
                "references": {
                    "count": self.references_count,
                    "avg_ms": self.avg_references_ms(),
                    "errors": self.references_errors,
                },
            },
        }


class MetricsCollector:
    """Thread-safe metrics collector for multiple workspaces.

    Tracks performance metrics across all workspaces and operations.
    Uses asyncio.Lock for thread-safe access in async context.
    """

    def __init__(self) -> None:
        """Initialize metrics collector."""
        self._metrics: dict[Path, WorkspaceMetrics] = {}
        self._start_time = time.time()
        self._lock = asyncio.Lock()

    async def record(
        self,
        workspace_root: Path,
        operation: str,
        duration_ms: float,
        success: bool,
    ) -> None:
        """Record metrics for an operation.

        Args:
            workspace_root: Root path of the workspace
            operation: Operation name (hover, definition, completion, references)
            duration_ms: Duration in milliseconds
            success: Whether the operation succeeded

        Raises:
            ValueError: If operation is not a valid operation name
        """
        if operation not in ("hover", "definition", "completion", "references"):
            raise ValueError(f"Invalid operation: {operation}")

        async with self._lock:
            if workspace_root not in self._metrics:
                self._metrics[workspace_root] = WorkspaceMetrics(workspace_root)

            metrics = self._metrics[workspace_root]

            # Update operation counts and times
            if operation == "hover":
                metrics.hover_count += 1
                metrics.hover_times.append(duration_ms)
                if not success:
                    metrics.hover_errors += 1
            elif operation == "definition":
                metrics.definition_count += 1
                metrics.definition_times.append(duration_ms)
                if not success:
                    metrics.definition_errors += 1
            elif operation == "completion":
                metrics.completion_count += 1
                metrics.completion_times.append(duration_ms)
                if not success:
                    metrics.completion_errors += 1
            elif operation == "references":
                metrics.references_count += 1
                metrics.references_times.append(duration_ms)
                if not success:
                    metrics.references_errors += 1

    def get_workspace_metrics(self, workspace_root: Path) -> WorkspaceMetrics | None:
        """Get metrics for a specific workspace.

        Args:
            workspace_root: Root path of the workspace

        Returns:
            WorkspaceMetrics if workspace exists, None otherwise
        """
        return self._metrics.get(workspace_root)

    def get_all_metrics(self) -> list[WorkspaceMetrics]:
        """Get metrics for all workspaces.

        Returns:
            List of WorkspaceMetrics, one per workspace with recorded activity
        """
        return list(self._metrics.values())

    def uptime_seconds(self) -> float:
        """Get server uptime in seconds.

        Returns:
            Time elapsed since collector initialization
        """
        return time.time() - self._start_time
