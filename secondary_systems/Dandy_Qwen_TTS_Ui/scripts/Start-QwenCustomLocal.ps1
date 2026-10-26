$ErrorActionPreference = "Stop"
$PackageRoot = Split-Path -Parent $PSScriptRoot
$ShowRoot = (Resolve-Path (Join-Path $PackageRoot "../..")).Path
$Python = "C:\Users\bryan\AppData\Local\Programs\Python\Python311\python.exe"
$Model = & $Python -c "from huggingface_hub import snapshot_download; print(snapshot_download('Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice', local_files_only=True))"
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Model)) { throw "Qwen3 TTS 1.7B CustomVoice is not cached." }
$LogDir = Join-Path $PackageRoot "logs"
New-Item -ItemType Directory -Force $LogDir | Out-Null
$Runtime = Get-Content (Join-Path $ShowRoot "config/runtime.local.json") -Raw | ConvertFrom-Json
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:GRADIO_ANALYTICS_ENABLED = "False"
$env:PYTHONIOENCODING = "utf-8"
$env:PATH = "$($Runtime.ffmpeg_bin);$env:PATH"
if (-not (Get-NetTCPConnection -LocalPort 8031 -State Listen -ErrorAction SilentlyContinue)) {
    $ModelArgs = @("-m", "qwen_tts.cli.demo", $Model, "--ip", "127.0.0.1", "--port", "8031", "--device", "cuda:0", "--dtype", "bfloat16", "--no-flash-attn", "--no-share", "--concurrency", "1")
    $ModelProcess = Start-Process -FilePath $Python -ArgumentList $ModelArgs -WorkingDirectory $PackageRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $LogDir "qwen-custom-local.out.log") -RedirectStandardError (Join-Path $LogDir "qwen-custom-local.err.log")
    Write-Output "Started Qwen3 TTS 1.7B CustomVoice PID=$($ModelProcess.Id) on port 8031"
}
if (-not (Get-NetTCPConnection -LocalPort 8020 -State Listen -ErrorAction SilentlyContinue)) {
    $env:DANDY_SHOW_ROOT = $ShowRoot
    $env:DANDY_QWEN_BACKENDS = "http://127.0.0.1:8031"
    $env:DANDY_FFMPEG = Join-Path $Runtime.ffmpeg_bin "ffmpeg.exe"
    $env:DANDY_FFPROBE = Join-Path $Runtime.ffmpeg_bin "ffprobe.exe"
    $BridgeProcess = Start-Process -FilePath $Python -ArgumentList @("-m", "uvicorn", "bridge:app", "--host", "127.0.0.1", "--port", "8020") -WorkingDirectory $PackageRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $LogDir "qwen-bridge-local.out.log") -RedirectStandardError (Join-Path $LogDir "qwen-bridge-local.err.log")
    Write-Output "Started Dandy TTS bridge PID=$($BridgeProcess.Id) on port 8020"
}
