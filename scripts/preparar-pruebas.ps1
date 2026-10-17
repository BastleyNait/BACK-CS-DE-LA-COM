$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if (-not (Test-Path -LiteralPath ".env")) {
    $content = [IO.File]::ReadAllText((Join-Path $PWD ".env.test.example"))
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $content = $content.Replace("CHANGE_LOCAL_SECRET", [Convert]::ToBase64String($bytes))
    $rng.GetBytes($bytes)
    $content = $content.Replace("CHANGE_LOCAL_PASSWORD", [Convert]::ToBase64String($bytes))
    $rng.Dispose()
    [IO.File]::WriteAllText((Join-Path $PWD ".env"), $content, (New-Object Text.UTF8Encoding($false)))
}
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output "Completa DATABASE_URL y TEST_DATABASE_PROJECT_REF en .env; despues ejecuta .\scripts\iniciar-pruebas.ps1 -Inicializar"
