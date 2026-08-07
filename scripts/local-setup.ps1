param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop with Docker Compose is required for the isolated local PostGIS workflow."
}

if (-not (Test-Path ".env.local")) {
    Copy-Item ".env.example" ".env.local"
    Write-Host "Created .env.local from safe local defaults."
}

$pythonExe = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
if (-not $SkipInstall) {
    & $pythonExe -m pip install -r requirements.lock
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
}

docker compose up -d postgis
if ($LASTEXITCODE -ne 0) { throw "PostGIS startup failed." }

$healthy = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    docker compose exec -T postgis pg_isready -U openskagit_local -d openskagit_dev | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $healthy = $true
        break
    }
    Start-Sleep -Seconds 1
}
if (-not $healthy) { throw "PostGIS did not become ready within 30 seconds." }

$testDatabase = docker compose exec -T postgis psql -U openskagit_local -d openskagit_dev -tAc "SELECT 1 FROM pg_database WHERE datname = 'openskagit_test'"
if ($LASTEXITCODE -ne 0) { throw "Could not verify the local test database." }
if (($testDatabase | Out-String).Trim() -ne "1") {
    docker compose exec -T postgis createdb -U openskagit_local -O openskagit_local openskagit_test
    if ($LASTEXITCODE -ne 0) { throw "Could not create the local test database." }
}

$env:OPENSKAGIT_ENVIRONMENT = "development"
& $pythonExe manage.py bootstrap_mcp_source_schema --with-sample
if ($LASTEXITCODE -ne 0) { throw "Local source-schema bootstrap failed." }
& $pythonExe manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { throw "Local migrations failed." }
& $pythonExe manage.py check
if ($LASTEXITCODE -ne 0) { throw "Django checks failed." }

Write-Host "Local PostGIS and Django schema are ready. Run scripts\local-run.ps1."
