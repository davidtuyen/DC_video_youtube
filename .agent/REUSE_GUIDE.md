# Quick Reference: Reusing Antigravity Config

## 📍 Current Location
All workflows and skills are stored in:
```
C:\Users\PC\Desktop\CODE\CODE\Code-pc\Autogen_ex_ver2\.agent\
```

## 🔄 Copy to New Project

### Method 1: PowerShell Script (Easiest)
```powershell
cd C:\Users\PC\Desktop\CODE\CODE\Code-pc\Autogen_ex_ver2\.agent
.\setup-agent.ps1 C:\path\to\new\project
```

### Method 2: Manual Copy
```powershell
# Copy entire .agent folder
cp -r C:\Users\PC\Desktop\CODE\CODE\Code-pc\Autogen_ex_ver2\.agent `
      C:\path\to\new\project\.agent
```

### Method 3: Selective Copy
```powershell
# Only copy workflows
cp -r C:\Users\PC\Desktop\CODE\CODE\Code-pc\Autogen_ex_ver2\.agent\workflows `
      C:\path\to\new\project\.agent\workflows

# Only copy specific skills
cp -r C:\Users\PC\Desktop\CODE\CODE\Code-pc\Autogen_ex_ver2\.agent\skills\claude-code-behavior `
      C:\path\to\new\project\.agent\skills\claude-code-behavior
```

## 📦 What Gets Copied

### Workflows (16 files) - Hardened for Antigravity
- ✅ Aggressive `// turbo` removed from risky operations
- ✅ Safe turbos kept for read-only operations
- ✅ Platform bug resistance improved

### Skills (23+ skills)
- `claude-code-behavior/` - Claude Code emulation (priority: critical)
- `python-modern-typing/` - Modern Python standards
- `ui-ux-pro-max-skill/` - Advanced UI/UX design
- Plus 20 more specialized skills

### NOT Copied (Global Settings)
❌ User Rules (memory[user_global]) - These are in Antigravity Settings
❌ Conversation history
❌ Knowledge items

## 🌍 Global vs Local

| Setting | Scope | Location | Auto-Apply? |
|---------|-------|----------|-------------|
| **User Rules** | All projects | Antigravity Settings | ✅ Yes |
| **Workflows** | Per project | `.agent/workflows/` | ❌ No |
| **Skills** | Per project | `.agent/skills/` | ❌ No |

## 💾 Backup Current Config

```powershell
# Create timestamped backup
$timestamp = Get-Date -Format "yyyy-MM-dd_HHmm"
cp -r C:\Users\PC\Desktop\CODE\CODE\Code-pc\Autogen_ex_ver2\.agent `
      C:\Users\PC\Backups\antigravity-agent-$timestamp
```

## 📝 Version Control

Consider adding to Git:
```powershell
cd C:\Users\PC\Desktop\CODE\CODE\Code-pc\Autogen_ex_ver2
git add .agent/
git commit -m "feat: Add Antigravity workflows and skills (v2.0 hardened)"
```

## 🔧 Customization

After copying to new project, you can:
1. Add project-specific workflows in `.agent/workflows/`
2. Add project-specific skills in `.agent/skills/`
3. Modify existing workflows to fit project needs
4. Keep global User Rules in Antigravity Settings

---

**Last Updated:** 2026-01-18  
**Version:** 2.0 (Platform Hardened)
