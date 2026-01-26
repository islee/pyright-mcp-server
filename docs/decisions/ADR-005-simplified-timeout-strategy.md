# ADR-005: Simplified Timeout Strategy

**Date:** 2026-01-26
**Status:** Accepted
**Decision:** Use single configurable timeout for LSP idle detection; no adaptive timeout logic

---

## Context

LSP clients automatically shut down after a period of inactivity to free resources. The idle timeout duration needs to balance:
- **User experience** - Don't shut down during active work
- **Resource management** - Don't keep idle processes running indefinitely
- **Predictability** - Users should understand timeout behavior

**Question:** Should timeout be adaptive (change based on activity patterns) or static (single configurable value)?

---

## Problem

**Two approaches:**

1. **Adaptive timeout:**
   - Short timeout after high activity (e.g., 1 min after many completions)
   - Long timeout during low activity (e.g., 5 min normally)
   - Rationale: Aggressive cleanup when user is "done" editing

2. **Static timeout:**
   - Single timeout value for all scenarios
   - Simple to understand and configure
   - Predictable behavior

**Trade-offs:**
- Adaptive: Better resource usage, but complex and unpredictable
- Static: Simple, but may keep LSP alive longer than needed

---

## Analysis

### Option 1: Adaptive Timeout

Adjust timeout based on activity patterns.

**Example logic:**
```python
def get_timeout(self) -> float:
    if self._recent_completion_rate > 10_per_minute:
        return 60.0  # 1 minute (user finished burst)
    elif self._recent_activity < 5_per_minute:
        return 300.0  # 5 minutes (sparse activity)
    else:
        return 180.0  # 3 minutes (moderate activity)
```

**Pros:**
- Potentially better resource usage
- Shuts down quickly after completion bursts

**Cons:**
- ❌ Complex implementation (track activity rates)
- ❌ Unpredictable behavior (timeout changes)
- ❌ Hard to document ("timeout varies based on activity")
- ❌ More test cases (activity patterns)
- ❌ Edge cases (what if user pauses to think?)

### Option 2: Single Configurable Timeout ⭐ SELECTED

One timeout value for all scenarios.

**Example:**
```python
# Configuration
PYRIGHT_MCP_LSP_TIMEOUT=300  # 5 minutes (default)

# Implementation
if idle_time >= self.config.lsp_timeout:
    await shutdown()
```

**Pros:**
- ✅ Simple implementation (~10 lines)
- ✅ Predictable behavior
- ✅ Easy to document ("LSP shuts down after 5 minutes of inactivity")
- ✅ Configurable (users can adjust to preference)
- ✅ Few edge cases

**Cons:**
- May keep LSP alive longer than adaptive approach
- Single size may not fit all workflows

---

## Decision

**Use single configurable timeout for LSP idle detection. No adaptive timeout logic.**

**Rationale:**
1. **Simplicity** - Easy to implement, test, and maintain
2. **Predictability** - Users know exactly when LSP will shut down
3. **Configurability** - Users can tune to their workflow
4. **Sufficient** - 5-minute default is reasonable for most cases

**User decision:** "keep it simple"

**Configuration:**
```bash
# Default (5 minutes)
PYRIGHT_MCP_LSP_TIMEOUT=300

# Faster iteration (1 minute)
PYRIGHT_MCP_LSP_TIMEOUT=60

# Keep alive longer (10 minutes)
PYRIGHT_MCP_LSP_TIMEOUT=600
```

---

## Consequences

### Positive
- ✅ Simple implementation (single timeout check)
- ✅ Predictable behavior (no surprises)
- ✅ Easy to document and explain
- ✅ Easy to test (just wait for timeout)
- ✅ Fewer edge cases

### Negative
- ⚠️ May not be optimal for all activity patterns
- ⚠️ Some users may want adaptive behavior

### Neutral
- Users who want adaptive behavior can restart manually
- Timeout is checked every 60 seconds (not exact)
- Can add adaptive logic in future if user feedback demands it

---

## Implementation Details

**Timeout Enforcement:**
```python
# lsp_client.py
async def _idle_timeout_watcher(self) -> None:
    """Check idle timeout every 60 seconds."""
    while self._state == LSPState.READY:
        await asyncio.sleep(60)

        idle_time = time.time() - self._process.last_activity
        if idle_time >= self.config.lsp_timeout:
            logger.info(f"Idle timeout ({idle_time:.1f}s >= {self.config.lsp_timeout}s)")
            await self._shutdown_internal()
```

