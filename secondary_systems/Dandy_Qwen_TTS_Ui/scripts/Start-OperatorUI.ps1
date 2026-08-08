$ErrorActionPreference = "Stop"

$PackageRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $PackageRoot "logs"
New-Item -ItemType Directory -Force $LogDir | Out-Null

$Port = 7861
Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

$env:DANDY_QWEN_UI_HOST = "127.0.0.1"
$env:DANDY_QWEN_UI_PORT = "$Port"
$env:DANDY_QWEN_BACKENDS = "http://127.0.0.1:8031,http://127.0.0.1:8032,http://127.0.0.1:8033"

$Python = if ($env:DANDY_QWEN_PYTHON) {
    $env:DANDY_QWEN_PYTHON
} elseif (Test-Path "R:\Services\qwen_tts_312\Scripts\python.exe") {
    "R:\Services\qwen_tts_312\Scripts\python.exe"
} else {
    "R:\R_Drive_Substrate\Services\qwen_tts_312\Scripts\python.exe"
}
if (-not (Test-Path $Python)) {
    throw "Python runtime not found: $Python. Set DANDY_QWEN_PYTHON to the Python that has gradio and gradio_client installed."
}

$OutLog = Join-Path $LogDir "operator-ui-$Port.out.log"
$ErrLog = Join-Path $LogDir "operator-ui-$Port.err.log"

$Process = Start-Process `
    -FilePath $Python `
    -ArgumentList @("app.py") `
    -WorkingDirectory $PackageRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -PassThru

Write-Output "Started operator UI pid=$($Process.Id)"
Write-Output "Ready target: http://127.0.0.1:$Port"
