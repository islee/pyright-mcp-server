# Project Status

**Last Updated:** 2026-01-22
**Current Phase:** Phase 1 Complete (PR Ready)

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
- [x] Test suite (183 tests, 89% coverage)
- [x] Backend selector interface (`backends/selector.py`)

### Verification Results

| Check | Status |
|-------|--------|
| Pyright | 0 errors |
| Tests | 183 passed, 1 skipped |
| Coverage | 89% |
| Ruff | Clean |

---

## Implementation Roadmap

| Phase | Status | Deliverables |
|-------|--------|--------------|
| **1: MVP** | **Complete** | `check_types`, `health_check` tools via CLI |
| **2: LSP** | Planned | `get_hover`, `go_to_definition` via LSP; CLI stays for `check_types` |
| **3: Production** | Planned | `get_completions`, `find_references`, LSP pooling, metrics |

---

## File Structure

```
src/pyright_mcp/
├── __init__.py
├── __main__.py           # Entry point
├── server.py             # FastMCP server setup
├── config.py             # Configuration management
├── logging_config.py     # Logging infrastructure
├── utils/
│   ├── position.py       # Position/Range handling
│   └── uri.py            # Path/URI conversion
├── validation/
│   ├── paths.py          # Path validation
│   └── inputs.py         # Input validation
├── context/
│   └── project.py        # Project detection
├── backends/
│   ├── base.py           # Backend protocol
│   ├── cli_runner.py     # Pyright CLI wrapper
│   └── selector.py       # Backend selector interface
└── tools/
    ├── check_types.py    # check_types MCP tool
    └── health_check.py   # health_check MCP tool

tests/
├── conftest.py           # Shared fixtures
├── unit/                 # Unit tests (167 tests)
└── integration/          # Integration tests (16 tests)
```

---

## Next Phase: Phase 2 (LSP for Hover/Definition)

**Scope:** Add `get_hover` and `go_to_definition` via Pyright LSP

**Key architectural decision:** LSP for IDE features only, CLI stays for type checking
- `check_types` → CLI (publishDiagnostics is async notification, not request)
- `get_hover` → LSP (textDocument/hover is sync request/response)
- `go_to_definition` → LSP (textDocument/definition is sync request/response)

**New files:**
- `backends/lsp_client.py` - LSP subprocess + JSON-RPC
- `backends/document_manager.py` - didOpen/didClose lifecycle
- `tools/hover.py` - get_hover MCP tool
- `tools/definition.py` - go_to_definition MCP tool

**Modified files:**
- `backends/base.py` - HoverBackend, DefinitionBackend protocols
- `backends/selector.py` - HybridSelector (CLI for check, LSP for hover/def)

**Implementation order:**
1. Protocol extension (base.py)
2. LSP client (lsp_client.py)
3. Hover tool (hover.py)
4. Document manager (document_manager.py)
5. Definition tool (definition.py)
6. Selector update (selector.py)
7. Integration tests

See [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md) for full plan.

---

## Quick Commands

```bash
# Install dependencies
pip install -e ".[dev]"

# Run server
python -m pyright_mcp

# Run tests
pytest tests/ -v

# Type check
pyright src/

# Lint
ruff check src/ tests/
```

---

## Phase 1 Review (2026-01-22)

### Code Review Summary

| Category | Found | Resolved |
|----------|-------|----------|
| Critical Issues | 4 | 4 ✓ |
| Recommendations | 8 | 6 ✓ |
| Architecture Concerns | 4 | 4 ✓ |

### Critical Issues - All Resolved ✓

| # | Issue | Resolution |
|---|-------|------------|
| 1 | Duplicate condition in `or` expression | Fixed in `5932bdd` |
| 2 | `_server_start_time` set at import | Changed to lazy init |
| 3 | `type: ignore` for severity | Replaced with `cast()` |
| 4 | `type: ignore` for log_mode | Replaced with `cast()` |

### Recommendations Status

| Priority | Issue | Status |
|----------|-------|--------|
| High | Missing tests for `health_check.py` | ✓ Resolved (12 tests) |
| High | Missing tests for `logging_config.py` | ✓ Resolved (18 tests) |
| High | Missing tests for `server.py` | ✓ Resolved (14 tests) |
| Medium | Error codes are strings, not enum | Deferred to Phase 2 |
| Medium | TOML parsing is regex-based | ✓ Resolved (tomli) |
| Medium | Double path validation | Deferred (minor) |
| Low | Hardcoded 5s timeout | Deferred (minor) |
| Low | Bare `except Exception` | Deferred (minor) |

### Architecture Concerns - All Resolved ✓

| # | Issue | Resolution |
|---|-------|------------|
| 1 | TDD/impl mismatch for BackendError | TDD updated in `eb11f9f` |
| 2 | Protocol only has `check()` | Added `shutdown()` in `90ee4f9` |
| 3 | Sync I/O in async function | Wrapped with `asyncio.to_thread()` |
| 4 | No backend selector | Added `backends/selector.py` |

### Phase 2 Readiness - Improved

| Gap | Status |
|-----|--------|
| Backend Selection | ✓ `selector.py` with `Backend` protocol |
| Document Lifecycle | Deferred to Phase 2 |
| Workspace Awareness | Deferred to Phase 2 |
| Cancellation | Deferred to Phase 2 |

### Strengths

- Clean module boundaries that will scale to Phase 2
- Discriminated union responses match TDD specification
- Position indexing with `from_lsp()`/`to_lsp()` ready for LSP
- Security-first CLI execution (no shell=True)
- Explicit logging initialization in `__main__.py`
- Minimal dependencies (`mcp`, `pyright`, `tomli`)
- 89% test coverage with comprehensive unit tests
