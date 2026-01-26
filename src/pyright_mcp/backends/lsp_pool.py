"""LSP client pool for multi-workspace support.

Manages multiple LSP clients with LRU (Least Recently Used) eviction strategy
to support working with multiple workspaces while limiting resource usage.

Key features:
- On-demand client creation per workspace
- LRU eviction when pool reaches max capacity
- Cache hit/miss tracking
- Graceful shutdown of evicted clients
- Configurable pool size via PYRIGHT_MCP_LSP_POOL_SIZE (default: 3)
"""

import asyncio
import os
from pathlib import Path
from typing import Any

from ..config import Config, get_config
from ..logging_config import get_logger
from .lsp_client import LSPClient

logger = get_logger("backends.lsp_pool")


class LSPPool:
    """Manages a pool of LSP clients for multiple workspaces.

    Uses LRU (Least Recently Used) eviction to maintain a fixed pool size.
    When the pool is at capacity and a new workspace is requested, the least
    recently used workspace is evicted.

    Example:
        pool = LSPPool(max_instances=3)
        client = await pool.get_client(Path("/workspace1"))
        client2 = await pool.get_client(Path("/workspace2"))
        stats = pool.get_pool_stats()
        await pool.shutdown_all()
    """

    def __init__(
        self,
        max_instances: int | None = None,
        idle_timeout: float | None = None,
        config: Config | None = None,
    ) -> None:
        """Initialize LSP pool.

        Args:
            max_instances: Maximum number of LSP clients to keep (default from env or 3)
            idle_timeout: Idle timeout for LSP clients in seconds (default from config)
            config: Configuration instance (uses get_config() if not provided)
        """
        self.config = config or get_config()
        self._max_instances = max_instances or int(
            os.getenv("PYRIGHT_MCP_LSP_POOL_SIZE", "3")
        )
        self._idle_timeout = idle_timeout or self.config.lsp_timeout

        self._clients: dict[Path, LSPClient] = {}
        self._access_order: list[Path] = []  # LRU tracking (oldest first)
        self._lock = asyncio.Lock()

        # Usage statistics
        self._stats = {
            "evictions": 0,
            "workspace_switches": 0,
            "cache_hits": 0,
        }

        logger.info(
            f"Initialized LSP pool with max_instances={self._max_instances}, "
            f"idle_timeout={self._idle_timeout}s"
        )

    async def get_client(self, workspace_root: Path) -> LSPClient:
        """Get or create LSP client for workspace.

        If a client for this workspace already exists, it is returned and marked
        as recently used. If not, a new client is created. If the pool is at
        capacity, the least recently used client is evicted first.

        Args:
            workspace_root: Root path of the workspace

        Returns:
            LSPClient instance for the workspace

        Raises:
            BackendError: If client creation fails
        """
        async with self._lock:
            # Check if client exists (cache hit)
            if workspace_root in self._clients:
                self._stats["cache_hits"] += 1
                self._update_access_order(workspace_root)
                logger.debug(f"Cache hit for workspace: {workspace_root}")
                return self._clients[workspace_root]

            # Cache miss - need to create new client
            self._stats["workspace_switches"] += 1
            logger.debug(f"Cache miss for workspace: {workspace_root}")

            # Evict LRU if at capacity
            if len(self._clients) >= self._max_instances:
                await self._evict_lru()

            # Create new client with configured timeout
            client = LSPClient(config=self.config)
            client.config.lsp_timeout = self._idle_timeout
            self._clients[workspace_root] = client
            self._access_order.append(workspace_root)
            logger.info(
                f"Created new LSP client for workspace: {workspace_root} "
                f"(pool size: {len(self._clients)}/{self._max_instances})"
            )
            return client

    async def _evict_lru(self) -> None:
        """Evict least recently used workspace.

        Removes the oldest (least recently used) workspace from the pool
        and gracefully shuts down its LSP client.

        The access_order list is maintained with oldest entries at index 0.
        """
        if not self._access_order:
            logger.warning("Attempted to evict but access_order is empty")
            return

        lru_workspace = self._access_order.pop(0)
        client = self._clients.pop(lru_workspace)

        # Graceful shutdown
        try:
            logger.info(f"Evicting LSP client for workspace: {lru_workspace}")
            await client.shutdown()
        except Exception as e:
            logger.warning(f"Error shutting down evicted client for {lru_workspace}: {e}")

        self._stats["evictions"] += 1

    def _update_access_order(self, workspace_root: Path) -> None:
        """Move workspace to end of LRU list (mark as recently used).

        The access_order list maintains LRU order with oldest (least recently used)
        at index 0 and newest (most recently used) at the end.

        Args:
            workspace_root: Path to move to end of list
        """
        if workspace_root in self._access_order:
            self._access_order.remove(workspace_root)
        self._access_order.append(workspace_root)

    async def shutdown_all(self) -> None:
        """Shutdown all LSP clients and clear the pool.

        Safe to call multiple times. After calling this, the pool is empty
        and get_client() will create new clients as needed.
        """
        async with self._lock:
            for workspace_root, client in self._clients.items():
                try:
                    logger.debug(f"Shutting down LSP client for workspace: {workspace_root}")
                    await client.shutdown()
                except Exception as e:
                    logger.warning(
                        f"Error shutting down client for {workspace_root}: {e}"
                    )

            self._clients.clear()
            self._access_order.clear()
            logger.info("LSP pool shut down completely")

    def get_pool_stats(self) -> dict[str, Any]:
        """Get pool usage statistics.

        Returns statistics about cache performance, evictions, and current pool state.

        Returns:
            Dictionary containing:
                - active_instances: Current number of clients in pool
                - max_instances: Maximum pool size
                - workspaces: List of workspace paths in LRU order
                - cache_hit_rate: Fraction of get_client() calls that were cache hits
                - eviction_count: Number of clients evicted due to capacity
                - workspace_switches: Number of new workspaces requested
        """
        total_switches = self._stats["cache_hits"] + self._stats["workspace_switches"]
        cache_hit_rate = 0.0
        if total_switches > 0:
            cache_hit_rate = self._stats["cache_hits"] / total_switches

        return {
            "active_instances": len(self._clients),
            "max_instances": self._max_instances,
            "workspaces": [str(ws) for ws in self._access_order],
            "cache_hit_rate": round(cache_hit_rate, 3),
            "eviction_count": self._stats["evictions"],
            "workspace_switches": self._stats["workspace_switches"],
        }
