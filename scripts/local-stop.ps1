$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
docker compose down
if ($LASTEXITCODE -ne 0) { throw "Compose teardown failed." }
Write-Host "Local containers stopped. The named PostGIS volume was preserved."
