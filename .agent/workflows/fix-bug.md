---
description: Debug and fix a bug with proper verification
---

# Bug Fix Workflow

Follow this systematic approach for debugging and fixing issues.

## 1. Reproduce the Problem
// turbo
```
First, understand and reproduce the bug:
- Get exact error message
- Identify the failing test/behavior
- Run the failing command to see the error
```

## 2. Locate the Source
```
Use grep_search and view_file to find:
- The file(s) where the error occurs
- The exact line causing the issue
- Related code paths
```

## 3. Understand the Root Cause
```
Analyze WHY the bug happens:
- Is it a logic error?
- Missing edge case handling?
- Wrong assumptions about input?
- Race condition?
```

## 4. Write a Failing Test (if not exists)
```
Create a test that reproduces the bug:
- This prevents regression
- Confirms when the fix works
```

## 5. Implement the Fix
```
Make the MINIMAL change to fix the issue:
- Don't refactor unrelated code
- Don't "improve" things while fixing
- Focus on the specific bug
```

## 6. Verify the Fix
```
Run the specific test:
- pytest tests/test_specific.py -v
- npm test -- --grep "test name"
```

## 7. Run Full Test Suite
```
Ensure no regressions:
- pytest tests/ -v
- npm test
```

## 8. Document the Fix
```
Add a brief comment or commit message explaining:
- What the bug was
- Why it happened
- How it was fixed
```

## Anti-patterns to Avoid
- **Don't guess**: Understand the root cause before fixing
- **Don't over-fix**: Change only what's needed
- **Don't skip tests**: Always verify the fix works
- **Don't ignore related issues**: Note any other problems found
