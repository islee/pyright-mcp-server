# ADR-003: Per-Workspace Metrics Granularity

**Date:** 2026-01-26
**Status:** Accepted
**Decision:** Track performance metrics per workspace rather than globally or per-operation

---

## Context

Phase 3 includes a metrics collection system to monitor pyright-mcp performance in production. This helps identify bottlenecks, detect regressions, and guide optimization efforts.

**Metrics to track:**
- Operation counts (hover, definition, completion, check)
- Latency statistics (avg, min, max)
- Error rates
- Success/failure counts

**Question:** What granularity should metrics be collected at?

---

## Problem

**Need to answer:**
1. Which workspaces are slow? (per-workspace)
2. Which operations are slow? (per-operation)
3. What's the overall system health? (global)

**Trade-offs:**
- **Global metrics** - Simple but no actionable insights
- **Per-operation metrics** - Identifies slow operations but not slow projects
- **Per-workspace metrics** - Identifies problematic workspaces
- **Per-workspace + per-operation** - Full visibility but complex

---

## Analysis

### Option 1: Global Metrics

Track totals across all operations and workspaces.

**Example:**
```json
{
  "total_requests": 1000,
  "avg_latency_ms": 150,
  "error_rate": 0.02
}
```

**Pros:**
- Simple to implement
- Low memory overhead
- Easy to understand

**Cons:**
- ❌ Can't identify slow workspaces
- ❌ Can't see which operations are problematic
- ❌ No actionable insights

**Rejected:** Not useful enough for troubleshooting.

### Option 2: Per-Operation Metrics

Track each operation type separately.

**Example:**
```json
{
  "hover": {"count": 500, "avg_ms": 120, "errors": 5},
  "definition": {"count": 300, "avg_ms": 100, "errors": 2},
  "completion": {"count": 200, "avg_ms": 200, "errors": 10}
}
```

**Pros:**
- Identifies slow operations
- Guides optimization priorities

**Cons:**
- ❌ Can't identify slow workspaces
- ❌ Doesn't help with project-specific issues

**Rejected:** Useful but incomplete.

### Option 3: Per-Workspace Metrics ⭐ SELECTED

Track metrics separately for each workspace.

**Example:**
```json
{
  "workspaces": [
    {
      "workspace": "/projects/small-app",
      "hover": {"count": 50, "avg_ms": 80, "errors": 0},
      "definition": {"count": 30, "avg_ms": 60, "errors": 0}
    },
    {
      "workspace": "/projects/large-monorepo",
      "hover": {"count": 450, "avg_ms": 500, "errors": 20},
      "definition": {"count": 270, "avg_ms": 450, "errors": 15}
    }
  ]
}
```

**Pros:**
- ✅ Identifies slow workspaces
- ✅ Identifies problematic projects
- ✅ Guides per-project optimization
- ✅ Helps with LSP pool sizing decisions

**Cons:**
- Memory grows with workspace count
- Slightly more complex aggregation

**Selected:** Best balance of insight and complexity.

### Option 4: Per-Workspace + Per-Operation (Full Matrix)

Track every combination.

**Pros:**
- Complete visibility

**Cons:**
- ❌ Complex to implement
- ❌ High memory usage
- ❌ Harder to interpret

**Rejected:** Overkill for current needs. Can add later if needed.

---

## Decision

**Implement per-workspace metrics tracking in Phase 3.**

**Key design:**
1. **WorkspaceMetrics** class tracks metrics for one workspace
2. **MetricsCollector** maintains dict of workspace → metrics
3. Each tool records operation with workspace context
4. health_check exposes per-workspace stats

**Rationale:**
1. **Actionable insights** - Can identify which projects are slow
2. **LSP pool tuning** - See which workspaces need priority
3. **User guidance** - Recommend configuration per workspace
4. **Debugging** - Narrow down performance issues to specific projects

**User decisions addressed:**
- ❌ Not per-operation (too coarse)
- ❌ Not global (not actionable)
- ✅ Per-workspace (identifies problematic projects)
- ❌ Not full matrix (unnecessary complexity)

---

## Consequences

