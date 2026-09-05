param(
    [switch]$Restart,
    [switch]$NoBackend,
    [switch]$NoFrontend,
    [switch]$NoQwen,
    [switch]$Reload,
    [ValidateSet("custom", "clone", "design")]
    [string]$QwenMode = "custom",
    [int]$BackendPort = 8110,
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"
$qwenRoot = Join-Path $root "secondary_systems\Dandy_Qwen_TTS_Ui"
$qwenModeScript = Join-Path $qwenRoot "scripts\Start-QwenTTSMode.ps1"
$ffmpegBin = Join-Path $root "staging\ffmpeg\ffmpeg-master-latest-win64-gpl\bin"
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
} else {
    Write-Warning "FFmpeg path not found: $ffmpegBin"
}

if ($Restart) {
    Stop-ByPort -Port $BackendPort
    Stop-ByPort -Port $FrontendPort
}

if (-not $NoBackend) {
    $backendArgsLiteral = ($pythonArgs | ForEach-Object { "'$_'" }) -join ", "
    $backendCmd = @"
`$env:PATH = '$($env:PATH)';
Set-Location '$backendDir';
& '$pythonCmd' @($backendArgsLiteral)
"@
    Start-Process -FilePath "powershell" -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-Command", $backendCmd
    ) | Out-Null
    Write-Host "Backend launch requested on http://127.0.0.1:$BackendPort"
}

if (-not $NoFrontend) {
    $frontendCmd = @"
Set-Location '$frontendDir';
`$env:DANDY_API_TARGET = 'http://127.0.0.1:$BackendPort';
npm run dev -- --host 127.0.0.1 --port $FrontendPort
"@
    Start-Process -FilePath "powershell" -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-Command", $frontendCmd
    ) | Out-Null
    Write-Host "Frontend launch requested on http://127.0.0.1:$FrontendPort"
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
                "-File", $qwenModeScript,
                "-Mode", $QwenMode
            ) | Out-Null
            Write-Host "Qwen $QwenMode launch requested on http://127.0.0.1:$qwenPort"
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
