# Setup PowerShell Profile for Antigravity
# Run this ONCE to add global agent functions

$ProfilePath = $PROFILE
$SnippetPath = "C:\Users\PC\.antigravity-global\profile-snippet.ps1"

Write-Host "[SETUP] Adding Antigravity functions to PowerShell profile" -ForegroundColor Cyan
Write-Host ""

# Check if profile exists
if (-not (Test-Path $ProfilePath)) {
    Write-Host "[INFO] Creating new PowerShell profile..." -ForegroundColor Yellow
    New-Item -Path $ProfilePath -ItemType File -Force | Out-Null
}

# Check if already added
$profileContent = Get-Content $ProfilePath -Raw -ErrorAction SilentlyContinue
if ($profileContent -like "*ANTIGRAVITY GLOBAL AGENT FUNCTIONS*") {
    Write-Host "[SKIP] Antigravity functions already in profile" -ForegroundColor Gray
    exit 0
}

# Add snippet
Write-Host "[INFO] Adding functions to profile..." -ForegroundColor Yellow
Add-Content -Path $ProfilePath -Value "`n# Load Antigravity Global Agent functions`n"
Add-Content -Path $ProfilePath -Value ". `"$SnippetPath`"`n"

Write-Host "[SUCCESS] Profile updated!" -ForegroundColor Green
Write-Host ""
Write-Host "[IMPORTANT] Restart PowerShell to activate" -ForegroundColor Yellow
Write-Host "Or run: . `$PROFILE" -ForegroundColor Gray
Write-Host ""
Write-Host "[USAGE] After restart:" -ForegroundColor Cyan
Write-Host "  cd C:\new-project" -ForegroundColor Gray
Write-Host "  lag" -ForegroundColor Green
Write-Host "  → Done!" -ForegroundColor Gray
