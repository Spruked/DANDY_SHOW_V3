param(
    [switch]$Restart, [switch]$NoBackend, [switch]$NoFrontend,
    [switch]$NoQwen, [switch]$Reload, [switch]$Production,
    [int]$BackendPort = 8110, [int]$FrontendPort = 5173
)
$ErrorActionPreference = "Stop"
if ($Production) { $NoFrontend = $true; if ($Reload) { throw "Production mode cannot use reload" } }
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
. (Join-Path $PSScriptRoot "studio/processes.ps1")
$runtimePath = Join-Path $root "config/runtime.local.json"
$runtime = if (Test-Path $runtimePath) { Get-Content -LiteralPath $runtimePath -Raw | ConvertFrom-Json } else { $null }
$pythonCmd = if ($env:DANDY_PYTHON) { $env:DANDY_PYTHON } elseif ($runtime.python) { $runtime.python } else { Join-Path $root ".venv/Scripts/python.exe" }
if (-not [IO.Path]::IsPathRooted($pythonCmd)) { $pythonCmd = Join-Path $root $pythonCmd }
if (-not $NoBackend -and -not (Test-Path -LiteralPath $pythonCmd)) { throw "Create the studio venv or set DANDY_PYTHON." }
if ($runtime.ffmpeg_bin) { $env:PATH = "$($runtime.ffmpeg_bin);$env:PATH" }
if ($runtime.writer_base_url) { $env:DANDY_LLAMACPP_BASE_URL = $runtime.writer_base_url }
foreach ($tool in @("ffmpeg", "ffprobe")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool is missing from PATH" }
}
if ($Restart) { & (Join-Path $PSScriptRoot "stop_dandy_stack.ps1") -BackendPort $BackendPort -FrontendPort $FrontendPort -KeepQwen }
if ($Production -and -not (Test-Path (Join-Path $root "frontend/dist/index.html"))) { throw "Build the frontend with npm ci and npm run build first" }
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
if (-not $NoBackend) {
    Assert-DandyListener -Port $BackendPort -ExpectedCommand 'uvicorn.*app.main:app'
    if (-not (Get-NetTCPConnection -LocalPort $BackendPort -State Listen -ErrorAction SilentlyContinue)) {
        $backendArgs = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$BackendPort")
        if ($Reload) { $backendArgs += "--reload" }
        Start-Process -FilePath $pythonCmd -ArgumentList $backendArgs -WorkingDirectory (Join-Path $root "backend") -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "backend.out.log") -RedirectStandardError (Join-Path $logDir "backend.err.log") | Out-Null
    }
}
if (-not $NoFrontend) {
    Assert-DandyListener -Port $FrontendPort -ExpectedCommand "$([regex]::Escape($root)).*vite"
    if (-not (Get-NetTCPConnection -LocalPort $FrontendPort -State Listen -ErrorAction SilentlyContinue)) {
        $frontendScript = Join-Path $PSScriptRoot "studio/start_frontend.ps1"
        $frontendShell = if (Get-Command pwsh.exe -ErrorAction SilentlyContinue) { (Get-Command pwsh.exe).Source } else { "powershell.exe" }
        Start-Process -FilePath $frontendShell -ArgumentList @("-NoProfile", "-File", "`"$frontendScript`"", "-Port", "$FrontendPort", "-BackendPort", "$BackendPort") -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "frontend.out.log") -RedirectStandardError (Join-Path $logDir "frontend.err.log") | Out-Null
    }
}
if (-not $NoBackend -and -not $NoQwen) { & (Join-Path $root "secondary_systems/Dandy_Qwen_TTS_Ui/scripts/Start-QwenCustomLocal.ps1") }
if ($Production) { Write-Output "Production studio: http://127.0.0.1:$BackendPort/studio" }
Write-Output "Dandy launch requested: http://127.0.0.1:$FrontendPort ; API http://127.0.0.1:$BackendPort"
