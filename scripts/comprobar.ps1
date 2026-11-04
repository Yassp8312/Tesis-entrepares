param([switch]$ConPostgreSQL)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repoPath '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Primero ejecuta scripts/preparar-entorno.ps1.' }
$checkArgs = @()
if ($ConPostgreSQL) { $checkArgs += '--postgresql' }
& $pythonPath (Join-Path $PSScriptRoot 'comprobar_proyecto.py') @checkArgs
if ($LASTEXITCODE -ne 0) { throw 'Hay comprobaciones fallidas; consulta el informe indicado.' }
