param([switch]$VerifyAfter)
$args = @('-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'research-os.ps1'),'-Action','backup')
if ($VerifyAfter) { $args += '-VerifyBackup' }
& powershell @args
exit $LASTEXITCODE
