#Requires -Version 5.1
<#
.SYNOPSIS
  Safely copy legacy TaskPack data from the former integration workspace into
  AI-Knowledge-Engine/data/taskpacks. Source data is never deleted.

.EXAMPLE
  # Dry run
  .\runtime\migrate-taskpacks.ps1

  # Apply after reviewing the dry run
  .\runtime\migrate-taskpacks.ps1 -Apply
#>

[CmdletBinding()]
param(
    [string]$Source = 'D:\AI知识整合体系\taskpacks',
    [string]$Destination = '',
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
if (-not $Destination) { $Destination = Join-Path $repoRoot 'data\taskpacks' }

if (-not (Test-Path $Source)) {
    Write-Host "Legacy TaskPack root not found; nothing to migrate: $Source" -ForegroundColor Yellow
    exit 0
}

$sourceFull = (Resolve-Path $Source).Path.TrimEnd('\')
$destinationFull = [System.IO.Path]::GetFullPath($Destination).TrimEnd('\')
if ($sourceFull -eq $destinationFull) {
    Write-Host 'Source and destination are identical; nothing to migrate.' -ForegroundColor Green
    exit 0
}

$files = @(Get-ChildItem $sourceFull -Recurse -Force -File)
$copyCount = 0
$sameCount = 0
$conflicts = @()

foreach ($file in $files) {
    $rel = $file.FullName.Substring($sourceFull.Length).TrimStart('\')
    $target = Join-Path $destinationFull $rel
    if (Test-Path $target) {
        $srcHash = (Get-FileHash $file.FullName -Algorithm SHA256).Hash
        $dstHash = (Get-FileHash $target -Algorithm SHA256).Hash
        if ($srcHash -eq $dstHash) {
            $sameCount++
            continue
        }
        $conflicts += $rel
        continue
    }
    $copyCount++
    if ($Apply) {
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item $file.FullName $target
    }
}

Write-Host "Source:      $sourceFull"
Write-Host "Destination: $destinationFull"
Write-Host "Files:       $($files.Count)"
Write-Host "Already same: $sameCount"
Write-Host "To copy:      $copyCount"
Write-Host "Conflicts:    $($conflicts.Count)"

if ($conflicts.Count -gt 0) {
    Write-Host 'Conflicting destination files (different SHA256):' -ForegroundColor Red
    $conflicts | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    throw 'Migration stopped because conflicting files exist. No source files were deleted.'
}

if (-not $Apply) {
    Write-Host 'DRY RUN only. Re-run with -Apply to copy missing files.' -ForegroundColor Yellow
    exit 0
}

# Verify every source file exists at destination with identical SHA256.
$bad = 0
foreach ($file in $files) {
    $rel = $file.FullName.Substring($sourceFull.Length).TrimStart('\')
    $target = Join-Path $destinationFull $rel
    if (-not (Test-Path $target)) { $bad++; continue }
    if ((Get-FileHash $file.FullName -Algorithm SHA256).Hash -ne (Get-FileHash $target -Algorithm SHA256).Hash) {
        $bad++
    }
}
if ($bad -gt 0) { throw "Migration verification failed: $bad file(s)" }

Write-Host 'TaskPack migration PASS. Legacy source remains untouched.' -ForegroundColor Green
