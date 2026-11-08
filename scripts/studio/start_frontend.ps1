param([int]$Port = 5173, [int]$BackendPort = 8110)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "../../frontend")
$env:DANDY_API_TARGET = "http://127.0.0.1:$BackendPort"
& npm.cmd run dev -- --host 127.0.0.1 --port $Port --strictPort
exit $LASTEXITCODE
