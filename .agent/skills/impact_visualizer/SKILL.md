---
name: Impact-Visualizer
description: "Tracks code changes with Before/After tables AND maintains a 5-file Memory Bank (projectbrief, activeContext, systemPatterns, techContext, progress) that serves as the agent's persistent memory across sessions. Also keeps README.md updated as human-readable project overview."
---

# Impact-Visualizer v2.0 — Change Tracker & Memory Bank Keeper

This skill executes automatically **at the very end** of every response where code is modified. It has TWO core responsibilities:

1. **Change Log Summary** — Before/after comparison table (inline in response)
2. **Memory Bank Maintenance** — Update the 5-file context system for cross-session continuity

---

## Part 1: Change Log Summary (Always Required When Code Changes)

### When to Apply
- ✅ Created a new file with code
- ✅ Modified existing code
- ✅ Deleted or renamed files
- ✅ Added/removed dependencies
- ✅ Modified configuration files

### When to Skip
- ❌ Only answered a question without code changes
- ❌ Only read/viewed files
- ❌ Only ran commands without editing code

### Output Format

At the **end of every response** where code was modified:

```markdown
---
### 📋 Change Log Summary

| Metric | Details |
| :--- | :--- |
| **📂 Files Modified** | `[filenames]` |
| **🔴 Before** | *[Previous logic, bug, or missing feature]* |
| **🟢 After** | *[New logic, fix, or added feature]* |
| **✨ Key Changes** | • *[Bullet 1]*<br>• *[Bullet 2]*<br>• *[More as needed]* |
---
```

### Quality Standards
- **Be specific**: Reference actual function names, variable names, logic patterns
- **Be quantified**: Include metrics when applicable (performance, line count, etc.)
- **Group by domain**: When 4+ files modified, group as Backend/UI/Config

---

## Part 2: Memory Bank — The 5-File Context System

### Overview

The Memory Bank is a set of 5 markdown files in `docs/` that form the agent's persistent memory. Together they answer every question an agent needs:

```
docs/
├── projectbrief.md     ← WHAT is this project? (rarely changes)
├── activeContext.md    ← WHAT's happening NOW? (changes every session)
├── systemPatterns.md   ← HOW is code organized? (changes when architecture evolves)
├── techContext.md      ← WHAT tools are used? (changes when stack changes)
└── progress.md         ← WHAT's done/pending? (changes every session)
```

### Relationship Between Files

```
projectbrief.md (Foundation — defines EVERYTHING)
     ↓ informs
systemPatterns.md (HOW we build it)
techContext.md (WHAT we build with)
     ↓ tracks
activeContext.md (WHERE we are right now)
progress.md (HOW FAR we've come)
```

---

### File 1: `docs/projectbrief.md` — Project Brief

**Purpose:** The compass of the project. Defines what the product is, who it's for, and what it must do.

**When to Create:** First significant session with a new project.
**When to Update:** Only when project scope/goals fundamentally change.

**Template:**
```markdown
# Project Brief: [Project Name]

## 🎯 Core Purpose
[One paragraph: What does this application do?]

## 👥 Target Users
[Who is the end user? What are their needs?]

## ✅ Must-Have Features
1. [Feature 1]
2. [Feature 2]
3. [Feature 3]

## 🚫 Out of Scope
- [What this project does NOT do]

## 📐 Success Criteria
- [How do we know it's working correctly?]
```

---

### File 2: `docs/activeContext.md` — Active Context (Short-Term Memory)

**Purpose:** The agent's working memory. What's happening RIGHT NOW. This is the most frequently updated file.

**When to Create:** First session.
**When to Update:** **Every session** with code changes. This file is OVERWRITTEN (not appended) — it always reflects the CURRENT state.

**Template:**
```markdown
# Active Context

## 🎯 Current Focus
[What are we working on right now?]

## 📝 Recent Changes
- [YYYY-MM-DD] [Change 1: what and why]
- [YYYY-MM-DD] [Change 2: what and why]
- [YYYY-MM-DD] [Change 3: what and why]

## ⚡ Next Steps
1. [Immediate next action]
2. [Follow-up action]

## 🐛 Active Issues
- [Any bugs or blockers currently being addressed]

## 💡 Key Decisions Made
- [Decision 1: chose X over Y because...]
- [Decision 2: ...]
```

**Rules:**
- Keep this SHORT — max ~50 lines. It's a snapshot, not a history.
- Recent Changes: Keep only the last 5-10 entries. Old ones move to `progress.md`.
- Overwrite on each session — don't let it grow unbounded.

---

### File 3: `docs/systemPatterns.md` — System Patterns & Architecture

**Purpose:** How the codebase is organized. Prevents the agent from writing code that breaks existing structure.

**When to Create:** After the first session where architecture is established.
**When to Update:** When architecture, patterns, or conventions change.

**Template:**
```markdown
# System Patterns

## 📁 Project Structure
```
[Directory tree of key folders/files]
```

## 🏗️ Architecture
[Pattern used: MVC, Clean Architecture, Microservices, Monolith, etc.]
[Diagram or description of how components interact]

## 📐 Key Conventions
- **Naming**: [snake_case / camelCase / PascalCase for what]
- **File Organization**: [Where new components go]
- **State Management**: [How state is handled]
- **Error Handling**: [Pattern for error handling]
- **API Pattern**: [How endpoints are structured]

## 🔗 Component Relationships
- [Component A] → calls → [Component B]
- [Component C] → depends on → [Component D]

## ⚠️ Critical Rules
- [Rule 1: e.g., UI layer must NOT import business logic directly]
- [Rule 2: e.g., All API calls go through the service layer]
```

---

### File 4: `docs/techContext.md` — Technical Context

