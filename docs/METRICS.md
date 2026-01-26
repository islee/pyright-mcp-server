# Metrics Guide

Per-workspace metrics collection enables performance monitoring and debugging in multi-workspace environments.

## Overview

pyright-mcp automatically tracks performance metrics for each workspace:
- Operation counts (hover, definition, completion, references)
- Average latencies per operation (in milliseconds)
- Error counts per operation

Metrics are collected across all tool invocations and can be viewed via the `health_check` tool when using the `PooledSelector` (Phase 3+).

## Viewing Metrics

### Via health_check Tool

Access metrics through the `health_check` MCP tool:

```python
result = await health_check()
metrics = result.get("metrics", {})
workspaces = metrics.get("workspaces", [])
```

Response structure:

```json
{
  "metrics": {
    "uptime_seconds": 123.45,
    "workspaces": [
      {
        "workspace": "/path/to/workspace",
        "operations": {
          "hover": {
            "count": 10,
            "avg_ms": 25.5,
            "errors": 0
          },
          "definition": {
            "count": 5,
            "avg_ms": 35.2,
            "errors": 1
          },
          "completion": {
            "count": 3,
            "avg_ms": 40.1,
            "errors": 0
          },
          "references": {
            "count": 2,
            "avg_ms": 50.0,
            "errors": 0
          }
        }
      }
    ]
  }
}
```

## Metrics Collected

### Per Operation

Each operation (hover, definition, completion, references) tracks:

| Metric | Type | Description |
|--------|------|-------------|
| `count` | Integer | Number of times this operation was invoked |
| `avg_ms` | Float | Average execution time in milliseconds |
| `errors` | Integer | Number of failed invocations |

### Per Workspace

Aggregated across all operations:

| Metric | Type | Description |
|--------|------|-------------|
| `workspace` | String | Root path of the workspace |
| `operations` | Dict | Per-operation metrics (hover, definition, completion, references) |

### Server-Wide

| Metric | Type | Description |
|--------|------|-------------|
| `uptime_seconds` | Float | Seconds since metrics collector initialization |

## Interpreting Metrics

### Cache Hit Rate (LSP Pool)

Via `health_check` lsp_pool stats:

```python
cache_hit_rate = result.get("lsp_pool", {}).get("cache_hit_rate", 0.0)
# 0.667 = 66.7% cache hit rate
# Higher is better (indicates good workspace locality)
```

**Interpretation:**
- **> 80%**: Excellent. Workspaces are well-localized.
- **60-80%**: Good. Normal multi-workspace performance.
- **< 60%**: Consider increasing `PYRIGHT_MCP_LSP_POOL_SIZE` if workspaces are repeatedly evicted.

### Operation Latencies

Compare average latencies across operations and workspaces:

```python
hover_avg = workspace_metrics["operations"]["hover"]["avg_ms"]
definition_avg = workspace_metrics["operations"]["definition"]["avg_ms"]
```

**Interpretation:**
- **< 100ms**: Excellent. Likely cached LSP responses.
- **100-300ms**: Normal. Expected for first access or complex files.
- **> 500ms**: Slow. Investigate Pyright configuration or file complexity.

### Error Rates

Track operation reliability:

```python
hover_count = workspace_metrics["operations"]["hover"]["count"]
hover_errors = workspace_metrics["operations"]["hover"]["errors"]
error_rate = hover_errors / hover_count if hover_count > 0 else 0.0
```

**Interpretation:**
- **0%**: Perfect. No errors.
- **< 5%**: Good. Occasional transient errors.
- **> 5%**: Investigate. May indicate configuration issues or edge cases.

## Performance Tuning

### High Cache Hit Rate But Slow Latencies

**Symptom:** Cache hit rate > 80%, but `avg_ms` > 300ms

**Causes:**
- Complex Python files requiring slow analysis
- Slow system or insufficient memory
- Suboptimal Pyright configuration

**Solutions:**
1. Review `pyrightconfig.json` for performance settings
2. Check system resources (CPU, memory)
3. Profile Pyright with `pyright --version` and compare with baseline

### Low Cache Hit Rate

**Symptom:** Cache hit rate < 60%

**Causes:**
- Working across many unrelated workspaces
- Pool size too small for your workflow
- Rapid workspace switching

**Solutions:**
1. Increase `PYRIGHT_MCP_LSP_POOL_SIZE`:
   ```bash
   export PYRIGHT_MCP_LSP_POOL_SIZE=5  # default is 3
   ```

2. Organize workspaces by locality (minimize context switches)

3. Check eviction count:
   ```python
   evictions = result.get("lsp_pool", {}).get("eviction_count", 0)
   ```

### High Error Rates

**Symptom:** Operation `errors` > 0

**Causes:**
- Files with syntax errors
- Misconfigured Pyright settings
- LSP server crashes or timeouts

**Solutions:**
1. Check LSP logs: `PYRIGHT_MCP_LOG_LEVEL=DEBUG`
2. Validate workspace with `check_types` tool
3. Ensure `pyrightconfig.json` is valid JSON
4. Check system resources (memory, CPU)

### Unbalanced Operation Latencies

**Symptom:** Some operations much slower than others

**Example:** Definition avg_ms: 200, Hover avg_ms: 25

**Causes:**
- Definition operations may require more analysis
- Some workspaces more complex than others
- Legitimate differences in operation complexity

**Solutions:**
1. Baseline expectations - definition is inherently slower
2. Profile slow workspaces separately
3. Consider increasing `PYRIGHT_MCP_LSP_TIMEOUT` if workspaces are large

## Examples

### Monitor a Single Workspace

```python
result = await health_check()
target_workspace = "/path/to/project"

for ws_metrics in result["metrics"]["workspaces"]:
    if ws_metrics["workspace"] == target_workspace:
        ops = ws_metrics["operations"]
        print(f"Hover avg: {ops['hover']['avg_ms']:.1f}ms")
        print(f"Definition avg: {ops['definition']['avg_ms']:.1f}ms")
        print(f"Completion avg: {ops['completion']['avg_ms']:.1f}ms")
```

### Find Slow Operations

```python
result = await health_check()
slow_threshold = 200  # milliseconds

for ws_metrics in result["metrics"]["workspaces"]:
    workspace = ws_metrics["workspace"]
    for op_name, op_stats in ws_metrics["operations"].items():
        if op_stats["avg_ms"] > slow_threshold:
            print(f"{workspace} {op_name}: {op_stats['avg_ms']:.1f}ms")
```

### Track Pool Efficiency

```python
result = await health_check()
pool = result.get("lsp_pool", {})

efficiency = pool["cache_hit_rate"]
utilization = pool["active_instances"] / pool["max_instances"]

print(f"Pool cache hit rate: {efficiency:.1%}")
print(f"Pool utilization: {utilization:.1%}")
print(f"Evictions: {pool['eviction_count']}")
```

## Notes

- Metrics are per-session (reset when server restarts)
- Averages are calculated in real-time (not pre-aggregated)
- Error tracking includes all exceptions during operation
- LSP pool stats require `PooledSelector` (Phase 3+)

For detailed performance analysis, enable debug logging:

```bash
PYRIGHT_MCP_LOG_LEVEL=DEBUG uv run python -m pyright_mcp
```

See [STATUS.md](../STATUS.md) for Phase 3 implementation details.
