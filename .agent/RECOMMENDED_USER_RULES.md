# Recommended User Global Rules for Claude Code Behavior
# ====================================================
# Copy the content below into your Antigravity User Rules settings
# Location: Antigravity → Settings → User Rules (or Memory[user_global])

---

# Project Rules (Personal/Local)

## Core Behavior: Claude Code Emulation
- **Read Before Write**: ALWAYS use view_file or view_file_outline before ANY code modification. NEVER modify code you haven't read first.
- **Direct Execution**: NEVER respond with "I'll do X". Just provide the actual code implementation immediately.
- **Complete Solutions**: Always provide complete, executable code. No placeholders like `# ...` or `// TODO`.
- **Surgical Precision**: Prefer replace_file_content over write_to_file with Overwrite. Make minimal, targeted changes.

## Verification Protocol
- **Verify After Every Change**: Run syntax checks and tests after every edit.
- **Fix Immediately**: If errors occur, fix them before proceeding. Never leave broken code.
- **Test Commands**: 
  - Python: `pytest tests/ -v` or `python -m unittest discover tests -v`
  - Node: `npm test`
  - Build: Check with appropriate build command

## Code Quality Standards
- **Match Existing Patterns**: Follow the project's conventions, not your preferences.
- **Type Hints**: Use modern typing in Python (list, dict, str | None).
- **Error Handling**: Don't suppress errors. Handle them explicitly.
- **No Silent Failures**: Always report and handle errors properly.

## Safety Guidelines
- **Preserve Working Code**: Don't rewrite working code unless broken or explicitly requested.
- **Minimize Blast Radius**: Prefer changes that affect fewer files.
- **Dependencies**: If you add a new library, remind to install it or update project files.

## Communication
- **Context Aware**: Check docs/00-central-design.md (if available) to align with existing architecture.
- **Ask for Clarification**: If unsure, ask rather than assume.
- **Acknowledge Mistakes**: Admit and correct errors when they occur.

---

# How These Rules Work Together

1. **Before ANY edit**: Read the file first (Read Before Write)
2. **When editing**: Use minimal, precise changes (Surgical Precision)
3. **After editing**: Run tests immediately (Verify After Every Change)
4. **If tests fail**: Fix before doing anything else (Fix Immediately)
5. **Throughout**: Follow project patterns (Match Existing Patterns)

---

# Usage Notes

- These rules are meant to be copied into your Antigravity user settings
- They complement the .agent/skills/claude-code-behavior/SKILL.md skill
- For project-specific rules, use .agent/skills/ in each project
