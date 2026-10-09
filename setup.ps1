# One-time setup: Python 3.12 environment (via uv), npm packages, built UI, Whisper model download.
param([switch]$SkipModels)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is not installed. Get it from https://docs.astral.sh/uv/ and run this again."
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "Node.js is not installed. Get it from https://nodejs.org/ and run this again."
}

uv venv --python 3.12 backend\.venv
uv pip install --python backend\.venv\Scripts\python.exe -r backend\requirements.txt

Push-Location frontend
npm install
npm run build
Pop-Location

if (-not $SkipModels) {
    Write-Host "Downloading the Whisper large-v3-turbo model (about 1.6 GB, once)..."
    $env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
    & backend\.venv\Scripts\python.exe -c "from faster_whisper.utils import download_model; print(download_model('large-v3-turbo'))"
}

foreach ($kind in "skills", "agents") {
    $target = Join-Path ".claude" $kind
    New-Item -ItemType Directory -Force $target | Out-Null
    Copy-Item "integrations\claude-code\$kind\*" $target -Recurse -Force
}

New-Item -ItemType Directory -Force ".agents\skills" | Out-Null
Copy-Item "integrations\codex\skills\*" ".agents\skills" -Recurse -Force

if (-not (Test-Path backend\.env)) { Copy-Item backend\.env.example backend\.env }
Write-Host "`nDone. Start the app with:  ./start.ps1"
