# ADR-001: Automatic LSP Idle Timeout Enforcement

**Date:** 2026-01-26
**Status:** Accepted
**Decision:** Implement background watcher task for automatic idle timeout enforcement

---

## Context

The LSP client in Phase 2 includes idle timeout functionality to shut down the pyright-langserver subprocess after a period of inactivity (default: 5 minutes). This prevents memory leaks and resource consumption when the LSP server is not actively used.

**Current implementation:**
- `check_idle_timeout()` method exists in LSPClient
- Method must be called manually to enforce timeout
- If not called, timeout never fires → LSP subprocess runs indefinitely

**Problem:**
Without automatic enforcement, the idle timeout is a documentation feature that doesn't actually work unless someone remembers to call the check method.

---

## Problem

**Manual timeout checking has several issues:**

1. **Easy to forget** - Developers must remember to call `check_idle_timeout()` periodically
2. **Inconsistent enforcement** - Different call sites may check at different frequencies
3. **Memory leaks** - If never called, LSP processes accumulate in long-running servers
4. **Testing complexity** - Tests must explicitly trigger timeout checks

**Impact:**
- Production deployments: LSP subprocesses never shut down → memory leaks
- Development: Inconsistent behavior depending on call patterns
- User experience: Unpredictable resource usage

---

## Analysis

### Option 1: Background Watcher Task ⭐ SELECTED

**Implementation:**
```python
async def _idle_timeout_watcher(self) -> None:
    """Background task to enforce idle timeout."""
    while self._state == LSPState.READY:
        await asyncio.sleep(60)  # Check every minute
        # Check timeout logic
        if idle_time >= self.config.lsp_timeout:
            await self._shutdown_internal()
```

**Pros:**
- Automatic enforcement (no manual calls needed)
- Consistent checking interval (every 60 seconds)
- Tied to LSP lifecycle (starts with init, stops with shutdown)
- Simple implementation (~20 lines)

**Cons:**
- One additional background task per LSP instance
- 60-second checking granularity (not exact timeout)

### Option 2: Per-Request Check

Call `check_idle_timeout()` after every hover/definition/completion request.

**Pros:**
- No background task
- Exact timeout enforcement

**Cons:**
- Must add to every tool wrapper
- Easy to forget in new tools
- Timeout only checked when operations occur (idle server never times out)

### Option 3: External Timer (asyncio.call_later)

Use asyncio's timer mechanism to schedule timeout checks.

**Pros:**
- Event-driven (no polling)

**Cons:**
- Complex timeout rescheduling on each activity
- More state to track (timer handles)
- Harder to test

---

## Decision

**Implement background watcher task (Option 1) for automatic idle timeout enforcement.**

**Rationale:**
1. **Automatic** - No manual intervention required
2. **Reliable** - Always enforces timeout, can't be forgotten
3. **Simple** - Straightforward implementation and testing
4. **Efficient** - Checks every 60s (low overhead)
5. **Lifecycle-bound** - Starts with LSP init, stops with cleanup

**Changes:**
- Add `_watcher_task` field to LSPClient
- Implement `_idle_timeout_watcher()` method
- Start watcher in `_start_and_initialize()`
- Cancel watcher in `_cleanup()`

**Location:** `src/pyright_mcp/backends/lsp_client.py`

---

## Consequences

### Positive
- ✅ Automatic timeout enforcement (no manual calls)
- ✅ Prevents memory leaks in long-running servers
- ✅ Consistent behavior across deployments
- ✅ Simpler tool implementation (no timeout checks needed)
- ✅ Easy to test (just wait for timeout)

### Negative
- ⚠️ One additional task per LSP instance (minimal overhead)
- ⚠️ 60-second checking granularity (timeout ±60s, acceptable for 5-minute default)

### Neutral
- Checking interval (60s) is hardcoded but timeout itself is configurable via `PYRIGHT_MCP_LSP_TIMEOUT`
- No impact on Phase 3 LSP pooling (each pooled client has its own watcher)

---

## Alternatives Considered

### Alternative: Manual Check in Tool Wrapper

**Rejected:** Too easy to forget, defeats purpose of automatic timeout.

Example of problematic pattern:
```python
# tools/hover.py
async def get_hover(...):
    result = await backend.hover(...)
    # Developer must remember:
    await backend.check_idle_timeout()  # Easy to forget!
    return result
```

### Alternative: Remove Idle Timeout Feature

**Rejected:** Idle timeout is valuable for resource management. Better to make it work reliably than remove it.

---

## Implementation Notes

**Testing:**
```python
async def test_idle_timeout_automatic():
    client = LSPClient()
    client.config.lsp_timeout = 2.0  # 2 seconds for test

    await client.ensure_initialized(Path("/tmp/project"))
    assert client.state == LSPState.READY

    # Wait for automatic timeout
    await asyncio.sleep(3.0)

    # Watcher should have shut down LSP
    assert client.state == LSPState.NOT_STARTED
```

**Activity tracking** (already implemented):
- `ensure_initialized()` - updates last_activity
- `hover()` - updates last_activity
- `definition()` - updates last_activity
- `complete()` - updates last_activity (Phase 3)

**Watcher lifecycle:**
1. Starts: When LSP transitions to READY state
2. Checks: Every 60 seconds
3. Stops: When LSP state changes (shutdown, crash) or timeout fires

---

## References

- Implementation: `src/pyright_mcp/backends/lsp_client.py`
- Tests: `tests/unit/test_lsp_client.py`
- TDD Section 14.2: Phase 2 LSP Integration
- Configuration: `PYRIGHT_MCP_LSP_TIMEOUT` environment variable
