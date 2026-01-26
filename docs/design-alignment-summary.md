# Design Documentation Alignment Summary

**Date:** 2026-01-26
**Action:** Reformatted architectural review into proper ADR format per knowledge management protocols

---

## What Was Done

### 1. Created Architecture Decision Records (ADRs)

Following the ADR format from `~/.claude/docs/decisions/ADR-001-remove-general-purpose-agent.md`, created six ADRs documenting Phase 2.5 and Phase 3 design decisions:

| ADR | Title | Category |
|-----|-------|----------|
| ADR-001 | Automatic LSP Idle Timeout Enforcement | Phase 2.5 Hardening |
| ADR-002 | Pyright Version Compatibility Tracking | Phase 2.5 Hardening |
| ADR-003 | Per-Workspace Metrics Granularity | Phase 3 Production |
| ADR-004 | LSP Pool Size Strategy | Phase 3 Production |
| ADR-005 | Simplified Timeout Strategy | Phase 3 Production |
| ADR-006 | No Tool-Level Caching | Phase 3 Production |

**Location:** `docs/decisions/`

### 2. Updated TDD.md with Implementation Details

Updated existing Technical Design Document sections:

- **Section 8.2:** Added defensive logging initialization pattern
- **Section 14.2:** Added automatic idle timeout enforcement details
- **Section 14.3:** Refined Phase 3 plan with design decisions and ADR references
- **Revision history:** Added version 0.7 entry documenting changes

### 3. Created ADR Index

Created `docs/decisions/README.md` with:
- Table of all ADRs
- Organization by phase and category
- ADR template for future decisions
- Guidelines for when to create ADRs

---

## Alignment with Documentation Standards

### Per `documentation-awareness.md`

| Trigger | Required Doc | Status |
|---------|--------------|--------|
| Breaking changes | ADR + migration guide | ✅ ADR-001 (idle timeout), ADR-002 (version check) |
| New patterns | Pattern documentation | ✅ Documented in ADRs |
| Config changes | Config documentation | ✅ ADR-004, ADR-005 (env vars documented) |

### Per ADR Format Standard

Each ADR follows the established format:
- ✅ Date, Status, Decision summary
- ✅ Context (background and problem)
- ✅ Analysis (options with pros/cons)
- ✅ Decision (what and why)
- ✅ Consequences (positive, negative, neutral)
- ✅ Alternatives Considered
- ✅ References (code, tests, related docs)

### Documentation Location Consistency

| Doc Type | Location | Status |
|----------|----------|--------|
| Architecture decisions | `docs/decisions/ADR-*.md` | ✅ Created |
| Technical design | `docs/TDD.md` | ✅ Updated |
| Product requirements | `docs/PRD.md` | ✅ Existing |
| Implementation plan | `docs/IMPLEMENTATION.md` | ✅ Existing |
| Project status | `STATUS.md` | ✅ Existing |

---

## Before vs After

### Before (Design Revision Document)

```
# Design Revision: pyright-mcp-server

## 1. Summary of Changes
...
## 2. Phase 2.5 Hardening
...
## 3. Phase 3 Design Refinements
...
```

**Issues:**
- ❌ Freeform structure
- ❌ No location standard
- ❌ Mixed decisions and implementation
- ❌ Not discoverable

### After (ADRs + TDD Updates)

**ADRs:**
```
docs/decisions/
├── ADR-001-automatic-lsp-idle-timeout.md
├── ADR-002-pyright-version-tracking.md
├── ADR-003-per-workspace-metrics.md
├── ADR-004-lsp-pool-sizing-strategy.md
├── ADR-005-simplified-timeout-strategy.md
├── ADR-006-no-tool-level-caching.md
└── README.md (index)
```

**TDD.md:**
- Section 8.2: Implementation patterns with ADR references
- Section 14.2: Phase 2 details with ADR-001, ADR-005
- Section 14.3: Phase 3 scope with ADR-003, ADR-004, ADR-006

**Benefits:**
- ✅ Standardized format
- ✅ Clear location
- ✅ Decisions separated from implementation
- ✅ Discoverable via index
- ✅ Referenced from TDD

---

