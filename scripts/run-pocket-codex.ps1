$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EnvPath = Join-Path $ProjectRoot ".conda"
$Python = Join-Path $EnvPath "python.exe"
$LogDir = Join-Path $ProjectRoot "data\logs"
$LogFile = Join-Path $LogDir "pocket-codex.log"

Set-Location $ProjectRoot

if (-not (Test-Path $EnvPath)) {
    Write-Host "Local Conda environment not found at $EnvPath"
    Write-Host "Create it first with: conda env create -p .\.conda -f environment.yml"
    exit 1
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$env:PYTHONUNBUFFERED = "1"

$ErrorActionPreference = "Continue"
& $Python -m pocket_codex >> $LogFile 2>&1
exit $LASTEXITCODE
