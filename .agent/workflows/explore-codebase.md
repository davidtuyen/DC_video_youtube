---
description: Systematically explore and understand codebase structure
---

# Explore Codebase Workflow

Systematic codebase exploration workflow adapted from Claude Code's Explore agent.

## Critical: Read-Only Mode
**This is STRICTLY READ-ONLY. You are PROHIBITED from:**
- Creating new files
- Modifying existing files
- Deleting files
- Moving or copying files
- Any state-changing operations

## 1. Get Repository Overview
// turbo
```
list_dir at repository root
View README.md or similar documentation
```

## 2. Identify Key Directories
```
Use find_by_name to locate:
- Source code directories (src/, lib/, app/)
- Test directories (tests/, test/, __tests__)
- Configuration files (*.config.*, *.json, *.yaml)
- Documentation (docs/, README*)
```

## 3. Analyze Project Structure
// turbo
```
Common patterns to identify:
- Backend vs Frontend organization
- Monorepo vs Single project
- Main entry points
- Build system files
```

## 4. Search for Specific Patterns (if needed)
```
Use grep_search for:
- Class/function definitions
- Import/require patterns
- API endpoints
- Database models
- Environment variables
```

## 5. Read Key Files
```
Use view_file_outline first to understand structure
Then view_file for detailed reading:
- Main entry point files
- Core business logic
- Configuration files
- Important utilities
```

## 6. Parallel Operations for Efficiency
```
ALWAYS make parallel tool calls when searching:
- Multiple grep_search calls for different patterns
- Multiple view_file calls for independent files
- Combine find_by_name with grep_search
```

## Efficient Search Strategy

### For File Names
```
Use find_by_name with patterns:
- **/*.py (all Python files)
- **/test_*.py (test files)
- **/*config* (config files)
```

### For File Contents
```
Use grep_search with regex:
- "class \w+" (class definitions)
- "def \w+\(" (function definitions)
- "import|require" (dependencies)
- "TODO|FIXME|HACK" (code comments)
```

### For Specific Files
```
Use view_file when you know exact path:
- Read package.json, requirements.txt
- Read main entry points
- Read core module files
```

## Output Format
```
Report findings as:

## Codebase Structure
- Language: [Python/JavaScript/etc]
- Type: [Web app/Library/CLI tool]
- Framework: [Django/React/etc]

## Key Directories
- `/src/` - [description]
- `/tests/` - [description]

## Entry Points
- `file.py` - [purpose]

## Core Modules
- `module1/` - [responsibility]
- `module2/` - [responsibility]

## Notable Patterns
- [Architecture pattern used]
- [Testing strategy]
- [Build/deployment approach]
```

## Speed Optimization
- ✅ Use parallel tool calls aggressively
- ✅ Use glob patterns for broad searches
- ✅ Read file outlines before full content
- ❌ Don't read every file sequentially
- ❌ Don't repeat searches with slight variations
