param([switch]$Qdrant)
$args = @('-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'research-os.ps1'),'-Action','stop')
if ($Qdrant) { $args += '-StopQdrant' }
& powershell @args
exit $LASTEXITCODE
