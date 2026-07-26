---
description: Perform security review on code changes
---

# Security Review Workflow

Comprehensive security review workflow adapted from Claude Code's `/security-review` slash command.

## 1. Check Git Status
```
git status
```

## 2. Review Modified Files
```
git diff --name-only origin/HEAD... || git diff --name-only HEAD
```

## 3. Review Commits
```
git log --no-decorate origin/HEAD... -10 || git log -10
```

## 4. Analyze Diff for Security Issues
```
Review the complete diff with security focus.
Categories to examine:

**Input Validation:**
- SQL injection
- Command injection  
- Path traversal
- XXE injection
- NoSQL injection

**Authentication & Authorization:**
- Authentication bypass
- Privilege escalation
- Session management flaws
- JWT vulnerabilities

**Crypto & Secrets:**
- Hardcoded credentials
- Weak algorithms
- Improper key storage

**Injection & Code Execution:**
- Remote code execution
- XSS vulnerabilities
- Deserialization issues
- Eval/template injection

**Data Exposure:**
- Sensitive data logging
- PII handling violations
- API data leakage
```

## 5. Filter High-Confidence Findings Only
```
Severity Guidelines:
- HIGH: RCE, data breach, auth bypass
- MEDIUM: Requires conditions but significant impact
- LOW: Defense-in-depth issues

Confidence Threshold: Report only if >80% confident
```

## 6. Generate Report
```
Output format:

# Vuln 1: [Category]: `file:line`

* Severity: [High/Medium]
* Description: [Clear description]
* Exploit Scenario: [Concrete attack path]
* Recommendation: [Specific fix]
```

## Hard Exclusions (DO NOT Report)
- Denial of Service vulnerabilities
- Secrets stored on disk if otherwise secured
- Rate limiting concerns
- Memory/CPU exhaustion
- Theoretical race conditions
- Test files only
- Documentation files
- Log spoofing
- Regex DOS
- React/Angular XSS (unless using dangerouslySetInnerHTML)
- Client-side permission checks

## Focus Areas
✅ Report: Concrete, exploitable vulnerabilities
✅ Report: Clear attack paths with specific code locations
❌ Skip: Theoretical issues, style concerns, low-impact findings
