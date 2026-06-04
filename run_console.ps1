$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot "venv_flightgear\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    Write-Error "Virtual environment Python was not found: $Python"
}

$env:PYTHONPATH = Join-Path $ProjectRoot "src"
& $Python -m flightgear_framework.console_app @args