## Design Decisions Captured

### Phase 2.5 (Hardening)

**ADR-001: Automatic LSP Idle Timeout**
- Decision: Background watcher task
- Rationale: Reliable enforcement without manual calls
- Impact: Prevents memory leaks

**ADR-002: Pyright Version Tracking**
- Decision: Add version check to health_check
- Rationale: Early incompatibility detection
- Impact: Better user guidance

### Phase 3 (Production)

**ADR-003: Per-Workspace Metrics**
- Decision: Track metrics per workspace (not global)
- Rationale: Identify slow projects, guide tuning
- Impact: Actionable performance insights

**ADR-004: LSP Pool Sizing**
- Decision: Default 3 instances, monitor usage
- Rationale: Covers typical workflows, tune with data
- Impact: Defer optimization until production metrics

**ADR-005: Simplified Timeout**
- Decision: Single configurable timeout (no adaptive)
- Rationale: Simple, predictable, sufficient
- Impact: Lower complexity, easy to understand

**ADR-006: No Tool-Level Cache**
- Decision: Rely on LSP internal cache
- Rationale: LSP caching sufficient, avoid staleness
- Impact: Simpler implementation, no invalidation bugs

---

## Integration Points

### With TDD.md

ADRs referenced in:
- Section 8.2: Logging (defensive initialization)
- Section 14.2: Phase 2 (ADR-001, ADR-005)
- Section 14.3: Phase 3 (ADR-003, ADR-004, ADR-006)
- Revision history: Version 0.7 entry

### With IMPLEMENTATION.md

ADRs provide decision rationale for:
- Phase 2.5 implementation tasks
- Phase 3 feature prioritization
- Removed features justification

### With STATUS.md

ADRs clarify:
- Current phase decisions
- Future phase scope
- Monitoring strategies

---

## Documentation Maintenance

### When to Update ADRs

- **Status changes:** Proposed → Accepted → Deprecated
- **New learnings:** Add to "Future Considerations"
- **Superseded:** Link to replacement ADR

### When to Create New ADRs

Per `docs/decisions/README.md`:
- Architectural decisions
- Design patterns
- Trade-offs
- Cross-cutting concerns

**Not for:**
- Implementation details
- Trivial decisions
- Temporary workarounds

---

## Next Steps

### For Phase 2.5 Implementation

1. Read ADR-001 before implementing idle timeout watcher
2. Read ADR-002 before adding version check to health_check
3. Update TDD Section 8.2 implementation code samples
4. Add ADR references to code comments:
   ```python
   # Automatic idle timeout enforcement (ADR-001)
   async def _idle_timeout_watcher(self):
       ...
   ```

### For Phase 3 Planning

1. Review ADR-003, ADR-004, ADR-006 before implementation
2. Use ADRs as requirements for implementation tasks
3. Update ADRs with monitoring results
4. Create follow-up ADRs if decisions change

### For Documentation

1. Link ADRs from README (user-facing summary)
2. Reference ADRs in code comments (implementation)
3. Update ADRs when decisions change or are superseded
4. Keep `docs/decisions/README.md` index current

---

## Verification

**Documentation standards compliance:**

| Standard | Requirement | Status |
|----------|-------------|--------|
| ADR format | Use established template | ✅ All 6 ADRs |
| Location | `docs/decisions/` | ✅ Created |
| Index | README with table | ✅ Created |
| Integration | Link from TDD | ✅ Updated |
| Revision history | Document changes | ✅ Version 0.7 |

**Documentation triggers (from `documentation-awareness.md`):**

| Trigger | Required | Completed |
|---------|----------|-----------|
| Breaking changes | ADR | ✅ ADR-001, ADR-002 |
| New patterns | Documentation | ✅ In ADRs |
| Config changes | Config docs | ✅ ADR-004, ADR-005 |

---

## Summary

Successfully reformatted architectural review into standards-compliant documentation:

- **6 ADRs** created following established format
- **TDD.md** updated with implementation details and ADR references
- **Index** created for discoverability
- **Integration** maintained across documents (TDD, IMPLEMENTATION, STATUS)

All documentation now aligns with knowledge management protocols and ADR standards.
