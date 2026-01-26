# ADR-006: No Tool-Level Caching

**Date:** 2026-01-26
**Status:** Accepted
**Decision:** Do not implement tool-level result caching; rely on LSP internal caching

---

## Context

Performance optimization for pyright-mcp could include caching results at multiple levels:
1. **LSP internal cache** - Pyright language server maintains its own cache
2. **Tool-level cache** - pyright-mcp caches responses between LSP and client
3. **No caching** - Pass through all requests to LSP

**Question:** Should pyright-mcp add tool-level caching on top of LSP's internal cache?

---

## Problem

**Potential benefits of tool-level caching:**
- Faster response times for repeated requests
- Reduced LSP load
- Better resource utilization

**Concerns:**
- Cache invalidation complexity
- Stale results
- Memory usage
- Implementation cost

**Need to evaluate:** Does tool-level caching provide meaningful benefit over LSP's internal cache?

---

## Analysis

### LSP Internal Caching (Baseline)

Pyright language server already caches:
- **AST parsing** - File syntax trees
- **Type information** - Resolved types for symbols
- **Module imports** - Dependency graphs
- **Hover results** - Symbol information
- **Completion items** - Available suggestions

**LSP cache invalidation:**
- Automatic on file changes (via file watcher)
- Handles concurrent requests efficiently
- Memory-efficient (LRU eviction)

**Conclusion:** LSP already provides substantial caching.

### Option 1: No Tool-Level Cache ⭐ SELECTED

Pass all requests through to LSP without caching.

**Pros:**
- ✅ Simple implementation (no cache logic)
- ✅ Always fresh results
- ✅ No staleness issues
- ✅ No cache invalidation complexity
- ✅ LSP handles caching internally
- ✅ Lower memory usage

**Cons:**
- May miss optimization opportunities

### Option 2: Tool-Level Response Cache

Cache LSP responses in pyright-mcp.

**Example:**
```python
class ResponseCache:
    def __init__(self):
        self._cache: dict[CacheKey, CacheEntry] = {}

    def get(self, file: Path, line: int, column: int) -> HoverResult | None:
        key = CacheKey(file, line, column)
        entry = self._cache.get(key)

        if entry and not entry.is_stale():
            return entry.result
        return None
```

**Pros:**
- Potentially faster for repeated requests

**Cons:**
- ❌ Complex invalidation (when to clear cache?)
- ❌ Staleness risk (file modified, cache stale)
- ❌ Memory usage (duplicate of LSP cache)
- ❌ Implementation cost (~200-300 lines)
- ❌ Testing complexity (invalidation edge cases)

### Option 3: Intelligent Cache with Invalidation

Tool-level cache with file watcher for invalidation.

**Pros:**
- Avoids staleness with proper invalidation

**Cons:**
- ❌ Very complex implementation
- ❌ Duplicates LSP's file watching
- ❌ Race conditions (LSP updates before cache)
- ❌ High maintenance burden

---

## Decision

**Do not implement tool-level caching. Rely on LSP internal caching.**

**Rationale:**
1. **LSP already caches** - Pyright maintains internal cache
2. **Marginal benefit** - Tool-level cache adds little over LSP cache
3. **High complexity** - Invalidation logic is error-prone
4. **Staleness risk** - File changes may not propagate
5. **Resource overhead** - Memory duplication
6. **Maintenance burden** - Cache bugs are subtle and hard to fix

**User decision:** "no"

**Performance strategy:**
- Phase 2: Rely on LSP internal cache (sufficient)
- Phase 3: Measure actual latency before reconsidering
- Future: Only add caching if profiling shows bottleneck

---

## Consequences

### Positive
- ✅ Simple implementation (pass-through)
- ✅ No staleness issues
- ✅ No invalidation bugs
- ✅ Lower memory usage
- ✅ Less code to maintain
- ✅ LSP cache handles common cases

### Negative
- ⚠️ May miss marginal optimization opportunities

### Neutral
- Can add caching later if profiling shows need
- LSP restart clears LSP cache (acceptable)
- Document manager ensures files are open (LSP can cache)

---

## Performance Analysis

**Typical request flow without tool-level cache:**
```
1. Tool receives request (file, line, column)
2. LSP client sends request
3. Pyright checks internal cache
   - Cache hit (common): <10ms
   - Cache miss (rare): 50-200ms
4. LSP client receives response
5. Tool formats and returns
```

