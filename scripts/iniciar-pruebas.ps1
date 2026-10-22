param([switch]$Inicializar, [int]$Port = 8000, [switch]$Lan, [string]$LanHost = "")
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
$python = Join-Path $PWD ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Ejecuta primero scripts\preparar-pruebas.ps1." }
if ($Inicializar) { & $python -m app.db.bootstrap_test }
else { & $python -m app.db.bootstrap_test --check }
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$bindAddress = "127.0.0.1"
if ($Lan) {
    if (-not $LanHost) {
        $LanHost = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.IPv4Address -and $_.InterfaceAlias -notmatch 'vEthernet|WSL' } | ForEach-Object { $_.IPv4Address.IPAddress } | Select-Object -First 1
    }
    $parsed = $null
    if (-not [System.Net.IPAddress]::TryParse($LanHost, [ref]$parsed)) { throw "No se encontro una IPv4 LAN. Indica -LanHost con la IP de Windows." }
    $env:DEV_LAN_HOST = $LanHost
    $bindAddress = "0.0.0.0"
    Write-Host "API de pruebas para celular: http://${LanHost}:$Port"
}
& $python -m uvicorn app.main:app --host $bindAddress --port $Port --reload
exit $LASTEXITCODE
