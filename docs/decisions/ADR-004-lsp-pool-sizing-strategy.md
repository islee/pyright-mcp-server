# ADR-004: LSP Pool Size Strategy

**Date:** 2026-01-26
**Status:** Accepted
**Decision:** Default pool size of 3 LSP instances; monitor usage patterns before optimization

---

## Context

Phase 3 introduces multi-workspace support via LSP pooling. Users working across multiple Python projects need concurrent LSP instances to avoid reinitialization delays.

**Requirements:**
- Support users working across multiple projects
- Avoid unbounded memory usage
- Balance performance vs resource consumption

**Question:** What should the default pool size be, and how should we handle capacity limits?

---

## Problem

**Need to balance:**
1. **User workflow** - How many projects do users work on simultaneously?
2. **Resource constraints** - Each LSP instance uses ~50-100MB RAM
3. **Performance** - LRU eviction causes reinitialization delays
4. **Default experience** - Most users shouldn't need to configure

**Unknown:** Real-world usage patterns. We don't have production data yet on:
- Typical workspace count per session
- Workspace switching frequency
- Cache hit rates

**Risk of wrong choice:**
- **Too small** - Frequent evictions, poor performance
- **Too large** - Wasted memory for most users

---

## Analysis

### Option 1: Pool Size = 1

Single LSP instance (no pooling).

**Pros:**
- Minimal memory usage
- Simple implementation (like Phase 2)

**Cons:**
- ❌ Poor multi-workspace experience
- ❌ Reinitialize on every switch (3s delay)
- ❌ Defeats purpose of pooling

**Rejected:** Inadequate for target use case.

### Option 2: Pool Size = 3 ⭐ SELECTED

Default pool of 3 LSP instances with LRU eviction.

**Pros:**
- ✅ Covers typical workflows (1-3 active projects)
- ✅ Reasonable memory usage (~150-300MB)
- ✅ Simple default (no configuration needed)
- ✅ Good starting point for data collection

**Cons:**
- May be insufficient for power users (4+ projects)
- May be excessive for single-project users

**Selected:** Best starting point given uncertainty.

### Option 3: Pool Size = 5

Larger default pool.

**Pros:**
- Covers more use cases
- Fewer evictions

**Cons:**
- ❌ Higher memory baseline (~250-500MB)
- ❌ Wasteful if most users work on 1-2 projects

**Rejected:** Premature optimization without data.

### Option 4: Dynamic Pool Sizing

Automatically adjust pool size based on usage.

**Pros:**
- Adapts to user behavior

**Cons:**
- ❌ Complex implementation
- ❌ Unpredictable memory usage
- ❌ Hard to reason about behavior

**Rejected:** Too complex for Phase 3.

---

## Decision

**Default LSP pool size: 3 instances with LRU eviction. Monitor usage patterns before further optimization.**

**Rationale:**
1. **Covers common case** - Most users work on 1-3 projects simultaneously
2. **Reasonable resource usage** - ~150-300MB total
3. **Tunable** - Users can adjust via `PYRIGHT_MCP_LSP_POOL_SIZE`
4. **Data-driven approach** - Collect metrics before optimizing

**Configuration:**
```bash
# Default (recommended for most users)
# (no configuration needed)

# Power users (4+ concurrent projects)
export PYRIGHT_MCP_LSP_POOL_SIZE=5

# Single-project users (memory constrained)
export PYRIGHT_MCP_LSP_POOL_SIZE=1
```

**User decision:** "idk. let's review this periodically."

---

## Consequences

### Positive
- ✅ Simple default (works for most users)
- ✅ Configurable (power users can increase)
- ✅ Collects usage data (cache hit rate, eviction count)
- ✅ Easy to adjust after observing patterns

### Negative
- ⚠️ May not be optimal for all users
- ⚠️ Power users (4+ projects) may experience evictions

### Neutral
- Pool size is a configuration detail, not a hard limit
- Can adjust recommendation after collecting metrics
- Memory usage: ~50-100MB per instance

---

## Monitoring Strategy

**Collect these metrics in Phase 3:**

1. **Cache hit rate**
   ```
   hits / (hits + workspace_switches)
   ```
   - High rate (>80%) → Pool size is adequate
   - Low rate (<50%) → Consider increasing default

2. **Eviction count**
   ```
   evictions / workspace_switches
   ```
   - High rate (>50%) → Pool too small
   - Low rate (<10%) → Pool size is good

