$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EnvPath = Join-Path $ProjectRoot ".conda"
$Python = Join-Path $EnvPath "python.exe"

Set-Location $ProjectRoot

if (-not (Test-Path $EnvPath)) {
    Write-Host "Local Conda environment not found at $EnvPath"
    Write-Host "Create it first with: conda env create -p .\.conda -f environment.yml"
    exit 1
}

& $Python -m pocket_codex
