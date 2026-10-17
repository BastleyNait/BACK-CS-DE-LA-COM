param([switch]$Inicializar, [int]$Port = 8000)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
$python = Join-Path $PWD ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Ejecuta primero scripts\preparar-pruebas.ps1." }
if ($Inicializar) { & $python -m app.db.bootstrap_test }
else { & $python -m app.db.bootstrap_test --check }
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m uvicorn app.main:app --host 127.0.0.1 --port $Port --reload
exit $LASTEXITCODE
