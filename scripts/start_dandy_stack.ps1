param(
    [switch]$Restart,
    [switch]$NoBackend,
    [switch]$NoFrontend,
    [switch]$NoQwen,
    [switch]$Reload,
    [ValidateSet("custom", "clone", "design")]
    [string]$QwenMode = "custom",
    [int]$BackendPort = 8110,
    [int]$FrontendPort = 5173,
    [string]$LlamaCppBaseUrl = "http://127.0.0.1:40343/v1",
    [string]$LlamaCppModel = ""
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"
$qwenRoot = Join-Path $root "secondary_systems\Dandy_Qwen_TTS_Ui"
$qwenModeScript = Join-Path $qwenRoot "scripts\Start-QwenTTSMode.ps1"
$qwenBridgeScript = Join-Path $qwenRoot "scripts\Start-QwenTTSBridge.ps1"
$qwenUiScript = Join-Path $qwenRoot "scripts\Start-OperatorUI.ps1"
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$ffmpegBin = Join-Path $root "staging\ffmpeg\ffmpeg-master-latest-win64-gpl\bin"
if (-not (Test-Path (Join-Path $ffmpegBin "ffmpeg.exe"))) {
    $sharedFfmpegBin = Join-Path (Split-Path -Parent $root) "Dandy\staging\ffmpeg\ffmpeg-master-latest-win64-gpl\bin"
    if (Test-Path (Join-Path $sharedFfmpegBin "ffmpeg.exe")) {
        $ffmpegBin = $sharedFfmpegBin
    }
}
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$pythonCmd = if ($env:DANDY_PYTHON) {
    $env:DANDY_PYTHON
} elseif (Test-Path $venvPython) {
    $venvPython
} else {
    "py"
}
$backendBaseArgs = @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$BackendPort")
if ($Reload) {
    $backendBaseArgs += "--reload"
}
$pythonArgs = if ($env:DANDY_PYTHON) {
    $backendBaseArgs
} elseif (Test-Path $venvPython) {
    $backendBaseArgs
} else {
    @("-3.12") + $backendBaseArgs
}

$QwenPorts = @{
    custom = 8031
    clone = 8032
    design = 8033
}

function Stop-ByPort {
    param([int]$Port)
    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $listeners) {
        return
    }
    $pids = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $pids) {
        try {
            Stop-Process -Id $processId -Force -ErrorAction Stop
            Write-Host "Stopped PID $processId on port $Port"
        } catch {
            Write-Warning "Could not stop PID $processId on port ${Port}: $($_.Exception.Message)"
        }
    }
}

if (Test-Path $ffmpegBin) {
    $alreadyPresent = ($env:PATH -split ";") -contains $ffmpegBin
    if (-not $alreadyPresent) {
        $env:PATH = "$ffmpegBin;$env:PATH"
    }
    $env:DANDY_FFMPEG = Join-Path $ffmpegBin "ffmpeg.exe"
    $env:DANDY_FFPROBE = Join-Path $ffmpegBin "ffprobe.exe"
} else {
    Write-Warning "FFmpeg path not found: $ffmpegBin"
}

if ($Restart) {
    Stop-ByPort -Port $BackendPort
    Stop-ByPort -Port $FrontendPort
}

if (-not $NoBackend) {
    $backendListener = Get-NetTCPConnection -LocalPort $BackendPort -State Listen -ErrorAction SilentlyContinue
    if ($backendListener) {
        Write-Host "Backend already listening on http://127.0.0.1:$BackendPort"
    } else {
        $env:DANDY_LLAMACPP_BASE_URL = $LlamaCppBaseUrl.TrimEnd("/")
        if (-not $LlamaCppModel) {
            $modelList = Invoke-RestMethod -Uri "$($env:DANDY_LLAMACPP_BASE_URL)/models" -TimeoutSec 5
            $LlamaCppModel = ($modelList.data | Where-Object { $_.id -match "DeepSeek.*7B" } | Select-Object -First 1).id
            if (-not $LlamaCppModel) {
                throw "DeepSeek 7B was not found at $LlamaCppBaseUrl. Supply -LlamaCppModel to select a different local model."
            }
        }
        $env:DANDY_LLAMACPP_MODEL = $LlamaCppModel
        $env:PYTHONUNBUFFERED = "1"
        $backendProcess = Start-Process -FilePath $pythonCmd -ArgumentList $pythonArgs `
            -WorkingDirectory $backendDir -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $logDir "backend.out.log") `
            -RedirectStandardError (Join-Path $logDir "backend.err.log") -PassThru
        Write-Host "Backend PID $($backendProcess.Id) launched on http://127.0.0.1:$BackendPort"
        Write-Host "Writer: $LlamaCppModel at $($env:DANDY_LLAMACPP_BASE_URL)"
    }
}