3. **Workspace distribution**
   ```
   unique_workspaces_per_session
   ```
   - Median < 3 → Current default is good
   - Median > 3 → Consider increasing default

**Tuning guidance** (to be documented):
```markdown
### LSP Pool Sizing

Monitor via health_check:
- Cache hit rate < 50% → Increase pool size
- Evictions > 50% of switches → Increase pool size
- Unique workspaces < pool size → Can decrease pool size
```

---

## Implementation Details

**Pool Configuration:**
```python
class LSPPool:
    def __init__(
        self,
        max_instances: int = 3,  # Default from environment or 3
        idle_timeout: float = 300.0,
    ):
        self._max_instances = max_instances
        self._clients: dict[Path, LSPClient] = {}
        self._access_order: list[Path] = []  # LRU tracking

        # Usage tracking
        self._stats = {
            "evictions": 0,
            "workspace_switches": 0,
            "cache_hits": 0,
        }
```

**Health Check Output:**
```json
{
  "lsp_pool": {
    "active_instances": 2,
    "max_instances": 3,
    "workspaces": ["/projects/app1", "/projects/app2"],
    "cache_hit_rate": 0.85,
    "eviction_count": 5,
    "workspace_switches": 30
  }
}
```

**LRU Eviction:**
- Evict least recently used workspace when at capacity
- Graceful shutdown (send LSP shutdown request)
- Document manager cleanup (didClose all files)

---

## Tuning Examples

**Example 1: Power User**
```bash
# Observes frequent evictions
$ health_check
{
  "lsp_pool": {
    "eviction_count": 50,
    "workspace_switches": 80,
    "cache_hit_rate": 0.38  # Low!
  }
}

# Solution: Increase pool size
export PYRIGHT_MCP_LSP_POOL_SIZE=5
```

**Example 2: Memory-Constrained**
```bash
# Single-project user on low-memory device
export PYRIGHT_MCP_LSP_POOL_SIZE=1
```

**Example 3: Default Works**
```bash
# Most users: no configuration needed
$ health_check
{
  "lsp_pool": {
    "eviction_count": 2,
    "workspace_switches": 50,
    "cache_hit_rate": 0.92  # Good!
  }
}
```

---

## Review Plan

**After 1 month of Phase 3 production usage:**

1. Collect metrics from users (via anonymous telemetry or manual reports)
2. Analyze distribution:
   - What's the median workspace count?
   - What's the typical cache hit rate?
   - How often do evictions occur?

3. Adjust recommendation if needed:
   - If median workspaces > 3: Increase default to 4 or 5
   - If eviction rate high: Increase default
   - If cache hit rate low: Increase default

**Decision triggers:**
- Cache hit rate < 60% across users → Increase to 4
- Cache hit rate < 50% across users → Increase to 5
- Eviction rate > 60% → Increase default

---

## Future Enhancements

**Not in Phase 3 scope:**
- Dynamic pool sizing (adaptive)
- Priority-based eviction (keep frequently-used workspaces)
- Pool size auto-tuning (ML-based)
- Per-workspace memory tracking

**Potential Phase 4:**
- Workspace usage prediction (pre-load likely workspaces)
- Time-based eviction (close workspace after long idle)
- Shared LSP pool across multiple MCP server instances

---

## Alternatives Considered

### Alternative: No Pool Limit

Allow unlimited LSP instances.

**Rejected:**
- Unbounded memory usage
- Can exhaust system resources
- No backpressure mechanism

### Alternative: Pool Size = CPU Count

Set pool size based on available cores.

**Rejected:**
- Workspaces are I/O-bound, not CPU-bound
- Cores don't correlate with workspace count
- Same machine might have 1 or 10 projects

### Alternative: Make Pool Size Required

Force users to configure pool size explicitly.

**Rejected:**
- Poor default experience
- Most users won't know what to choose
- Default of 3 works for most cases

---

## References

- Implementation: `src/pyright_mcp/backends/lsp_pool.py` (Phase 3)
- Configuration: `PYRIGHT_MCP_LSP_POOL_SIZE` environment variable
- Monitoring: `tools/health_check.py` pool statistics
- TDD Section 14.3: Phase 3 Multi-Workspace Support
- ADR-003: Per-Workspace Metrics (provides data for tuning)
