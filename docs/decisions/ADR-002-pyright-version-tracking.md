# ADR-002: Pyright Version Compatibility Tracking

**Date:** 2026-01-26
**Status:** Accepted
**Decision:** Add Pyright version check to health_check tool with compatibility warnings

---

## Context

pyright-mcp depends on Pyright's CLI `--outputjson` format for type checking. The project currently specifies `pyright>=1.1.0` in dependencies with no upper bound.

**Risk:** Pyright is under active development. JSON output format could change in breaking ways:
- Field renames (e.g., `generalDiagnostics` → `diagnostics`)
- Schema changes (e.g., severity encoding)
- New diagnostic types
- Removal of fields

**Current state:**
- No version tracking in health_check
- No compatibility validation
- Users may encounter cryptic parse errors after Pyright upgrade
- Testing is done against specific Pyright versions but not documented

---

## Problem

**When Pyright releases breaking changes:**

1. **User experience is poor:**
   ```
   ERROR: Failed to parse Pyright output: KeyError 'generalDiagnostics'
   ```
   User doesn't know if the problem is:
   - Pyright installation
   - pyright-mcp bug
   - Version incompatibility

2. **No early warning:**
   - Error only appears when running type checks
   - By then, user may have upgraded Pyright system-wide
   - Downgrading is non-trivial

3. **Undocumented compatibility:**
   - README says `pyright>=1.1.0`
   - But which versions are actually tested?
   - What happens with Pyright 2.0?

---

## Analysis

### Option 1: Strict Version Pinning

Pin Pyright version: `pyright==1.1.350`

**Pros:**
- Guaranteed compatibility
- No surprise breakage

**Cons:**
- Users can't get Pyright bug fixes
- Locks ecosystem to old versions
- Incompatible with global Pyright installations

**Rejected:** Too restrictive for a development tool.

### Option 2: Version Range with Upper Bound

Specify tested range: `pyright>=1.1.350,<1.2.0`

**Pros:**
- Allows patch releases
- Prevents major version surprises

**Cons:**
- Still restrictive
- May block legitimate upgrades
- Hard to maintain upper bound

**Rejected:** Better than strict pinning, but still too rigid.

### Option 3: Version Check with Warnings ⭐ SELECTED

Check Pyright version at runtime, warn on incompatibility.

**Pros:**
- Allows any Pyright version
- Provides early warning
- Documents tested versions
- Doesn't block users

**Cons:**
- Warning may be ignored
- Users can still run incompatible versions

**Selected:** Best balance of flexibility and safety.

---

## Decision

**Add Pyright version check to `health_check` tool with compatibility validation.**

**Implementation:**
1. Run `pyright --version` in health_check
2. Parse version string (e.g., "pyright 1.1.350")
3. Compare against tested version range (1.1.350+)
4. Add warning to diagnostics if incompatible
5. Include version in health_check response

**Location:** `src/pyright_mcp/tools/health_check.py`

**Documentation:**
- README: Document tested version range
- CHANGELOG: Note tested versions per release
- Health check: Report version + compatibility

---

## Consequences

### Positive
- ✅ Early incompatibility detection (before type check fails)
- ✅ Users see version in health_check output
- ✅ Warnings guide troubleshooting
- ✅ Documented compatibility baseline
- ✅ No restrictions on Pyright version

### Negative
- ⚠️ Warnings may be ignored by users
- ⚠️ Requires maintenance as tested versions change

### Neutral
- Version check adds ~50ms to health_check (subprocess call)
- Check only runs on health_check invocation (not per type check)

---

## Implementation Details

**Version Check Logic:**
```python
def _is_version_compatible(version: str) -> bool:
    """Check if Pyright version is compatible."""
    major, minor, patch = map(int, version.split("."))

    # Minimum tested version: 1.1.350
    if major < 1:
        return False
    if major == 1 and minor < 1:
        return False
    if major == 1 and minor == 1 and patch < 350:
        return False

    return True  # All newer versions assumed compatible until proven otherwise
```

**Health Check Response:**
```json
{
  "status": "healthy",
  "pyright_available": true,
  "pyright_version": "1.1.350",
  "diagnostics": []
}

// Or with warning:
{
  "status": "degraded",
  "pyright_available": true,
  "pyright_version": "1.1.100",
  "diagnostics": [
    "Pyright version 1.1.100 may be incompatible. Tested with 1.1.350+"
  ]
}
```

**README Update:**
```markdown
## Requirements

- Python 3.10+
- Pyright 1.1.350+ (tested with 1.1.350-1.1.400)

Run `health_check` to verify compatibility.
```

---

## Testing Strategy

**Unit tests:**
```python
def test_version_compatibility_check():
    assert _is_version_compatible("1.1.350") == True
    assert _is_version_compatible("1.1.400") == True
    assert _is_version_compatible("1.2.0") == True
    assert _is_version_compatible("1.1.100") == False
    assert _is_version_compatible("1.0.0") == False

async def test_health_check_includes_version():
    result = await health_check()
    assert "pyright_version" in result
    if result["pyright_available"]:
        assert result["pyright_version"] is not None
```

**Integration test:**
```python
async def test_health_check_warns_incompatible_version():
    # Mock old Pyright version
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = CompletedProcess(
            args=["pyright", "--version"],
            returncode=0,
            stdout="pyright 1.1.100\n",
        )
        result = await health_check()
        assert any("may be incompatible" in d for d in result["diagnostics"])
```

---

## Future Work

**Potential enhancements:**
1. **Version-specific adapters** - Handle breaking changes gracefully
2. **Compatibility matrix** - Document tested combinations
3. **Auto-update checks** - Notify of new Pyright releases

**Not doing now:**
- Automatic Pyright installation (users manage their own)
- Version-specific code paths (handle breaking changes when they occur)
- Pyright upgrade prompts (advisory only)

---

## Alternatives Considered

### Alternative: No Version Check

**Rejected:** Leaves users with cryptic errors.

### Alternative: Fail on Incompatible Version

Raise error instead of warning.

**Rejected:** Too strict. Warning allows users to proceed at their own risk (e.g., if they know their version works).

### Alternative: Download Specific Pyright Binary

Bundle compatible Pyright version.

**Rejected:**
- Increases package size significantly
- Complicates cross-platform distribution
- Users often have system Pyright already

---

## References

- Implementation: `src/pyright_mcp/tools/health_check.py`
- Tests: `tests/unit/test_health_check.py`
- Pyright releases: https://github.com/microsoft/pyright/releases
- TDD Section 5.9: Health Check Tool
