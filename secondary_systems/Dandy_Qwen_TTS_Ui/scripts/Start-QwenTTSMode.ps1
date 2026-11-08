param(
    [ValidateSet("custom", "clone", "design")]
    [string]$Mode = "custom",
    [switch]$NoStopExisting
)

$ErrorActionPreference = "Stop"

if ($Mode -eq "custom") {
    & (Join-Path $PSScriptRoot "Start-QwenCustomLocal.ps1")
    return
}

$PackageRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $PackageRoot "logs"
New-Item -ItemType Directory -Force $LogDir | Out-Null

$ShowRoot = (Resolve-Path (Join-Path $PackageRoot "../..")).Path
$RuntimePath = Join-Path $ShowRoot "config/runtime.local.json"
$Runtime = if (Test-Path -LiteralPath $RuntimePath) { Get-Content -LiteralPath $RuntimePath -Raw | ConvertFrom-Json } else { $null }
$Python = if ($env:DANDY_QWEN_PYTHON) { $env:DANDY_QWEN_PYTHON } elseif ($Runtime.qwen_python) { $Runtime.qwen_python } else { Join-Path $ShowRoot ".venv-qwen/Scripts/python.exe" }
if (-not [IO.Path]::IsPathRooted($Python)) { $Python = Join-Path $ShowRoot $Python }
$QwenEngine = $PackageRoot
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:GRADIO_ANALYTICS_ENABLED = "False"
$env:PYTHONIOENCODING = "utf-8"
$SoxDir = "C:\Users\bryan\AppData\Local\Microsoft\WinGet\Packages\ChrisBagwell.SoX_Microsoft.Winget.Source_8wekyb3d8bbwe\sox-14.4.2"
$env:PATH = "$SoxDir;$env:PATH"

$Modes = @{
    custom = @{
        Port = 8031
        Checkpoint = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
        Description = "Built-in Qwen speakers: Ryan, Aiden, Vivian, etc."
    }
    clone = @{
        Port = 8032
        Checkpoint = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
        Description = "Voice clone, save/load reusable voice prompts."
    }
    design = @{
        Port = 8033
        Checkpoint = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
        Description = "Natural-language voice design."
    }
}

$Selected = $Modes[$Mode]
$Port = [int]$Selected.Port
$Checkpoint = [string]$Selected.Checkpoint

if (-not (Test-Path $Python)) {
    throw "Python venv not found: $Python"
}

# Resolve a complete local checkpoint before stopping any running service.
& $Python (Join-Path $PSScriptRoot "english_demo.py")
if ($LASTEXITCODE -ne 0) { throw "Could not prepare the English Qwen UI." }
$CheckpointPath = & $Python -c "import sys; from huggingface_hub import snapshot_download; print(snapshot_download(repo_id=sys.argv[1], local_files_only=True))" $Checkpoint
if ($LASTEXITCODE -ne 0 -or -not $CheckpointPath) { throw "Qwen checkpoint is not installed locally: $Checkpoint" }
$Checkpoint = ([string]$CheckpointPath).Trim()
if (-not (Test-Path -LiteralPath (Join-Path $Checkpoint "config.json"))) { throw "Qwen checkpoint is incomplete: $Checkpoint" }

if (-not $NoStopExisting) {
    & (Join-Path $PSScriptRoot "Stop-QwenTTSModels.ps1") | Out-Host
}

$OutLog = Join-Path $LogDir "qwen-$Mode-$Port.out.log"
$ErrLog = Join-Path $LogDir "qwen-$Mode-$Port.err.log"

$Args = @(
    "-m", "qwen_tts.cli.demo",
    $Checkpoint,
    "--ip", "127.0.0.1",
    "--port", "$Port",
    "--device", "cuda:0",
    "--dtype", "float16",
    "--flash-attn"
)

$Process = Start-Process `
    -FilePath $Python `
    -ArgumentList $Args `
    -WorkingDirectory $QwenEngine `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -PassThru

Write-Output "Started Qwen TTS mode=$Mode pid=$($Process.Id) port=$Port"
Write-Output "Checkpoint=$Checkpoint"
Write-Output "Description=$($Selected.Description)"
Write-Output "Logs:"
Write-Output "  $OutLog"
Write-Output "  $ErrLog"

for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep -Seconds 2
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        Write-Output "Ready: http://127.0.0.1:$Port"
        exit 0
    }
}

Write-Output "Not ready yet after wait. Check logs:"
Write-Output "  $ErrLog"
exit 1