if (-not $NoFrontend) {
    $frontendListener = Get-NetTCPConnection -LocalPort $FrontendPort -State Listen -ErrorAction SilentlyContinue
    if ($frontendListener) {
        Write-Host "Frontend already listening on http://127.0.0.1:$FrontendPort"
    } else {
        $env:DANDY_API_TARGET = "http://127.0.0.1:$BackendPort"
        $nodeCmd = (Get-Command node -ErrorAction Stop).Source
        $viteScript = Join-Path $frontendDir "node_modules\vite\bin\vite.js"
        if (-not (Test-Path $viteScript)) {
            throw "Vite is not installed at $viteScript. Run npm install in frontend first."
        }
        $frontendProcess = Start-Process -FilePath $nodeCmd `
            -ArgumentList @("`"$viteScript`"", "--host", "127.0.0.1", "--port", "$FrontendPort", "--strictPort") `
            -WorkingDirectory $frontendDir -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $logDir "frontend.out.log") `
            -RedirectStandardError (Join-Path $logDir "frontend.err.log") -PassThru
        Write-Host "Frontend PID $($frontendProcess.Id) launched on http://127.0.0.1:$FrontendPort"
    }
}

if (-not $NoQwen) {
    if (-not (Test-Path $qwenModeScript)) {
        Write-Warning "Qwen launcher not found: $qwenModeScript"
    } else {
        $qwenPort = [int]$QwenPorts[$QwenMode]
        $qwenListener = Get-NetTCPConnection -LocalPort $qwenPort -State Listen -ErrorAction SilentlyContinue
        if ($qwenListener) {
            Write-Host "Qwen $QwenMode already ready on http://127.0.0.1:$qwenPort"
        } else {
            Start-Process -FilePath "powershell" -WindowStyle Hidden -ArgumentList @(
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-File", "`"$qwenModeScript`"",
                "-Mode", $QwenMode, "-NoStopExisting"
            ) -RedirectStandardOutput (Join-Path $logDir "qwen-start.out.log") `
              -RedirectStandardError (Join-Path $logDir "qwen-start.err.log") | Out-Null
            Write-Host "Qwen $QwenMode launch requested on http://127.0.0.1:$qwenPort"
        }
    }
    foreach ($service in @(
        @{ Port = 8020; Script = $qwenBridgeScript; Name = "qwen-bridge" },
        @{ Port = 7861; Script = $qwenUiScript; Name = "qwen-operator" }
    )) {
        if (-not (Get-NetTCPConnection -LocalPort $service.Port -State Listen -ErrorAction SilentlyContinue)) {
            Start-Process -FilePath "powershell" -WindowStyle Hidden -ArgumentList @(
                "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$($service.Script)`""
            ) -RedirectStandardOutput (Join-Path $logDir "$($service.Name)-start.out.log") `
              -RedirectStandardError (Join-Path $logDir "$($service.Name)-start.err.log") | Out-Null
            Write-Host "$($service.Name) launch requested on http://127.0.0.1:$($service.Port)"
        }
    }
}

Start-Sleep -Seconds 2
try {
    $health = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:$BackendPort/health" -TimeoutSec 3
    Write-Host "Backend health:" ($health | ConvertTo-Json -Compress)
} catch {
    Write-Warning "Backend health check not ready yet."
}
