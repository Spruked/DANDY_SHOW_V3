param(
    [int[]]$Ports = @(8031, 8032, 8033)
)

$ErrorActionPreference = "Continue"

$stopped = @{}

foreach ($port in $Ports) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object {
            $pid = [int]$_.OwningProcess
            if (-not $stopped.ContainsKey($pid)) {
                Write-Output "Stopping Qwen listener process $pid on port $port"
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
                $stopped[$pid] = $true
            }
        }
}

# Also catch a Qwen demo process that is still loading and has not bound its
# port yet. This prevents a cancelled model switch from appearing later after
# the UI already reported that Qwen was stopped.
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.CommandLine -and
        $_.CommandLine -match 'qwen_tts\.cli\.demo' -and
        $_.CommandLine -match 'Qwen3-TTS-12Hz-1\.7B-(CustomVoice|Base|VoiceDesign)'
    } |
    ForEach-Object {
        $pid = [int]$_.ProcessId
        if (-not $stopped.ContainsKey($pid)) {
            Write-Output "Stopping loading Qwen process $pid"
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            $stopped[$pid] = $true
        }
    }

Start-Sleep -Seconds 2

Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $Ports -contains $_.LocalPort } |
    Select-Object LocalAddress, LocalPort, OwningProcess
