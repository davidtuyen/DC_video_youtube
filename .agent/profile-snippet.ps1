# ============================================
# ANTIGRAVITY GLOBAL AGENT FUNCTIONS
# Add these to your PowerShell profile
# ============================================

# Function 1: Link current directory to global agent
function Link-Agent {
    & "C:\Users\PC\.antigravity-global\quick-link.ps1"
}

# Function 2: Link any project by path
function Link-Project {
    param([string]$Path)
    & "C:\Users\PC\.antigravity-global\link-agent.ps1" $Path
}

# Aliases for shorter typing
Set-Alias -Name lag -Value Link-Agent
if (-not (Test-Path "Alias:lp")) { Set-Alias -Name lp -Value Link-Project }

# ============================================
# USAGE EXAMPLES:
# ============================================
# 
# From inside a project:
#   > lag
#   → Links current directory to global agent
#
# From anywhere:
#   > lp C:\path\to\project
#   → Links specified project to global agent
#
# Or even shorter:
#   > cd C:\new-project
#   > lag
#   → Done!
# ============================================

Write-Host "[INFO] Antigravity Global Agent functions loaded" -ForegroundColor Green
Write-Host "  Use 'lag' to link current directory" -ForegroundColor Gray
Write-Host "  Use 'lp [path]' to link any project" -ForegroundColor Gray