**With tool-level cache:**
```
1. Tool receives request
2. Check tool cache
   - Cache hit: <1ms (small gain over LSP cache hit)
   - Cache miss: Continue to LSP
3-5. (same as above)
```

**Benefit analysis:**
- Best case: Save ~10ms (LSP cache hit → tool cache hit)
- Complexity: ~200-300 lines of cache logic
- Bugs introduced: Cache invalidation edge cases

**Conclusion:** ~10ms gain not worth ~300 lines of complex code.

---

## When to Reconsider

**Conditions for adding tool-level cache:**

1. **Profiling evidence:**
   - LSP cache miss rate > 30%
   - Measured latency > 500ms p95
   - User complaints about performance

2. **Clear bottleneck:**
   - LSP request overhead measured > 100ms
   - Network latency (if LSP becomes remote)
   - LSP startup cost amortization

3. **Solved invalidation:**
   - Clear invalidation strategy
   - Low staleness risk
   - Simple implementation

**Current state:** None of these conditions apply.

---

## Alternative Optimizations

**Instead of tool-level caching, focus on:**

1. **LSP persistence** (Phase 2) ✅
   - Keep LSP running (avoid cold start)
   - Idle timeout for resource management
   - Impact: Saves 3s initialization per request

2. **Document pre-opening** (Phase 2) ✅
   - Open files on first request
   - LSP can cache file contents
   - Impact: Faster subsequent requests

3. **LSP pooling** (Phase 3)
   - Multiple LSP instances for multi-workspace
   - Avoid reinitialization on workspace switch
   - Impact: Better multi-project performance

4. **Per-workspace metrics** (Phase 3)
   - Identify slow workspaces
   - Guide per-project optimization
   - Impact: Actionable performance insights

All of these provide better performance wins than tool-level caching.

---

## Implementation Simplification

**What we WON'T implement:**
```python
# No cache data structures
class ResponseCache: ...

# No cache invalidation logic
def invalidate_cache(self, file: Path): ...

# No file watching for cache
class CacheInvalidator: ...

# No cache metrics
cache_hit_rate: float
cache_miss_count: int
```

**What we WILL do:**
```python
# Simple pass-through
async def hover(...) -> HoverResult:
    # No cache check - go straight to LSP
    return await lsp_client.hover(...)
```

**Simplicity wins.**

---

## Testing Impact

**Tests we DON'T need:**
- Cache hit scenarios
- Cache invalidation triggers
- Staleness detection
- Cache memory limits
- Concurrent cache access
- Cache warming strategies

**Tests we DO need:**
- Direct LSP integration
- LSP restart handling
- Document lifecycle

**Savings:** ~50-100 fewer test cases.

---

## Documentation

**README:**
```markdown
### Performance

pyright-mcp relies on Pyright's internal caching for performance:
- AST parsing cached by Pyright
- Type information cached by Pyright
- LSP remains running for fast subsequent requests

No additional tool-level caching is implemented. This keeps the
implementation simple and avoids cache invalidation complexity.

For multi-workspace performance, see LSP pooling (Phase 3).
```

**FAQ:**
```markdown
**Q: Does pyright-mcp cache results?**

A: No tool-level caching. Pyright language server has its own internal
cache which is sufficient. This avoids cache invalidation complexity
and ensures results are always fresh.

**Q: How can I improve performance?**

A: Ensure LSP timeout is long enough for your workflow
(PYRIGHT_MCP_LSP_TIMEOUT). The LSP stays warm and caches results
internally. For multi-workspace workflows, increase pool size in Phase 3.
```

---

## Alternatives Considered

### Alternative: Aggressive LSP Caching

Keep LSP running indefinitely (no idle timeout).

**Rejected:** Resource waste. Idle timeout with restart is acceptable.

### Alternative: Pre-fetch Common Requests

Predict and pre-fetch likely requests.

**Rejected:**
- Hard to predict user intent
- Wastes resources on unused requests
- Adds complexity

### Alternative: Memcached/Redis External Cache

Use external caching service.

**Rejected:**
- Massive complexity
- Requires infrastructure
- Overkill for local MCP server

---

## References

- LSP Caching: Pyright internal implementation
- Document Manager: `src/pyright_mcp/backends/document_manager.py`
- LSP Client: `src/pyright_mcp/backends/lsp_client.py`
- Related: ADR-001 (Idle Timeout - keeps LSP warm)
- Related: ADR-004 (LSP Pooling - multi-workspace performance)
- TDD Section 14.3: Phase 3 scope (caching removed)
