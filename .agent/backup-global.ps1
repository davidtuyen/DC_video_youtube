# Backup Global Agent Config
# Usage: .\backup-global.ps1

$GlobalAgent = "C:\Users\PC\.antigravity-global"
$BackupDir = "C:\Users\PC\Backups\antigravity-backups"
$Timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$BackupPath = Join-Path $BackupDir "antigravity-$Timestamp"

Write-Host "[BACKUP] Creating backup of global agent config..." -ForegroundColor Cyan
Write-Host ""

# Create backup directory
if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}

# Copy global to backup
Copy-Item -Recurse $GlobalAgent $BackupPath

Write-Host "[SUCCESS] Backup created!" -ForegroundColor Green
Write-Host ""
Write-Host "[LOCATION] $BackupPath" -ForegroundColor Gray
Write-Host ""
Write-Host "[FILES]" -ForegroundColor Yellow
$workflowCount = (Get-ChildItem "$BackupPath\workflows" -Filter "*.md").Count
$skillCount = (Get-ChildItem "$BackupPath\skills" -Directory).Count
Write-Host "   Workflows: $workflowCount" -ForegroundColor Gray
Write-Host "   Skills: $skillCount" -ForegroundColor Gray
Write-Host ""
Write-Host "[TIP] To restore:" -ForegroundColor Cyan
Write-Host "   Copy-Item -Recurse `"$BackupPath\*`" `"$GlobalAgent\`" -Force" -ForegroundColor Gray
