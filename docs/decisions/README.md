# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records documenting significant design decisions for pyright-mcp-server.

## Index

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [ADR-001](ADR-001-automatic-lsp-idle-timeout.md) | Automatic LSP Idle Timeout Enforcement | Accepted | 2026-01-26 |
| [ADR-002](ADR-002-pyright-version-tracking.md) | Pyright Version Compatibility Tracking | Accepted | 2026-01-26 |
| [ADR-003](ADR-003-per-workspace-metrics.md) | Per-Workspace Metrics Granularity | Accepted | 2026-01-26 |
| [ADR-004](ADR-004-lsp-pool-sizing-strategy.md) | LSP Pool Size Strategy | Accepted | 2026-01-26 |
| [ADR-005](ADR-005-simplified-timeout-strategy.md) | Simplified Timeout Strategy | Accepted | 2026-01-26 |
| [ADR-006](ADR-006-no-tool-level-caching.md) | No Tool-Level Caching | Accepted | 2026-01-26 |

## By Phase

### Phase 2.5 (Hardening)
- **ADR-001:** Automatic idle timeout enforcement (background watcher)
- **ADR-002:** Pyright version compatibility tracking (health check)

### Phase 3 (Production)
- **ADR-003:** Per-workspace metrics granularity
- **ADR-004:** LSP pool sizing strategy (default 3, monitor)
- **ADR-005:** Simplified timeout strategy (no adaptive logic)
- **ADR-006:** No tool-level caching (rely on LSP)

## By Category

### Performance & Resource Management
- ADR-001: Automatic LSP Idle Timeout Enforcement
- ADR-004: LSP Pool Size Strategy
- ADR-005: Simplified Timeout Strategy
- ADR-006: No Tool-Level Caching

### Observability & Monitoring
- ADR-002: Pyright Version Compatibility Tracking
- ADR-003: Per-Workspace Metrics Granularity

## ADR Template

Each ADR follows this structure:

```markdown
# ADR-XXX: Title

**Date:** YYYY-MM-DD
**Status:** Proposed | Accepted | Deprecated | Superseded
**Decision:** One-line summary

## Context
[Background and problem statement]

## Problem
[What needs solving]

## Analysis
[Options considered with pros/cons]

## Decision
[What we're doing and why]

## Consequences
### Positive
### Negative
### Neutral

## Alternatives Considered
[Why other options were rejected]

## References
[Related code, docs, ADRs]
```

## Related Documentation

- **TDD.md** - Technical Design Document (references ADRs in sections 8.2, 14.2, 14.3)
- **IMPLEMENTATION.md** - Implementation plan
- **STATUS.md** - Current project status

## ADR Lifecycle

**Statuses:**
- **Proposed** - Under discussion
- **Accepted** - Decision made, ready to implement
- **Deprecated** - No longer recommended
- **Superseded** - Replaced by another ADR

**When to create an ADR:**
- Architectural decisions (backend choice, protocol selection)
- Design patterns (caching strategy, error handling)
- Trade-offs (performance vs simplicity)
- Cross-cutting concerns (logging, metrics)

**When NOT to create an ADR:**
- Implementation details (variable names, file locations)
- Trivial decisions (obvious best practice)
- Temporary workarounds
- Decisions easily reversed

## Contributing

When adding a new ADR:
1. Copy template structure
2. Number sequentially (ADR-007, ADR-008, ...)
3. Add to this index
4. Reference in relevant documentation (TDD.md, IMPLEMENTATION.md)
5. Update related code comments with ADR reference
