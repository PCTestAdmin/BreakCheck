$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    python -u packaging/smoke-windows.py
    if ($LASTEXITCODE -ne 0) { throw "Windows smoke tests failed (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}
