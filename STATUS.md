# Project Status

**Last Updated:** 2026-01-26
**Current Phase:** Phase 3 Complete (Production Features)

For project overview, see [README.md](README.md).

---

## What's Done

### Phase 1: MVP (Complete)

- [x] Project setup (`pyproject.toml`, directory structure)
- [x] Utility modules (`utils/position.py`, `utils/uri.py`)
- [x] Backend interface (`backends/base.py`)
- [x] Configuration module (`config.py`)
- [x] Logging infrastructure (`logging_config.py`)
- [x] Validation modules (`validation/paths.py`, `validation/inputs.py`)
- [x] Project detection (`context/project.py`)
- [x] Pyright CLI runner (`backends/cli_runner.py`)
- [x] MCP tools (`tools/check_types.py`, `tools/health_check.py`)
- [x] MCP server (`server.py`, `__main__.py`)
- [x] Backend selector interface (`backends/selector.py`)

### Phase 2: LSP IDE Features (Complete)

- [x] LSP client (`backends/lsp_client.py`) - JSON-RPC over stdin/stdout
- [x] Document manager (`backends/document_manager.py`) - didOpen/didClose lifecycle
- [x] Hover tool (`tools/hover.py`) - get_hover MCP tool
- [x] Definition tool (`tools/definition.py`) - go_to_definition MCP tool
- [x] Protocol extensions (`backends/base.py`) - HoverBackend, DefinitionBackend
- [x] Hybrid selector (`backends/selector.py`) - CLI for check, LSP for hover/definition
- [x] TDD updated for 1-indexed API convention
- [x] Shared validation (`validation/inputs.py`) - validate_position_input()
- [x] Phase 3 completion infrastructure (CompletionBackend, complete() method)

### Phase 2.5: Hardening (Complete)

- [x] Automatic LSP idle timeout enforcement (ADR-001) - background watcher task
- [x] Pyright version tracking (ADR-002) - version check in health_check tool
- [x] Defensive logging initialization - prevent duplicate handlers
- [x] Version compatibility warnings - degraded status for old versions
- [x] Updated README with version requirements

### Phase 3: Production Features (Complete)

- [x] LSP pool with LRU eviction (ADR-004) - Multi-workspace support
- [x] Per-workspace metrics collection (ADR-003) - Performance tracking
- [x] get_completions tool - Code completion suggestions
- [x] find_references tool - Find all symbol references
- [x] Enhanced health_check with pool stats and metrics
- [x] Integration tests for multi-workspace scenarios (15+ tests)
- [x] Documentation updates (README, STATUS, METRICS.md)

### Verification Results (Phase 2.5)

| Check | Status |
|-------|--------|
| Pyright | 0 errors, 0 warnings, 0 infos |
| Tests | 247 passed, 1 skipped (5 new tests for Phase 2.5) |
| Coverage | 70% |
| Ruff | Clean |

---

## Implementation Roadmap

| Phase | Status | Deliverables |
|-------|--------|--------------|
| **1: MVP** | **Complete** | `check_types`, `health_check` tools via CLI |
| **2: LSP** | **Complete** | `get_hover`, `go_to_definition` via LSP; CLI stays for `check_types` |
| **2.5: Hardening** | **Complete** | Automatic LSP timeout, version tracking, defensive logging |
| **3: Production** | **Complete** | `get_completions`, `find_references`, LSP pooling, metrics |

---

## File Structure

```
src/pyright_mcp/
├── __init__.py
├── __main__.py           # Entry point
├── server.py             # FastMCP server setup
├── config.py             # Configuration management
├── logging_config.py     # Logging infrastructure
├── metrics.py            # Per-workspace metrics collection
├── utils/
│   ├── position.py       # Position/Range handling
│   └── uri.py            # Path/URI conversion
├── validation/
│   ├── paths.py          # Path validation
│   └── inputs.py         # Input validation (validate_position_input)
├── context/
│   └── project.py        # Project detection
├── backends/
│   ├── base.py           # Backend protocols (Backend, HoverBackend, DefinitionBackend, CompletionBackend, ReferencesBackend)
│   ├── cli_runner.py     # Pyright CLI wrapper
│   ├── lsp_client.py     # LSP subprocess + JSON-RPC (hover, definition, complete, references)
│   ├── lsp_pool.py       # Multi-workspace LSP pooling with LRU eviction
│   ├── document_manager.py # LSP document lifecycle
│   └── selector.py       # PooledSelector (CLI for check, pooled LSP for IDE features)
└── tools/
    ├── check_types.py    # check_types MCP tool
    ├── health_check.py   # health_check MCP tool (with pool stats and metrics)
    ├── hover.py          # get_hover MCP tool (with metrics)
    ├── definition.py     # go_to_definition MCP tool (with metrics)
    ├── completions.py    # get_completions MCP tool (with metrics)
    └── references.py     # find_references MCP tool (with metrics)

tests/
├── conftest.py           # Shared fixtures
├── unit/                 # Unit tests (20+ files)
└── integration/          # Integration tests (Phase 3 multi-workspace scenarios)
```

