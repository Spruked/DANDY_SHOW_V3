$ErrorActionPreference = "Stop"

$PackageRoot = Split-Path -Parent $PSScriptRoot
$ShowRoot = (Resolve-Path (Join-Path $PackageRoot "..\..")).Path
$LogDir = Join-Path $PackageRoot "logs"
New-Item -ItemType Directory -Force $LogDir | Out-Null

$Port = 8020
Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

$env:DANDY_SHOW_ROOT = $ShowRoot
$env:DANDY_QWEN_BRIDGE_HOST = "0.0.0.0"
$env:DANDY_QWEN_BRIDGE_PORT = "$Port"
$env:DANDY_QWEN_BACKENDS = "http://127.0.0.1:8031,http://127.0.0.1:8032,http://127.0.0.1:8033"
$env:DANDY_FFMPEG = Join-Path $ShowRoot "staging\ffmpeg\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"
$env:DANDY_FFPROBE = Join-Path $ShowRoot "staging\ffmpeg\ffmpeg-master-latest-win64-gpl\bin\ffprobe.exe"

$Python = if ($env:DANDY_QWEN_PYTHON) {
    $env:DANDY_QWEN_PYTHON
} elseif (Test-Path "R:\Services\qwen_tts_312\Scripts\python.exe") {
    "R:\Services\qwen_tts_312\Scripts\python.exe"
} else {
    "R:\R_Drive_Substrate\Services\qwen_tts_312\Scripts\python.exe"
}
if (-not (Test-Path $Python)) {
    throw "Qwen Python runtime not found: $Python. Set DANDY_QWEN_PYTHON to the Windows CUDA Python 3.12 runtime."
}
$OutLog = Join-Path $LogDir "qwen-bridge-$Port.out.log"
$ErrLog = Join-Path $LogDir "qwen-bridge-$Port.err.log"

$Process = Start-Process `
    -FilePath $Python `
    -ArgumentList @("-m", "uvicorn", "bridge:app", "--host", $env:DANDY_QWEN_BRIDGE_HOST, "--port", "$Port") `
    -WorkingDirectory $PackageRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -PassThru

Write-Output "Started Qwen TTS bridge pid=$($Process.Id)"
Write-Output "Ready target: http://127.0.0.1:$Port"
