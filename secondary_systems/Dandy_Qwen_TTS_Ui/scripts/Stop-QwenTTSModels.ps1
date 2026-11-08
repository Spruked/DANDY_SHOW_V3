param(
    [int[]]$Ports = @(8032, 8033)
)

$ErrorActionPreference = "Continue"

if ($Ports -contains 8031) { throw "Port 8031 is a shared PC service. Stop it through the Shared Qwen3 TTS task, not Dandy." }

. (Join-Path $PSScriptRoot "../../../scripts/studio/processes.ps1")
foreach ($port in $Ports) {
    if ($port -notin @(8031, 8032, 8033)) { throw "Unsupported Qwen model port" }
    Stop-DandyListener -Port $port -ExpectedCommand 'qwen_tts.cli.demo'
}
