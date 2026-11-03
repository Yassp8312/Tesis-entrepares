param(
    [ValidateSet('unitarias', 'integracion', 'todas')][string]$Modo = 'todas',
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$PytestArgs
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
    if ($Modo -ne 'unitarias') {
        & $pythonPath scripts/postgresql_local.py iniciar
        if ($LASTEXITCODE -ne 0) { throw 'No se puede utilizar el cluster privado de pruebas.' }
    }
    $selection = switch ($Modo) {
        'unitarias' { 'not postgresql' }
        'integracion' { 'postgresql' }
        'todas' { 'postgresql or not postgresql' }
    }
    # --ds tiene prioridad sobre DJANGO_SETTINGS_MODULE procedente del .env de desarrollo.
    & $uvPath run --locked --env-file .env python -m pytest @PytestArgs --ds=config.settings.test -m $selection
    if ($LASTEXITCODE -ne 0) { throw 'Hay pruebas fallidas.' }
} finally {
    Pop-Location
}
