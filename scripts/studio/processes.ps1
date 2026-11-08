# Process ownership checks shared by the supported launchers.
function Stop-DandyListener {
    param([int]$Port, [string]$ExpectedCommand)
    foreach ($listener in @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) {
        $ownedProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        if (-not $ownedProcess -or $ownedProcess.CommandLine -notmatch $ExpectedCommand) {
            throw "Refusing to stop unexpected process on port $Port"
        }
        Assert-DandyListener -Port $Port -ExpectedCommand $ExpectedCommand
        Stop-Process -Id $ownedProcess.ProcessId -ErrorAction Stop
        for ($releaseAttempt = 0; $releaseAttempt -lt 30; $releaseAttempt++) {
            if (-not (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) { break }
            Start-Sleep -Milliseconds 100
        }
        Write-Output "Stopped Dandy process $($ownedProcess.ProcessId) on port $Port"
    }
}

function Assert-DandyListener {
    param([int]$Port, [string]$ExpectedCommand)
    foreach ($listener in @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) {
        $ownedProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        if (-not $ownedProcess -or $ownedProcess.CommandLine -notmatch $ExpectedCommand) {
            throw "Port $Port is occupied by an unrelated process"
        }
        $expectedRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
        if ($ownedProcess.CommandLine -match 'app.main:app') {
            $health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 5
            if ($health.project_root -ne $expectedRoot) { throw "Backend on $Port belongs to another workspace" }
        } elseif ($ownedProcess.CommandLine -match 'bridge:app') {
            $health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 5
            if ($health.show_root -ne $expectedRoot) { throw "Bridge on $Port belongs to another workspace" }
        }
    }
}
