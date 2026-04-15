---
name: fix-bug
description: Use when fixing any bug or error
---

# Fix Bug Procedure

1. **Reproduce:** Find the exact error message and trace
   - Read the error carefully, not just the headline
   - Understand the conditions that trigger it
   - Note the call stack and affected code paths

2. **Locate:** Identify the module and function
   - Use grep/Glob to find where the bug manifests
   - Read the code context (5 lines before/after)
   - Don't assume — verify with actual code

3. **Root Cause:** Understand WHY, not just WHERE
   - Ask: "What assumption is wrong here?"
   - Check: boundary conditions, null checks, type mismatches
   - Trace: how data flows into the broken code

4. **Fix:** Minimal change, do not refactor unrelated code
   - Change only what's necessary to fix the bug
   - Don't "improve" while fixing
   - Don't rename variables or reorganize logic

5. **Test:** Add regression test that fails without fix
   - Write test case that reproduces the bug
   - Verify test fails before fix, passes after
   - Run full test suite: `pytest tests/ -v`

6. **Log:** Update CHANGELOG.md and .claude/rules/bugs.md
   - Add entry to CHANGELOG.md [Unreleased] section
   - Update .claude/rules/bugs.md with resolution
   - Commit message: `fix: <issue title> (root cause explanation)`

## PROHIBITED

- Rewriting entire module to "fix" one bug
- "Just in case" changes to unrelated code
- Removing code that might be used somewhere
- Merging multiple bug fixes in one commit
- Fixing a symptom instead of the root cause