### Positive
- ✅ Identifies slow workspaces (e.g., large monorepos)
- ✅ Guides LSP pool sizing (prioritize heavily-used workspaces)
- ✅ Helps users understand per-project performance
- ✅ Enables workspace-specific recommendations
- ✅ Easy to aggregate to global stats if needed

### Negative
- ⚠️ Memory usage grows with workspace count (acceptable: ~1KB per workspace)
- ⚠️ Slightly more complex than global metrics

### Neutral
- Can still compute global stats by aggregating workspaces
- Per-operation breakdown included within each workspace
- Old workspaces remain in metrics until server restart (no cleanup)

---

## Implementation Details

**Data Structure:**
```python
@dataclass
class WorkspaceMetrics:
    workspace_root: Path

    # Per-operation counts
    hover_count: int = 0
    definition_count: int = 0
    completion_count: int = 0

    # Per-operation latencies (for averaging)
    hover_times: list[float] = field(default_factory=list)
    definition_times: list[float] = field(default_factory=list)
    completion_times: list[float] = field(default_factory=list)

    # Per-operation error counts
    hover_errors: int = 0
    definition_errors: int = 0
    completion_errors: int = 0
```

**Collection:**
```python
# In tools/hover.py
async def get_hover(file: str, line: int, column: int) -> dict:
    start = time.time()
    success = False

    try:
        context = await detect_project(Path(file))
        result = await backend.hover(...)
        success = True
        return result.to_dict()
    finally:
        duration_ms = (time.time() - start) * 1000
        metrics_collector.record(
            workspace_root=context.root,  # Workspace context
            operation="hover",
            duration_ms=duration_ms,
            success=success,
        )
```

**Reporting:**
```python
# health_check output
{
  "metrics": {
    "uptime_seconds": 3600,
    "workspaces": [
      {
        "workspace": "/projects/myapp",
        "operations": {
          "hover": {
            "count": 150,
            "avg_ms": 120,
            "errors": 2
          },
          "definition": {
            "count": 80,
            "avg_ms": 100,
            "errors": 0
          }
        }
      }
    ]
  }
}
```

---

## Usage Examples

**Identify slow workspace:**
```json
{
  "workspace": "/projects/large-monorepo",
  "hover": {"count": 500, "avg_ms": 800, "errors": 50}
}
```
→ **Action:** Investigate Pyright configuration for this workspace

**LSP pool prioritization:**
```json
// Workspace A: heavily used
{"workspace": "/projects/active", "hover": {"count": 1000}}

// Workspace B: rarely used
{"workspace": "/projects/old", "hover": {"count": 10}}
```
→ **Action:** Keep workspace A in pool, evict workspace B

**Performance regression detection:**
```json
// Before: avg_ms = 150
// After: avg_ms = 500
```
→ **Action:** Bisect changes, investigate Pyright upgrade

---

## Future Enhancements

**Not in Phase 3 scope:**
- Time-series metrics (histogram buckets)
- Metrics persistence (reset on restart)
- Metrics export (Prometheus, etc.)
- Automatic alerts (threshold-based)

**Potential Phase 4:**
- Per-file metrics (identify hot files)
- Latency percentiles (p50, p95, p99)
- Metrics aggregation service

---

## Alternatives Considered

### Alternative: Per-File Metrics

Track metrics per individual file.

**Rejected:**
- Too granular (thousands of files)
- High memory usage
- Harder to interpret

### Alternative: No Metrics

Skip metrics collection entirely.

**Rejected:**
- Need visibility into production performance
- Can't identify optimization opportunities
- No data for LSP pool tuning

### Alternative: Metrics Off by Default

Make metrics opt-in.

**Rejected:**
- Want metrics in production by default
- Low overhead (~1KB per workspace)
- Can disable via `PYRIGHT_MCP_METRICS_ENABLED=false` if needed

---

## References

- Implementation: `src/pyright_mcp/metrics.py` (Phase 3)
- Integration: `tools/hover.py`, `tools/definition.py`, etc.
- Reporting: `tools/health_check.py`
- TDD Section 14.3: Phase 3 Performance Metrics
