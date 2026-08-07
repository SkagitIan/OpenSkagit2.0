$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
$pythonExe = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
$env:OPENSKAGIT_ENVIRONMENT = "development"
& $pythonExe -m uvicorn config.asgi:application --host 127.0.0.1 --port 8000
