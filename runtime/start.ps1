param([switch]$NoBrowser)
$args = @('-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'research-os.ps1'),'-Action','start')
if ($NoBrowser) { $args += '-NoBrowser' }
& powershell @args
exit $LASTEXITCODE