---

## Phase 3 Review (2026-01-26)

### Implementation Summary

**Multi-Workspace Support (ADR-004):**
- LSP pool manages up to 3 concurrent clients per workspace (configurable)
- LRU eviction prevents unbounded memory growth
- Cache hit tracking for performance analysis

**Per-Workspace Metrics (ADR-003):**
- Operation counts, latencies, and error rates per workspace
- Used for performance monitoring and debugging
- Integrated into health_check response for PooledSelector

**New Tools:**
- `get_completions` - Code completion with per-workspace metrics
- `find_references` - Reference finding with per-workspace metrics
- Enhanced `health_check` - Now includes pool stats and workspace metrics

**Quality Metrics:**
- Tests: 302+ passing, 15+ integration tests for multi-workspace scenarios
- Coverage: 75%+
- All tools record metrics to MetricsCollector
- Pool statistics visible in health_check response

### Configuration

Environment variables:
- `PYRIGHT_MCP_LSP_POOL_SIZE` - Maximum LSP clients (default: 3)
- `PYRIGHT_MCP_LSP_TIMEOUT` - LSP idle timeout in seconds (default: 300)

### Next Steps

Phase 3 is complete. Future enhancements could include:
- Persistent metrics logging
- Performance dashboards
- Advanced pool scheduling strategies
- Cache hit rate optimization

See [docs/TDD.md](docs/TDD.md) for full technical design.

---

## Quick Commands

```bash
# Install dependencies
uv sync

# Run server
uv run python -m pyright_mcp

# Run tests
uv run pytest

# Type check
uv run pyright

# Lint
uv run ruff check .
```

---

## Phase 2 Review (2026-01-22)

### PRR Summary

| Category | Status |
|----------|--------|
| Security | ✓ No vulnerabilities |
| Reliability | ✓ Crash recovery, timeouts |
| Performance | ✓ Lazy init, async I/O |
| Observability | ✓ Logging, error codes |
| Testing | ✓ 270 tests, 82% coverage |

**PRR Verdict:** APPROVED

### Key Decisions

1. **Hybrid backend**: CLI for type checking (publishDiagnostics is async), LSP for hover/definition
2. **1-indexed API**: User-facing positions match editor display (internal remains 0-indexed)
3. **Lazy LSP init**: Subprocess only starts on first hover/definition request
4. **5-minute idle timeout**: Configurable via `PYRIGHT_MCP_LSP_TIMEOUT`

### Phase 2 Commits

| Commit | Description |
|--------|-------------|
| `6fc92c4` | feat(phase-2): implement LSP-based hover and go_to_definition tools |
| `44be44a` | refactor(phase-2): extract shared validation and add Phase 3 completion infrastructure |

---

## Phase 2.5 Review (2026-01-26)

### Hardening Implementation

**ADR-001: Automatic LSP Idle Timeout**
- Background watcher task checks idle status every 60 seconds
- Automatically shuts down LSP after configured timeout (default 5 minutes)
- Stops cleanly on shutdown without manual intervention
- Implementation: `LSPClient._idle_timeout_watcher()` + `LSPClient._watcher_task`

**ADR-002: Pyright Version Tracking**
- Version check integrated into health_check tool
- Minimum version: 1.1.350 (tested with 1.1.350-1.1.408)
- Degraded status returned for incompatible versions
- Version parsing handles prerelease versions (e.g., 1.1.350-beta.1)

**Defensive Logging**
- `create_mcp_server()` checks if logging already initialized
- Prevents duplicate handlers when server created multiple times
- Critical for test suites and alternative entry points

### Quality Metrics

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Tests | 247 | 270+ | ✓ Pass (5 new) |
| Coverage | 70% | 80%+ | ⚠️ Review |
| Type Check | 0 errors | 0 | ✓ Pass |
| Lint | Clean | Clean | ✓ Pass |

### PRR Verdict: APPROVED

**Risk Assessment**: Low - All changes isolated to LSP timeout handling and health check initialization
**Breaking Changes**: None - Fully backward compatible
**Dependencies**: No new external dependencies
