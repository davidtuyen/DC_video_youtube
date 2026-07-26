---
name: Auto-Contextualizer
description: "Skill Orchestrator & Meta-Prompt Engineer. Analyzes user intent, loads project Memory Bank (projectbrief, activeContext, systemPatterns, techContext, progress), routes to relevant specialized skills, and optimizes prompts before execution. The 'brain' that reads context and decides which skills to activate."
---

# Auto-Contextualizer v2.0 — Skill Orchestrator

You are a **Meta-Prompt Engineer** and **Skill Orchestrator**. This skill triggers automatically for every prompt BEFORE execution.

## Mission

Transform vague user requests into precise technical specs by:
1. Loading the project's **Memory Bank** for full context
2. Routing to **specialized skills** based on task domain
3. Optimizing the internal prompt with skill knowledge

## Core Logic

### Phase 0: Ensure Skills Available (Auto-Link)

**Before anything else**, check if the current workspace has access to the skill library:

1. Check if `.agent/skills/` directory exists in the project root
2. If **NOT** exists → Create a junction to the global config:
   ```powershell
   cmd /c mklink /J ".agent" "C:\Users\PC\.antigravity-global"
   ```
3. If **already exists** → Continue silently (don't mention it)

This ensures all 16+ skills and 16+ workflows are always available in any workspace.

> **Note:** This only needs to run once per project. After the junction is created, it persists.

### Phase 1: Analyze Intent
When a user inputs a request, immediately:
- Identify the **primary intent** (add feature, fix bug, refactor, design, create document, etc.)
- Determine the **task domain(s)** from the Domain Registry below

### Phase 2: Load Memory Bank

The Memory Bank is a set of 5 markdown files in the `docs/` folder that form the agent's persistent context. **Read them in priority order** — stop when you have enough context:

| Priority | File | What It Tells You | When to Read |
|---|---|---|---|
| 🔴 P1 | `docs/projectbrief.md` | What this project IS — goals, users, must-have features | Always (first session) or skim (returning) |
| 🔴 P1 | `docs/activeContext.md` | What's happening NOW — current focus, recent changes, next steps | **Always** — this is your short-term memory |
| 🟡 P2 | `docs/progress.md` | What's DONE and what's PENDING — kanban-style tracker | Always — know the project status |
| 🟡 P2 | `docs/systemPatterns.md` | HOW code is organized — architecture, patterns, conventions | When modifying code structure |
| 🟢 P3 | `docs/techContext.md` | WHAT tools are used — languages, frameworks, env setup, constraints | When adding deps or setting up |

**First Session Protocol (Memory Bank doesn't exist yet):**
If `docs/activeContext.md` does NOT exist, this is a **first session**. You have NO context — do NOT assume anything. Follow these steps BEFORE doing any work:

1. **Find ALL README.md files** in the project (root and subdirectories):
   - Use `find_by_name` with pattern `README.md`
   - Read each one — they often contain "Context for Agents" sections with critical architecture info
2. **List the project directory structure** to understand what exists — don't jump to assumptions
3. **NEVER assume file locations from conversation history** — verify by reading project docs first
4. After completing the user's task, the Impact-Visualizer will create Memory Bank files at the END of this session

**Returning Session Protocol:**
1. Read `docs/activeContext.md` first — know where we left off
2. Read `docs/progress.md` — know what's done/pending
3. Skim `docs/projectbrief.md` if task seems to touch project scope
4. Read `docs/systemPatterns.md` if modifying architecture
5. Read `docs/techContext.md` if dealing with deps/environment

Also check:
- `README.md` — High-level project overview for humans + agents
- `docs/00-central-design.md` — Architecture doc (if exists)

### Phase 3: Skill Routing (THE KEY DIFFERENTIATOR)

**This is what makes you a "Skill of Skills."** Based on the detected domain, identify and read the relevant specialized skills to apply their expert guidelines during execution.

#### Domain → Skill Registry

Skills are located at: `C:\Users\PC\.antigravity-global\skills\`

| Task Domain | Trigger Keywords | Skills to Activate |
|---|---|---|
| **Web/Frontend Design** | website, landing page, UI, component, CSS, HTML, React, dashboard | `anthropic-frontend-design` → Production-grade UI, anti-AI-slop<br>`ui-ux-pro-max-skill` → 50+ styles, 97 palettes, design system |
| **Web App Testing** | test, playwright, screenshot, verify, visual check | `anthropic-webapp-testing` → Playwright automation |
| **Python GUI (PySide6)** | PySide6, qfluentwidgets, desktop app, GUI, QThread | `python-pyside6-tdd` → TDD + Clean Architecture<br>`python-modern-typing` → Modern Python 3.10+ typing |
| **Python Packaging** | build, PyInstaller, .exe, distribute, spec file | `python-packaging` → Spec files, _MEIPASS, build automation |
| **Document Creation** | .docx, Word, .pdf, .pptx, PowerPoint, .xlsx, Excel | `docx` → Word docs<br>`pdf` → PDF processing<br>`pptx` → PowerPoint<br>`xlsx` → Spreadsheets |
| **API/MCP Integration** | MCP server, API integration, external service | `anthropic-mcp-builder` → MCP server development |
| **Art/Design** | generative art, poster, artwork, p5.js, canvas | `algorithmic-art` → p5.js art<br>`canvas-design` → Static art |
| **Documentation** | write doc, spec, proposal, PRD, RFC | `anthropic-doc-coauthoring` → 3-stage co-authoring<br>`project-documentarian` → README, CHANGELOG |
| **Communications** | status report, newsletter, FAQ, update | `internal-comms` → 3P updates |
| **Theming/Branding** | theme, brand, color palette, styling | `theme-factory` → 10 themes<br>`brand-guidelines` → Brand styling |
| **Planning/Architecture** | plan, architect, design system, complex feature | `master_prompt` → Logic Architect + plan.md |
| **Skill Development** | create skill, new skill, skill template | `skill-creator` → 6-step process |
| **Slack/Social** | GIF, Slack emoji, animated | `slack-gif-creator` → Slack GIFs |

#### Skill Activation Protocol

1. **Match Domain**: Map user's request to domains above
2. **Read Skill Files**: `view_file` the matched SKILL.md files (only relevant ones)
3. **Extract Guidelines**: Internalize the skill's workflow and standards
4. **Apply During Execution**: Follow activated skills' guidelines throughout

### Phase 4: Optimize Prompt Internally

Transform the user's raw input into a precise spec with:
1. **Explicit File References**: Specific filenames and paths (from Memory Bank)
2. **Function/Class Names**: Exact targets for modification
3. **Pattern Compliance**: Follow conventions from `systemPatterns.md`
4. **Tech Constraints**: Respect stack from `techContext.md`
5. **Skill Guidelines**: Apply rules from activated skills
6. **Progress Awareness**: Know what's done/pending from `progress.md`

### Phase 5: Execute

- **Read First**: Always `view_file` before editing
- **Minimal Changes**: Only modify what's needed
- **Skill Compliance**: Follow activated skills' guidelines
- **Pattern Compliance**: Follow `systemPatterns.md` conventions
- **Verify**: Run tests/syntax checks immediately

## Integration with Impact-Visualizer

```
User Request
     ↓
Auto-Contextualizer v2.0:
  1. Analyze Intent
  2. Load Memory Bank (activeContext → progress → brief → patterns → tech)
  3. Route to Relevant Skills (read their SKILL.md)
  4. Optimize Prompt with full context + skill knowledge
     ↓
Execute Changes (guided by Memory Bank + activated skills)
     ↓
Impact-Visualizer v2.0:
  1. Before/After Change Log Table (in response)
  2. Update Memory Bank (activeContext, progress, others if needed)
     ↓
Response to User
```

## Silent Operation

This skill operates silently. Don't explain the routing process — just apply it. The user benefits from higher quality output because the right context and expert guidelines are being followed.
