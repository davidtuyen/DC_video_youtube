# Antigravity Agent Template

This repository contains curated Antigravity workflows and skills for rapid project setup.

## Contents

### Workflows (`workflows/`)
- **safe-code-edit.md** - Careful code editing with verification
- **fix-bug.md** - Systematic bug fixing
- **add-feature.md** - TDD feature implementation
- **code-review.md** - Comprehensive code review
- **security-review.md** - Security-focused review
- **explore-codebase.md** - Systematic codebase exploration
- Plus 10 more specialized workflows

### Skills (`skills/`)
- **claude-code-behavior/** - Claude Code emulation (hardened for Antigravity)
- **python-modern-typing/** - Modern Python standards enforcement
- **ui-ux-pro-max-skill/** - Advanced UI/UX design intelligence
- Plus 20+ specialized skills

## Usage

### Quick Start
```powershell
# In your new project
git clone https://github.com/yourusername/antigravity-template .agent-temp
cp -r .agent-temp/.agent .
rm -rf .agent-temp
```

### Manual Copy
```powershell
cp -r <path-to-this-repo>/.agent <your-project>/.agent
```

## Version History
- v2.0 (2026-01-18): Platform hardening - Removed aggressive turbo from risky operations
- v1.0 (2026-01-17): Initial Claude Code port

## Notes
- Workflows have been hardened for Antigravity platform stability
- `// turbo` kept only for safe read operations
- Tested on Windows 11 with Antigravity v1.x
