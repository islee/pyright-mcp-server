# Project Status

**Last Updated:** 2026-01-22
**Current Phase:** Phase 2 Complete (LSP IDE Features)

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

### Verification Results

| Check | Status |
|-------|--------|
| Pyright | 5 warnings (FastMCP decorator, pre-existing) |
| Tests | 270 passed, 1 skipped |
| Coverage | 82% |
| Ruff | Clean |

---

## Implementation Roadmap

| Phase | Status | Deliverables |
|-------|--------|--------------|
| **1: MVP** | **Complete** | `check_types`, `health_check` tools via CLI |
| **2: LSP** | **Complete** | `get_hover`, `go_to_definition` via LSP; CLI stays for `check_types` |
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
│   └── inputs.py         # Input validation (validate_position_input)
├── context/
│   └── project.py        # Project detection
├── backends/
│   ├── base.py           # Backend protocols (Backend, HoverBackend, DefinitionBackend, CompletionBackend)
│   ├── cli_runner.py     # Pyright CLI wrapper
│   ├── lsp_client.py     # LSP subprocess + JSON-RPC (hover, definition, complete)
│   ├── document_manager.py # LSP document lifecycle
│   └── selector.py       # HybridSelector (CLI for check, LSP for hover/def)
└── tools/
    ├── check_types.py    # check_types MCP tool
    ├── health_check.py   # health_check MCP tool
    ├── hover.py          # get_hover MCP tool
    └── definition.py     # go_to_definition MCP tool

tests/
├── conftest.py           # Shared fixtures
├── unit/                 # Unit tests (16 files)
└── integration/          # Integration tests
```

---

## Next Phase: Phase 3 (Production Polish)

**Scope:** Add completions, references, LSP pooling, metrics

**New tools:**
- `get_completions` - Code completion suggestions
- `find_references` - Find all references to symbol

**New infrastructure:**
- `backends/lsp_pool.py` - Multi-workspace LSP pooling with LRU eviction
- `metrics.py` - Performance tracking

**Foundations already in place:**
- `CompletionBackend` protocol in `base.py`
- `complete()` method in `lsp_client.py`
- Activity tracking for idle timeout

See [docs/TDD.md](docs/TDD.md) Section 14 for full Phase 3 plan.

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
