# Antigravity Agent Quick Setup Script
# Usage: .\setup-agent.ps1 <target-project-path>

param(
    [Parameter(Mandatory=$true)]
    [string]$TargetProject
)

$SourceAgent = "C:\Users\PC\Desktop\CODE\CODE\Code-pc\Autogen_ex_ver2\.agent"
$TargetAgent = Join-Path $TargetProject ".agent"

Write-Host "🚀 Antigravity Agent Setup" -ForegroundColor Cyan
Write-Host "Source: $SourceAgent" -ForegroundColor Gray
Write-Host "Target: $TargetAgent" -ForegroundColor Gray
Write-Host ""

# Check if target project exists
if (-not (Test-Path $TargetProject)) {
    Write-Host "❌ Target project does not exist: $TargetProject" -ForegroundColor Red
    exit 1
}

# Check if .agent already exists
if (Test-Path $TargetAgent) {
    Write-Host "⚠️  .agent folder already exists in target project" -ForegroundColor Yellow
    $overwrite = Read-Host "Overwrite? (y/N)"
    if ($overwrite -ne "y") {
        Write-Host "❌ Aborted" -ForegroundColor Red
        exit 1
    }
    Remove-Item -Recurse -Force $TargetAgent
}

# Copy .agent folder
Write-Host "📦 Copying workflows and skills..." -ForegroundColor Cyan
Copy-Item -Recurse $SourceAgent $TargetAgent

# Verify
$workflowCount = (Get-ChildItem "$TargetAgent\workflows" -Filter "*.md").Count
$skillCount = (Get-ChildItem "$TargetAgent\skills" -Directory).Count

Write-Host ""
Write-Host "✅ Setup complete!" -ForegroundColor Green
Write-Host "   Workflows: $workflowCount" -ForegroundColor Gray
Write-Host "   Skills: $skillCount" -ForegroundColor Gray
Write-Host ""
Write-Host "💡 Next steps:" -ForegroundColor Cyan
Write-Host "   1. Open Antigravity in the target project" -ForegroundColor Gray
Write-Host "   2. Workflows are available via /slash-commands" -ForegroundColor Gray
Write-Host "   3. Skills auto-apply based on file patterns" -ForegroundColor Gray
