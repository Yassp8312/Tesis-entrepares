Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repoPath '.venv/Scripts/python.exe'
Push-Location (Join-Path $repoPath 'frontend')
try {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo compilar la interfaz.' }
} finally { Pop-Location }
& $pythonPath (Join-Path $PSScriptRoot 'preparar_web.py')
if ($LASTEXITCODE -ne 0) { throw 'No se pudo preparar el documento y los recursos.' }
& (Join-Path $PSScriptRoot 'django.ps1') collectstatic --noinput
