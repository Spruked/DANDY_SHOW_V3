param([int]$BackendPort = 8110, [int]$FrontendPort = 5173, [switch]$KeepQwen)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "studio/processes.ps1")
try {
    $episodes = Invoke-RestMethod "http://127.0.0.1:$BackendPort/api/episodes" -TimeoutSec 5
} catch { $episodes = $null }
$records = if ($episodes.episodes) { $episodes.episodes } else { $episodes }
if (@($records | Where-Object { $_.status -in @("producing", "queued") }).Count) {
    throw "Production is active. Wait for completion before shutting down."
}
$repoPattern = [regex]::Escape((Resolve-Path (Join-Path $PSScriptRoot "..")).Path)
Stop-DandyListener -Port $FrontendPort -ExpectedCommand "$repoPattern.*vite"
Stop-DandyListener -Port $BackendPort -ExpectedCommand 'uvicorn.*app.main:app'
if (-not $KeepQwen) {
    Stop-DandyListener -Port 8020 -ExpectedCommand 'uvicorn.*bridge:app'
}
Write-Output "Dandy stopped. Shared writer and Qwen TTS model services were preserved."
