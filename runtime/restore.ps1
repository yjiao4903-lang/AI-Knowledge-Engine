#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Backup,
    [string]$RestoreCognitionDir = '',
    [string]$RestoreTaskpackDir = '',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$backupRoot = if ($env:AIKE_BACKUP_ROOT) { $env:AIKE_BACKUP_ROOT } else { Join-Path $repoRoot 'backups' }
$backupDir = if (Test-Path $Backup) { (Resolve-Path $Backup).Path } else { Join-Path $backupRoot $Backup }
$manifestPath = Join-Path $backupDir 'manifest.json'
if (-not (Test-Path $manifestPath)) { throw "manifest.json not found: $manifestPath" }

$manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
$bad = 0
foreach ($f in $manifest.files) {
    $full = Join-Path $backupDir $f.path.Replace('/','\')
    if (-not (Test-Path $full)) { Write-Host "FAIL missing $($f.path)" -ForegroundColor Red; $bad++; continue }
    $hash = (Get-FileHash $full -Algorithm SHA256).Hash.ToLower()
    if ($hash -ne $f.sha256) { Write-Host "FAIL hash $($f.path)" -ForegroundColor Red; $bad++ }
}
if ($bad -gt 0) { throw "backup verification failed: $bad file(s)" }
Write-Host "PASS backup manifest verified: $($manifest.files.Count) files" -ForegroundColor Green

if (-not $Force) {
    Write-Host 'Verification only. Pass -Force with explicit restore targets to copy data.' -ForegroundColor Yellow
    exit 0
}

if (-not $RestoreCognitionDir -and -not $RestoreTaskpackDir) {
    throw '-Force requires -RestoreCognitionDir and/or -RestoreTaskpackDir'
}

if ($RestoreCognitionDir) {
    $src = Join-Path $backupDir 'cognition'
    if (-not (Test-Path $src)) { throw "cognition snapshot missing: $src" }
    New-Item -ItemType Directory -Force -Path $RestoreCognitionDir | Out-Null
    Copy-Item (Join-Path $src '*') $RestoreCognitionDir -Recurse -Force
    Write-Host "Cognition restored to: $RestoreCognitionDir" -ForegroundColor Green
}

if ($RestoreTaskpackDir) {
    $src = Join-Path $backupDir 'taskpacks'
    if (-not (Test-Path $src)) { throw "taskpack snapshot missing: $src" }
    New-Item -ItemType Directory -Force -Path $RestoreTaskpackDir | Out-Null
    Copy-Item (Join-Path $src '*') $RestoreTaskpackDir -Recurse -Force
    Write-Host "TaskPack artifacts restored to: $RestoreTaskpackDir" -ForegroundColor Green
}

Write-Host 'Restore completed. Rebuild derived indexes before normal use.' -ForegroundColor Yellow
