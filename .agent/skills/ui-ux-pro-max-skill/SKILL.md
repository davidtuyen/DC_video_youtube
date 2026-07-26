---
name: ui-ux-pro-max
description: "UI/UX design intelligence. 50 styles, 21 palettes, 50 font pairings, 20 charts, 9 stacks. Actions: plan, build, create, design, implement, review, fix, improve. Projects: website, landing page, dashboard, admin panel, e-commerce, SaaS, portfolio, mobile app."
globs:
  - "**/*.html"
  - "**/*.js"
  - "**/*.jsx"
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.vue"
  - "**/*.svelte"
  - "**/*.css"
  - "**/*.scss"
  - "**/*.dart"
  - "**/*.swift"
  - "**/*.kt"
  - "**/*.py"
alwaysApply: true
priority: medium
---

# UI/UX Pro Max - Design Intelligence

Comprehensive design guide for web and mobile applications. Contains 50+ styles, 97 color palettes, 57 font pairings, 99 UX guidelines, and 25 chart types across 9 technology stacks. Searchable database with priority-based recommendations.

## When to Apply

Reference these guidelines when:
- Designing new UI components or pages
- Choosing color palettes and typography
- Reviewing code for UX issues
- Building landing pages or dashboards
- Implementing accessibility requirements

## How to Use This Skill

When user requests UI/UX work (design, build, create, implement, review, fix, improve), follow this workflow:

### Step 1: Analyze User Requirements

Extract key information from user request:
- **Product type**: SaaS, e-commerce, portfolio, dashboard, landing page, etc.
- **Style keywords**: minimal, playful, professional, elegant, dark mode, etc.
- **Industry**: healthcare, fintech, gaming, education, etc.
- **Stack**: React, Vue, Next.js, or default to `html-tailwind`

### Step 2: Generate Design System (REQUIRED)

**Always start with `--design-system`** to get comprehensive recommendations with reasoning.
Run this command from the project root:

```bash
python .agent/skills/ui-ux-pro-max-skill/.claude/skills/ui-ux-pro-max/scripts/search.py "<product_type> <industry> <keywords>" --design-system
```

**Example:**
```bash
python .agent/skills/ui-ux-pro-max-skill/.claude/skills/ui-ux-pro-max/scripts/search.py "beauty spa wellness service" --design-system -p "Serenity Spa"
```

### Step 3: Supplement with Detailed Searches (as needed)

After getting the design system, use domain searches to get additional details:

```bash
python .agent/skills/ui-ux-pro-max-skill/.claude/skills/ui-ux-pro-max/scripts/search.py "<keyword>" --domain <domain> [-n <max_results>]
```

**When to use detailed searches:**

| Need | Domain | Example |
|------|--------|---------|
| More style options | `style` | `--domain style "glassmorphism dark"` |
| Chart recommendations | `chart` | `--domain chart "real-time dashboard"` |
| UX best practices | `ux` | `--domain ux "animation accessibility"` |
| Alternative fonts | `typography` | `--domain typography "elegant luxury"` |
| Landing structure | `landing` | `--domain landing "hero social-proof"` |

### Step 4: Stack Guidelines (Default: html-tailwind)

Get implementation-specific best practices. If user doesn't specify a stack, **default to `html-tailwind`**.

```bash
python .agent/skills/ui-ux-pro-max-skill/.claude/skills/ui-ux-pro-max/scripts/search.py "<keyword>" --stack html-tailwind
```
