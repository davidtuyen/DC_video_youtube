---
description: Perform a thorough code review on specified files
---

# Code Review Workflow

Use this workflow to review code quality and identify issues.

## 1. Read the Target Files
// turbo
```
Use view_file_outline to get structure overview
Then use view_file to read the full content
```

## 2. Check Code Quality
```
Evaluate these aspects:

### Correctness
- [ ] Logic is correct
- [ ] Edge cases handled
- [ ] Error handling present
- [ ] No obvious bugs

### Readability
- [ ] Clear variable/function names
- [ ] Appropriate comments
- [ ] Consistent formatting
- [ ] Not overly complex

### Maintainability  
- [ ] Single responsibility principle
- [ ] No code duplication
- [ ] Proper abstraction level
- [ ] Easy to modify

### Security
- [ ] Input validation
- [ ] No hardcoded secrets
- [ ] Safe SQL/file operations
- [ ] Proper authentication checks

### Performance
- [ ] No obvious inefficiencies
- [ ] Appropriate data structures
- [ ] No memory leaks
- [ ] Reasonable resource usage
```

## 3. Check Test Coverage
```
Find associated tests:
- grep_search for test files
- Check if tests cover main functionality
```

## 4. Run Static Analysis
```
Run linters and type checkers:
- Python: mypy src/ && flake8 src/
- JavaScript: npm run lint
- TypeScript: npx tsc --noEmit
```

## 5. Run Tests
```
Ensure all tests pass:
- pytest tests/ -v
- npm test
```

## 6. Provide Feedback
```
Summarize findings:
- Critical issues (must fix)
- Suggestions (should consider)
- Positive observations (good practices)
```

## Review Output Format
```markdown
## Code Review: [filename]

### ✅ Strengths
- [positive observations]

### ⚠️ Issues Found
1. **[Severity]**: [Issue description]
   - Location: line X
   - Suggestion: [how to fix]

### 💡 Recommendations
- [optional improvements]
```
