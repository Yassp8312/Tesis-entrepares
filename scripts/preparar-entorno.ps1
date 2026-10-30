# Preparación local para Windows x64. No cambia PATH ni instala servicios.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoPath = Split-Path -Parent $PSScriptRoot
$pythonVersion = (Get-Content -LiteralPath (Join-Path $repoPath '.python-version') -Raw).Trim()
$nodeVersion = (Get-Content -LiteralPath (Join-Path $repoPath '.node-version') -Raw).Trim()
$manifest = Get-Content -LiteralPath (Join-Path $repoPath 'frontend/package.json') -Raw | ConvertFrom-Json
$npmVersion = $manifest.engines.npm
$uvVersion = '0.13.6'
$wheelName = "uv-$uvVersion-py3-none-win_amd64.whl"
$wheelSha256 = '7c9bc35ccb65932d8dc10a0669f9c805eaa3c9827ce18ecbecb1bd67944b2cdf'

if ([Environment]::Is64BitProcess -eq $false -or $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
    throw 'Este script requiere Windows x64. Consulta docs/entorno.md para otros entornos.'
}
$nodeCommand = (Get-Command node.exe -ErrorAction Stop).Source
$npmCommand = (Get-Command npm.cmd -ErrorAction Stop).Source
if ((& $nodeCommand --version).Trim() -ne "v$nodeVersion") {
    throw "Se requiere Node $nodeVersion. El script no sustituye tu instalación de Node."
}
if ((& $npmCommand --version).Trim() -ne $npmVersion) {
    throw "Se requiere npm $npmVersion. El script no modifica instalaciones globales."
}

$uvFolder = Join-Path $repoPath ".tools/uv/$uvVersion"
New-Item -ItemType Directory -Path $uvFolder -Force | Out-Null
$wheelPath = Join-Path $uvFolder $wheelName
$uvPath = Join-Path $uvFolder 'uv.exe'

function Test-WheelIntegrity {
    return (Test-Path -LiteralPath $wheelPath) -and (
        (Get-FileHash -LiteralPath $wheelPath -Algorithm SHA256).Hash.ToLowerInvariant() -eq $wheelSha256
    )
}

if (-not (Test-WheelIntegrity)) {
    $metadata = Invoke-RestMethod -Uri "https://pypi.org/pypi/uv/$uvVersion/json"
    $asset = @($metadata.urls | Where-Object { $_.filename -eq $wheelName })
    if ($asset.Count -ne 1 -or $asset[0].digests.sha256 -ne $wheelSha256) {
        throw 'El artefacto publicado de uv no coincide con la huella fijada.'
    }
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Invoke-WebRequest -Uri $asset[0].url -OutFile $wheelPath -TimeoutSec 120 -UseBasicParsing
            if (-not (Test-WheelIntegrity)) { throw 'La descarga no supera SHA256.' }
            break
        } catch {
            if ($attempt -eq 3) { throw }
            Write-Host "Repitiendo la descarga verificada de uv ($attempt de 3)."
        }
    }
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($wheelPath)
try {
    $entry = $archive.GetEntry("uv-$uvVersion.data/scripts/uv.exe")
    if ($null -eq $entry) { throw 'No se encontró uv.exe dentro del artefacto verificado.' }
    [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $uvPath, $true)
} finally {
    $archive.Dispose()
}

$env:UV_PYTHON_INSTALL_DIR = Join-Path $repoPath '.tools/python'
$env:UV_CACHE_DIR = Join-Path $repoPath '.tools/cache'
$env:UV_NO_PROGRESS = '1'

Push-Location $repoPath
try {
    & $uvPath python install $pythonVersion --no-bin --no-registry
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo preparar el Python fijado.' }
    & $uvPath sync --locked
    if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación Python desde uv.lock.' }
    & $uvPath pip check
    if ($LASTEXITCODE -ne 0) { throw 'El entorno Python presenta dependencias incompatibles.' }
    & $uvPath run --locked python scripts/verificar_dependencias.py
    if ($LASTEXITCODE -ne 0) { throw 'Falló la comprobación de dependencias Python.' }
    Push-Location (Join-Path $repoPath 'frontend')
    try {
        & $npmCommand ci --no-fund --no-audit
        if ($LASTEXITCODE -ne 0) { throw 'Falló npm ci.' }
        & $npmCommand run check:deps
        if ($LASTEXITCODE -ne 0) { throw 'Falló la comprobación del compilador de la interfaz.' }
    } finally {
        Pop-Location
    }
} finally {
    Pop-Location
}
Write-Host 'Entorno preparado y dependencias comprobadas.'
