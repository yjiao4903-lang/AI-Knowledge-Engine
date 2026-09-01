& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'research-os.ps1') -Action health
exit $LASTEXITCODE
