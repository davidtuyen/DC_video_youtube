# Quick Global Link (No Admin Required)
# Uses Junction instead of SymbolicLink
# Usage: Run from any project directory

$ProjectRoot = Get-Location
$GlobalAgent = "C:\Users\PC\.antigravity-global"
$ProjectAgent = Join-Path $ProjectRoot ".agent"

Write-Host "[QUICK-LINK] Linking Global Agent to Project" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot" -ForegroundColor Gray
Write-Host ""

# Verify global exists
if (-not (Test-Path $GlobalAgent)) {
    Write-Host "[ERROR] Global agent not set up yet!" -ForegroundColor Red
    Write-Host ""
    Write-Host "[INFO] Run setup first:" -ForegroundColor Yellow
    Write-Host "   C:\Users\PC\Desktop\CODE\CODE\Code-pc\Autogen_ex_ver2\.agent\setup-global-agent.ps1"
    exit 1
}

# Check if .agent already exists
if (Test-Path $ProjectAgent) {
    $item = Get-Item $ProjectAgent
    if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        Write-Host "[OK] Already linked to global agent!" -ForegroundColor Green
        exit 0
    }
    
    Write-Host "[WARNING] .agent folder exists (not linked)" -ForegroundColor Yellow
    $overwrite = Read-Host "Replace with global link? (y/N)"
    if ($overwrite -ne "y") {
        Write-Host "[ABORT] Cancelled by user" -ForegroundColor Red
        exit 1
    }
    
    Remove-Item -Recurse -Force $ProjectAgent
}

# Create junction (no admin required!)
cmd /c mklink /J "$ProjectAgent" "$GlobalAgent" | Out-Null

if ($LASTEXITCODE -eq 0) {
    Write-Host "[SUCCESS] Junction created successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "[INFO] Linked to global agent with:" -ForegroundColor Cyan
    $workflowCount = (Get-ChildItem "$GlobalAgent\workflows" -Filter "*.md").Count
    $skillCount = (Get-ChildItem "$GlobalAgent\skills" -Directory).Count
    Write-Host "   - $workflowCount workflows" -ForegroundColor Gray
    Write-Host "   - $skillCount skills" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[BENEFITS]" -ForegroundColor Yellow
    Write-Host "   - No need to copy .agent to new projects" -ForegroundColor Gray
    Write-Host "   - Updates to global config auto-sync" -ForegroundColor Gray
    Write-Host "   - Same workflows/skills across all projects" -ForegroundColor Gray
} else {
    Write-Host "[ERROR] Failed to create junction" -ForegroundColor Red
    Write-Host "   Try running from project root directory" -ForegroundColor Gray
}
