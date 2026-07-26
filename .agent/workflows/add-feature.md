---
description: Add a new feature with proper TDD and verification
---

# Add Feature Workflow

Use this workflow when implementing new functionality.

## 1. Understand Requirements
```
Clarify with the user:
- What exactly should the feature do?
- What are the edge cases?
- Are there any constraints?
```

## 2. Research Existing Code
```
Use codebase_search and grep_search to find:
- Similar existing implementations
- Related files and modules
- Existing patterns to follow
```

## 3. Plan the Implementation
```
Identify:
- Which files need to be created/modified
- What dependencies are needed
- How this integrates with existing code
```

## 4. Write Tests First (TDD)
```
Create test cases that define expected behavior:
- Happy path tests
- Edge case tests
- Error handling tests
```

## 5. Run Tests (Should Fail)
```
Run tests to confirm they fail (Red phase):
- pytest tests/ -v
- npm test
```

## 6. Implement Feature
```
Write minimal code to pass the tests:
- Follow existing code patterns
- Add proper error handling
- Include type hints and docstrings
```

## 7. Run Tests Again (Should Pass)
```
Verify all tests pass (Green phase):
- pytest tests/ -v
- npm test
```

## 8. Refactor (if needed)
```
Clean up the implementation:
- Remove duplication
- Improve naming
- Optimize if necessary
```

## 9. Final Verification
```
Run full test suite and any linters:
- pytest tests/ -v
- npm run lint
- mypy src/
```

## 10. Document
```
Update relevant documentation:
- README if user-facing
- Docstrings for functions/classes
- CHANGELOG if applicable
```
