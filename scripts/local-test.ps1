$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
$pythonExe = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }

$env:OPENSKAGIT_ENVIRONMENT = "test"
& $pythonExe manage.py bootstrap_mcp_source_schema --with-sample
if ($LASTEXITCODE -ne 0) { throw "Test source-schema bootstrap failed." }
& $pythonExe manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { throw "Test migrations failed." }
& $pythonExe manage.py check
if ($LASTEXITCODE -ne 0) { throw "Django checks failed." }
& $pythonExe manage.py smoke_mcp_protocol
if ($LASTEXITCODE -ne 0) { throw "Authenticated MCP protocol smoke failed." }
& $pythonExe manage.py test --keepdb
if ($LASTEXITCODE -ne 0) { throw "Django test suite failed." }
