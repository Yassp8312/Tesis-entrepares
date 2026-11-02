param([Parameter(ValueFromRemainingArguments = $true)][string[]]$DjangoArgs)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
$uvPath = Join-Path $repoPath '.tools/uv/0.13.6/uv.exe'
$envPath = Join-Path $repoPath '.env'
if (-not (Test-Path -LiteralPath $uvPath)) { throw 'Primero prepara el entorno.' }
if (-not (Test-Path -LiteralPath $envPath)) { throw 'Primero prepara la configuración local.' }
$env:UV_PYTHON_INSTALL_DIR = Join-Path $repoPath '.tools/python'
$env:UV_CACHE_DIR = Join-Path $repoPath '.tools/cache'
Push-Location $repoPath
try {
    & $uvPath run --locked --env-file .env python backend/manage.py @DjangoArgs
    if ($LASTEXITCODE -ne 0) { throw 'El comando Django terminó con un error.' }
} finally {
    Pop-Location
}