**Purpose:** The toolbox. What languages, frameworks, and tools the project uses. How to set up and run it.

**When to Create:** First session.
**When to Update:** When new dependencies are added, environment changes, or build steps change.

**Template:**
```markdown
# Technical Context

## 🛠️ Tech Stack
| Layer | Technology | Version |
|---|---|---|
| Language | [e.g., Python] | [3.11+] |
| Framework | [e.g., FastAPI] | [0.100+] |
| UI | [e.g., React + Vite] | [18.x] |
| Database | [e.g., SQLite] | |
| Auth | [e.g., Firebase] | |

## 📦 Key Dependencies
- [Library 1] — [what it's used for]
- [Library 2] — [what it's used for]

## 🚀 Setup & Run
```bash
# Install
[install command]

# Run dev
[dev command]

# Run tests
[test command]

# Build
[build command]
```

## 🌐 Environment Variables
| Variable | Purpose | Where Set |
|---|---|---|
| `API_URL` | Backend endpoint | `.env.local` |

## 🔌 External Services
| Service | Purpose | Credentials Location |
|---|---|---|
| [e.g., Firebase] | Auth | `src/config/firebase.js` |
| [e.g., PayOS] | Payments | Hardcoded in server |

## ⚠️ Technical Constraints
- [e.g., Must run on WSL Ubuntu]
- [e.g., Docker required for TTS engine]
```

---

### File 5: `docs/progress.md` — Progress Tracker

**Purpose:** Kanban board in text form. What's done, what's in progress, what's known to be broken.

**When to Create:** First session.
**When to Update:** **Every session** with code changes.

**Template:**
```markdown
# Project Progress

## ✅ Completed
- [x] [Feature/task 1] — [date or brief note]
- [x] [Feature/task 2]
- [x] [Feature/task 3]

## 🔄 In Progress
- [ ] [Feature/task currently being worked on]
- [ ] [Feature/task partially done]

## 📋 Planned / Backlog
- [ ] [Future feature 1]
- [ ] [Future feature 2]

## 🐛 Known Issues
- [Bug 1: description, severity, workaround if any]
- [Bug 2: description]

## 📊 Milestones
| Milestone | Status | Key Components |
|---|---|---|
| MVP | ✅ Complete | Core features working |
| v2.0 | 🔄 In Progress | New UI + admin panel |
```

---

## Memory Bank Update Rules

### Which Files to Update Per Session

| What Happened | activeContext | progress | systemPatterns | techContext | projectbrief |
|---|---|---|---|---|---|
| Code changes (normal) | ✅ Update | ✅ Update | ❌ Skip | ❌ Skip | ❌ Skip |
| New feature complete | ✅ Update | ✅ Update | ❌ Skip | ❌ Skip | ❌ Skip |
| Architecture changed | ✅ Update | ✅ Update | ✅ Update | ❌ Skip | ❌ Skip |
| New dependency added | ✅ Update | ✅ Update | ❌ Skip | ✅ Update | ❌ Skip |
| Project scope changed | ✅ Update | ✅ Update | ❌ Skip | ❌ Skip | ✅ Update |
| Bug fixed | ✅ Update | ✅ Update | ❌ Skip | ❌ Skip | ❌ Skip |
| Only answered questions | ❌ Skip | ❌ Skip | ❌ Skip | ❌ Skip | ❌ Skip |

### General Rules
1. **Always update `activeContext.md`** when code changes — it's the short-term memory
2. **Always update `progress.md`** when code changes — track what got done
3. **Don't over-update** — only touch files where the content actually changed
4. **Create missing files** — if a Memory Bank file doesn't exist, create it
5. **Keep `activeContext.md` lean** — overwrite, don't append forever
6. **Keep `progress.md` cumulative** — append completed items, update in-progress

---

## README.md Maintenance (Separate from Memory Bank)

`README.md` at the project root is the **human-readable project overview**. It's less agent-focused than the Memory Bank but still valuable.

### When to Update README.md
- ✅ Architecture/topology fundamentally changed
- ✅ New server/endpoint/database added
- ✅ Project doesn't have a README yet (create one)
- ❌ Normal code changes (Memory Bank covers this)

### README vs Memory Bank

| Aspect | README.md | Memory Bank (docs/) |
|---|---|---|
| **Audience** | Humans + Agents | Primarily Agents |
| **Content** | Project overview, setup, architecture diagram | Detailed operational context |
| **Update Frequency** | Rare (major changes only) | Every session |
| **Format** | Freeform, project-specific | Standardized 5-file template |

---

## Execution Flow

```
Code modification detected
     ↓
Part 1: Generate Change Log Summary table
  → Append to end of response
     ↓
Part 2: Update Memory Bank
  → ALWAYS: Update activeContext.md (current focus, recent changes, next steps)
  → ALWAYS: Update progress.md (mark completed, update in-progress)
  → IF architecture changed: Update systemPatterns.md
  → IF new deps/tools: Update techContext.md
  → IF scope changed: Update projectbrief.md
  → IF files don't exist: Create them from templates
     ↓
Part 3: Update README.md (only if architecture/topology changed)
     ↓
Response delivered to user
```

## Integration with Auto-Contextualizer

```
Session Start (Auto-Contextualizer reads):
  activeContext.md → What are we doing now?
  progress.md → What's done/pending?
  projectbrief.md → What is this project?
  systemPatterns.md → How is code organized?
  techContext.md → What tools do we use?
       ↓
  Execute with full context + activated skills
       ↓
Session End (Impact-Visualizer writes):
  activeContext.md ← Update current state
  progress.md ← Update what got done
  [others if needed]
  Change Log ← Inline in response

= Self-documenting feedback loop =
```
