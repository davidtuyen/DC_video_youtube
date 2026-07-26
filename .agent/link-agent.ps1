# Link Agent - Single Command Setup
# Usage: .\link-agent.ps1 C:\path\to\project

param(
    [Parameter(Mandatory=$false)]
    [string]$ProjectPath = (Get-Location)
)

$GlobalAgent = "C:\Users\PC\.antigravity-global"

# Change to project directory if path provided
if ($ProjectPath -ne (Get-Location)) {
    if (-not (Test-Path $ProjectPath)) {
        Write-Host "[ERROR] Project path does not exist: $ProjectPath" -ForegroundColor Red
        exit 1
    }
    Set-Location $ProjectPath
}

Write-Host "[LINK-AGENT] Setting up global agent for:" -ForegroundColor Cyan
Write-Host "   $ProjectPath" -ForegroundColor Gray
Write-Host ""

# Run quick-link
& "$GlobalAgent\quick-link.ps1"
