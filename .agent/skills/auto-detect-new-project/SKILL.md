---
name: auto-detect-new-project
description: "Automatically detect when user opens a new project without .agent folder and suggest linking to global config"
globs:
  - "**/*"
alwaysApply: false
priority: low
---

# Auto-Detect New Project

## Detection Logic

When the user opens a conversation in a new project directory:

1. **Check for `.agent` folder**
   - If NOT exists → Suggest linking to global
   - If exists but NOT a junction → Mention global option
   - If already linked → Silent (don't annoy user)

2. **Suggest Command**
   ```
   Detected new project without global agent link.
   
   Would you like to link to global config? Run:
   C:\Users\PC\.antigravity-global\quick-link.ps1
   
   Or if you have profile installed:
   lag
   ```

## When to Suggest

- At start of conversation
- User mentions "new project", "setup", "initialize"
- User asks about workflows/skills availability

## When NOT to Suggest

- If .agent already exists
- If user is just asking questions (not coding)
- More than once per conversation
