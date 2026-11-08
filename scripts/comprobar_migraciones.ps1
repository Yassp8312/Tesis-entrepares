param(
    [string]$Salida = '.cache/migraciones/informe.json'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
$uvPath = Join-Path $repoPath '.tools/uv/0.13.6/uv.exe'
$pythonPath = Join-Path $repoPath '.venv/Scripts/python.exe'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $repoPath '.tools/python'
$env:UV_CACHE_DIR = Join-Path $repoPath '.tools/cache'
Push-Location $repoPath
try {
    & $pythonPath scripts/postgresql_local.py iniciar
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo iniciar el cluster privado.' }
    & $uvPath run --locked --env-file .env python scripts/comprobar_migraciones.py --output $Salida
    if ($LASTEXITCODE -ne 0) { throw 'La reproducción de migraciones falló.' }
} finally {
    Pop-Location
}
