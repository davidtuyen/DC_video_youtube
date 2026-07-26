# 🌍 GLOBAL ANTIGRAVITY SETUP

**Lưu 1 lần, dùng mọi project!**

## 🎯 Tại Sao Cần Global Setup?

### ❌ Cách Cũ (Bất Tiện):
```
Project A ← Copy .agent
Project B ← Copy .agent  
Project C ← Copy .agent
→ Mỗi project 1 bản copy riêng
→ Update phải copy lại tất cả
```

### ✅ Cách Mới (Global):
```
C:\Users\PC\.antigravity-global ← 1 bản duy nhất
         ↓
Project A ← Link
Project B ← Link  
Project C ← Link
→ Tất cả projects dùng chung
→ Update 1 lần, sync tất cả!
```

---

## 🚀 Setup (Chỉ Làm 1 Lần)

### Step 1: Tạo Global Directory

```powershell
cd C:\Users\PC\Desktop\CODE\CODE\Code-pc\Autogen_ex_ver2\.agent
.\setup-global-agent.ps1
```

**Kết quả:**
```
C:\Users\PC\.antigravity-global\
├── workflows/      ← 16 workflows (hardened)
├── skills/         ← 23+ skills
├── README.md
├── REUSE_GUIDE.md
└── link-global-agent.ps1
```

---

## 🔗 Link Global Config vào Project

### Method 1: Quick Link (KHÔNG CẦN ADMIN) ⭐ Recommended

```powershell
# Vào bất kỳ project nào
cd C:\path\to\any\project

# Run quick link
C:\Users\PC\.antigravity-global\quick-link.ps1

# Hoặc nếu đã add vào PATH:
quick-link
```

**Done!** Project này giờ đã có workflows và skills!

### Method 2: Manual Junction (Nâng Cao)

```powershell
cd <your-project>
cmd /c mklink /J .agent C:\Users\PC\.antigravity-global
```

---

## 📋 Workflow Cho Project Mới

```powershell
# 1. Tạo hoặc clone project mới
git clone https://github.com/user/new-project
cd new-project

# 2. Link global agent (1 dòng!)
C:\Users\PC\.antigravity-global\quick-link.ps1

# 3. Open Antigravity và code!
# Workflows và skills tự động available
```

**That's it!** 🎉

---

## 💡 Lợi Ích

### ✅ Tiện Lợi
- Setup 1 lần, dùng vĩnh viễn
- Project mới chỉ cần 1 command
- Không cần copy-paste

### ✅ Tự Động Sync
- Update workflow → Tất cả projects được update
- Add skill mới → Ngay lập tức available everywhere
- Fix bug → Apply cho tất cả

### ✅ Tiết Kiệm Không Gian
```
Cách cũ: 16 workflows × 10 projects = 160 files
Cách mới: 16 workflows × 1 = 16 files (linked)
```

### ✅ Version Control Đơn Giản
```
Git chỉ cần track 1 global directory
Mỗi project không cần commit .agent/
```

---

## 🔧 Quản Lý Global Config

### Update Workflows/Skills

```powershell
# Edit trong global directory
cd C:\Users\PC\.antigravity-global\workflows
code safe-code-edit.md

# Save → Tất cả projects tự động update!
```

### Add Workflow Mới

```powershell
cd C:\Users\PC\.antigravity-global\workflows
code my-new-workflow.md

# Ngay lập tức available: /my-new-workflow
```

### Backup Global Config

```powershell
$timestamp = Get-Date -Format "yyyy-MM-dd"
cp -r C:\Users\PC\.antigravity-global `
      C:\Users\PC\Backups\antigravity-$timestamp
```

### Git Version Control (Optional)

```powershell
cd C:\Users\PC\.antigravity-global
git init
git add .
git commit -m "Initial global Antigravity config"
git remote add origin https://github.com/user/antigravity-global
git push -u origin main
```

---

## 🎨 Customization cho Project Riêng

Nếu 1 project cần workflow riêng:

### Option A: Override (Project-Specific)
```powershell
# Unlink global
cd <project>
rm .agent

# Create project-local
mkdir .agent
cp -r C:\Users\PC\.antigravity-global\* .agent\

# Customize locally
code .agent/workflows/project-specific.md
```

### Option B: Extend (Hybrid)
```powershell
# Keep global link + add extras
cd <project>
mkdir .agent-local
code .agent-local/workflows/special-workflow.md

# Both .agent (global) and .agent-local (project) work!
```

---

## 🧪 Testing

```powershell
# Test in current project
cd C:\Users\PC\Desktop\CODE\CODE\Code-pc\Autogen_ex_ver2

# Verify link
(Get-Item .agent).Target
# Should show: C:\Users\PC\.antigravity-global

# Test workflow
# Open Antigravity → Type /safe-code-edit
# Should work!

# Test skill
# Edit any .js file
# claude-code-behavior skill should auto-apply
```

---

## 🆘 Troubleshooting

### "Global directory not found"
```powershell
# Re-run setup
cd C:\Users\PC\Desktop\CODE\CODE\Code-pc\Autogen_ex_ver2\.agent
.\setup-global-agent.ps1
```

### "Junction creation failed"
```powershell
# Make sure you're in project root
cd <project-root>

# Try manual junction
cmd /c mklink /J .agent C:\Users\PC\.antigravity-global
```

### "Workflows not showing in Antigravity"
```powershell
# Verify link
ls .agent/workflows/

# Restart Antigravity
# Workflows should reload
```

---

## 📊 Comparison

| Feature | Copy Method | Global Method |
|---------|-------------|---------------|
| Setup Time | 5 min per project | 5 min once + 5 sec per project |
| Disk Space | N × size | 1 × size |
| Updates | Manual per project | Automatic all projects |
| Consistency | Can diverge | Always in sync |
| Maintenance | High | Low |
| **Recommended** | ❌ No | ✅ Yes |

---

## 🎓 Advanced: Add to PATH

```powershell
# Add to PowerShell profile
code $PROFILE

# Add this line:
function quick-link { & C:\Users\PC\.antigravity-global\quick-link.ps1 }

# Now from ANY project:
cd <new-project>
quick-link  # Done!
```

---

**Created:** 2026-01-18  
**Version:** 2.0 (Global Setup)  
**Maintained by:** You  
**Location:** `C:\Users\PC\.antigravity-global\`
