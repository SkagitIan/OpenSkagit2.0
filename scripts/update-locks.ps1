param(
    [switch]$Upgrade
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
$pythonExe = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }

& $pythonExe -m pip install "pip-tools==7.6.0"
if ($LASTEXITCODE -ne 0) { throw "pip-tools installation failed." }

$upgradeFlag = if ($Upgrade) { @("--upgrade") } else { @() }
& $pythonExe -m piptools compile @upgradeFlag --cache-dir .cache\pip-tools --strip-extras --output-file requirements.lock requirements.in
if ($LASTEXITCODE -ne 0) { throw "Runtime lock generation failed." }
$runtimeLock = [IO.File]::ReadAllText("requirements.lock")
$runtimeLock = [regex]::Replace(
    $runtimeLock,
    '(?m)^pywin32==([^\r\n;]+)',
    'pywin32==$1 ; sys_platform == "win32"'
)
[IO.File]::WriteAllText(
    (Resolve-Path "requirements.lock"),
    $runtimeLock,
    [Text.UTF8Encoding]::new($false)
)
& $pythonExe -m piptools compile @upgradeFlag --cache-dir .cache\pip-tools --strip-extras --output-file requirements-dev.lock requirements-dev.in
if ($LASTEXITCODE -ne 0) { throw "Development lock generation failed." }

Write-Host "Locks regenerated. Review both diffs and run scripts\local-test.ps1 before commit."
