---
description: Safe and careful code editing workflow (Claude Code style)
---

# Safe Code Edit Workflow

Follow these steps for ANY code modification:

## 1. Analyze the Target
// turbo
```
Use view_file_outline to understand the file structure
```

## 2. Read Relevant Sections
// turbo
```
Use view_file with StartLine/EndLine to read the specific code you need to modify
```

## 3. Identify Dependencies
```
Use grep_search to find other files that import or use the target code
(Manual execution recommended to avoid platform path issues)
```

## 4. Make Minimal Changes
```
Use replace_file_content (single change) or multi_replace_file_content (multiple non-adjacent changes)
NEVER use write_to_file with Overwrite unless creating new files
```

## 5. Verify Syntax
```
Run language-specific syntax check:
- Python: python -m py_compile <file>
- TypeScript/JavaScript: npx tsc --noEmit <file>
- Go: go vet <file>
(Execute manually to review results before proceeding)
```

## 6. Run Tests
```
Run the test suite:
- Python: pytest tests/ -v
- Node: npm test
- Go: go test ./...
(Execute after reviewing syntax check results)
```

## 7. Fix Issues (if any)
```
If syntax errors or test failures occur, fix immediately before proceeding
```

## Important Notes
- **NEVER skip step 1 and 2** - Always read before editing
- **Prefer surgical precision** - Only change what needs to be changed
- **Match existing style** - Follow the project's conventions