**Activity Tracking:**
Activity resets timeout on:
- `ensure_initialized()` - LSP startup
- `hover()` - Hover requests
- `definition()` - Definition requests
- `complete()` - Completion requests (Phase 3)

**Not tracked as activity:**
- `check_types()` - Uses CLI, not LSP
- Background tasks - Watcher, reader
- Health checks - Diagnostic only

---

## Documentation

**README:**
```markdown
### LSP Idle Timeout

The LSP server automatically shuts down after 5 minutes of inactivity (configurable).

Activity includes:
- Hover requests
- Go-to-definition requests
- Completion requests

The LSP will restart automatically on the next request.

**Configuration:**
```bash
export PYRIGHT_MCP_LSP_TIMEOUT=300  # 5 minutes (default)
```
```

**TDD Section 14.2:**
```markdown
**Timeout Strategy:**
- Single configurable timeout (no adaptive logic)
- Default: 300 seconds (5 minutes)
- Checked every 60 seconds by background watcher
- Activity tracked on all LSP operations
```

---

## Usage Examples

**Example 1: Development**
```bash
# Faster iteration during active development
export PYRIGHT_MCP_LSP_TIMEOUT=60  # 1 minute
```

**Example 2: Long Editing Sessions**
```bash
# Keep LSP alive during deep work
export PYRIGHT_MCP_LSP_TIMEOUT=1800  # 30 minutes
```

**Example 3: Default**
```bash
# Most users: no configuration needed
# Uses 5-minute default
```

---

## Future Considerations

**Not implementing now:**
- Adaptive timeout based on activity rate
- Different timeouts per workspace
- Time-of-day based timeouts
- User-configured timeout profiles

**Conditions for reconsidering:**
1. **User feedback** - Multiple users request adaptive behavior
2. **Resource data** - Evidence that static timeout wastes resources
3. **Clear use case** - Specific workflow that would benefit

**Likely outcome:** Static timeout is sufficient for foreseeable future.

---

## Alternatives Considered

### Alternative: Adaptive Timeout with Activity Heuristics

**Rejected:** Complexity not justified by benefits.

Example complexity:
```python
# Track activity for adaptive timeout
self._activity_window: deque[float] = deque(maxlen=100)
self._completion_burst_threshold = 20

def _calculate_adaptive_timeout(self) -> float:
    recent_activity = len([
        t for t in self._activity_window
        if time.time() - t < 60
    ])

    if recent_activity > self._completion_burst_threshold:
        return 60.0  # Short timeout after burst
    elif recent_activity < 5:
        return 300.0  # Long timeout for sparse
    else:
        return 180.0  # Medium timeout
```

Too complex for marginal benefit.

### Alternative: No Timeout

Keep LSP running indefinitely.

**Rejected:**
- Memory leaks in long-running servers
- Resource waste for inactive workspaces
- Idle timeout is a useful feature

### Alternative: Very Short Timeout (30 seconds)

Aggressive shutdown to minimize resource usage.

**Rejected:**
- Poor user experience (frequent restarts)
- 3-second restart penalty is noticeable
- Users may pause to think for >30 seconds

---

## Testing Strategy

**Unit test:**
```python
async def test_idle_timeout_single_value():
    """Verify timeout uses configured value."""
    client = LSPClient()
    client.config.lsp_timeout = 120.0  # 2 minutes

    await client.ensure_initialized(workspace)

    # Wait just under timeout
    await asyncio.sleep(110)
    assert client.state == LSPState.READY

    # Wait past timeout
    await asyncio.sleep(20)
    assert client.state == LSPState.NOT_STARTED
```

**Integration test:**
```python
async def test_activity_resets_timeout():
    """Verify activity resets idle timer."""
    client = LSPClient()
    client.config.lsp_timeout = 5.0

    await client.ensure_initialized(workspace)

    # Keep alive with periodic requests
    for _ in range(3):
        await asyncio.sleep(3)
        await client.hover(file, 0, 0)  # Resets timer

    # LSP should still be running (activity kept it alive)
    assert client.state == LSPState.READY
```

---

## References

- Implementation: `src/pyright_mcp/backends/lsp_client.py`
- Configuration: `PYRIGHT_MCP_LSP_TIMEOUT` environment variable
- Tests: `tests/unit/test_lsp_client.py`
- Related: ADR-001 (Automatic Idle Timeout Enforcement)
- TDD Section 14.2: Phase 2 LSP Integration
