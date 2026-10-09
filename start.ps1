# Start the app. Default: one server on http://127.0.0.1:8000 that also serves the built UI.
# -Dev: hot-reloading backend plus the Vite dev server on http://localhost:5173.
param([switch]$Dev)
$root = $PSScriptRoot
$py = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Run ./setup.ps1 first." }

$env:PYTHONUTF8 = "1"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"

if ($Dev) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\frontend'; npm run dev"
    Set-Location "$root\backend"
    & $py -m uvicorn app.main:app --reload --port 8000
} else {
    if (-not (Test-Path "$root\frontend\dist\index.html")) {
        Push-Location "$root\frontend"; npm run build; Pop-Location
    }
    Set-Location "$root\backend"
    Start-Process "http://127.0.0.1:8000"
    & $py -m uvicorn app.main:app --port 8000
}
