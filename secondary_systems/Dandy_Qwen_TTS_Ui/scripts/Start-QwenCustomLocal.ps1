$ErrorActionPreference = "Stop"
$PackageRoot = Split-Path -Parent $PSScriptRoot
$ShowRoot = (Resolve-Path (Join-Path $PackageRoot "../..")).Path
$RuntimePath = Join-Path $ShowRoot "config/runtime.local.json"
$Runtime = if (Test-Path $RuntimePath) { Get-Content $RuntimePath -Raw | ConvertFrom-Json } else { $null }
$Python = if ($env:DANDY_QWEN_PYTHON) { $env:DANDY_QWEN_PYTHON } elseif ($Runtime.qwen_python) { $Runtime.qwen_python } else { Join-Path $ShowRoot ".venv-qwen/Scripts/python.exe" }
if (-not [IO.Path]::IsPathRooted($Python)) { $Python = Join-Path $ShowRoot $Python }
if (-not (Test-Path $Python)) { throw "Set DANDY_QWEN_PYTHON or create .venv-qwen." }
& $Python (Join-Path $PSScriptRoot "english_demo.py")
if ($LASTEXITCODE -ne 0) { throw "Could not prepare the English Qwen UI." }
. (Join-Path $ShowRoot "scripts/studio/processes.ps1")
Assert-DandyListener -Port 8031 -ExpectedCommand 'qwen_tts.cli.demo.*Qwen3-TTS-12Hz-1.7B-CustomVoice'
Assert-DandyListener -Port 8020 -ExpectedCommand 'uvicorn.*bridge:app'
$SharedLauncher = if ($env:DANDY_QWEN_SHARED_LAUNCHER) { $env:DANDY_QWEN_SHARED_LAUNCHER } elseif ($Runtime.qwen_shared_launcher) { $Runtime.qwen_shared_launcher } else { "C:\AI-Services\Start-Shared-QwenTTS.ps1" }
$LogDir = Join-Path $PackageRoot "logs"
New-Item -ItemType Directory -Force $LogDir | Out-Null
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:GRADIO_ANALYTICS_ENABLED = "False"
$env:PYTHONIOENCODING = "utf-8"
if ($Runtime.ffmpeg_bin) { $env:PATH = "$($Runtime.ffmpeg_bin);$env:PATH" }
if (-not (Get-NetTCPConnection -LocalPort 8031 -State Listen -ErrorAction SilentlyContinue)) {
    & $SharedLauncher -Once
}
if (-not (Get-NetTCPConnection -LocalPort 8020 -State Listen -ErrorAction SilentlyContinue)) {
    $env:DANDY_SHOW_ROOT = $ShowRoot
    $env:DANDY_QWEN_BACKENDS = "http://127.0.0.1:8031"
    $env:DANDY_FFMPEG = (Get-Command ffmpeg -ErrorAction Stop).Source
    $env:DANDY_FFPROBE = (Get-Command ffprobe -ErrorAction Stop).Source
    $BridgeProcess = Start-Process -FilePath $Python -ArgumentList @("-m", "uvicorn", "bridge:app", "--host", "127.0.0.1", "--port", "8020") -WorkingDirectory $PackageRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $LogDir "qwen-bridge-local.out.log") -RedirectStandardError (Join-Path $LogDir "qwen-bridge-local.err.log")
    Write-Output "Started Dandy TTS bridge PID=$($BridgeProcess.Id) on port 8020"
}
