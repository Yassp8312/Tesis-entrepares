Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoPath '.env'
if (Test-Path -LiteralPath $envPath) {
    Write-Host 'La configuración local ya existe y se conserva.'
    return
}
$pythonPath = Join-Path $repoPath '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Primero ejecuta scripts/preparar-entorno.ps1.'
}
$secret = & $pythonPath -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($secret)) {
    throw 'No se pudo generar una clave local.'
}
$content = @(
    'DJANGO_SETTINGS_MODULE=config.settings.development',
    "DJANGO_SECRET_KEY='$($secret.Trim())'",
    'DJANGO_DEBUG=true',
    'DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,[::1]',
    'POSTGRES_HOST=127.0.0.1',
    'POSTGRES_PORT=5432',
    'POSTGRES_DB=entrepares_development',
    'POSTGRES_USER=entrepares',
    'POSTGRES_PASSWORD='
)
$stream = [System.IO.File]::Open($envPath, [System.IO.FileMode]::CreateNew)
try {
    $writer = [System.IO.StreamWriter]::new($stream, [System.Text.UTF8Encoding]::new($false))
    try { $writer.Write(($content -join "`n") + "`n") } finally { $writer.Dispose() }
} finally {
    $stream.Dispose()
}
Write-Host 'Configuración local creada; no contiene credenciales de una base operativa.'
