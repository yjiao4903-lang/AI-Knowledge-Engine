#Requires -Version 5.1
<#
.SYNOPSIS
  Unified local runtime for AI-Knowledge-Engine + Cognition App.

.DESCRIPTION
  This script absorbs the useful runtime responsibilities previously kept in
  the standalone integration workspace while keeping the two data domains
  separate. Knowledge Engine never writes formal Cognition Markdown.

  Actions:
    start  - start Cognition first, then Qdrant + KE; browser becomes usable early
    stop   - stop only processes started/identified by this runtime (PID scoped)
    health - PASS/WARN/FAIL status for Cognition, KE, Qdrant and TaskPack
    backup - backup formal Cognition Markdown + durable TaskPack research artifacts

  Optional environment overrides:
    COGNITION_APP_ROOT
    COGNITION_DATA_ROOT
    AIKE_TASKPACK_ROOT
    AIKE_BACKUP_ROOT
    AIKE_KE_PORT
    AIKE_COGNITION_PORT
    AIKE_QDRANT_CONTAINER
#>

[CmdletBinding()]
param(
    [ValidateSet('start','stop','health','backup')]
    [string]$Action = 'health',
    [switch]$NoBrowser,
    [switch]$StopQdrant,
    [switch]$VerifyBackup
)

$ErrorActionPreference = 'Stop'

$script:RepoRoot = Split-Path $PSScriptRoot -Parent
$script:RuntimeRoot = $PSScriptRoot
$script:LogRoot = Join-Path $script:RepoRoot 'logs'
$script:PidsFile = Join-Path $script:RuntimeRoot 'research-os-pids.json'
$script:Python = Join-Path $script:RepoRoot '.venv\Scripts\python.exe'
$script:KePort = if ($env:AIKE_KE_PORT) { [int]$env:AIKE_KE_PORT } else { 8765 }
$script:CogPort = if ($env:AIKE_COGNITION_PORT) { [int]$env:AIKE_COGNITION_PORT } else { 3220 }
$script:CognitionAppRoot = if ($env:COGNITION_APP_ROOT) { $env:COGNITION_APP_ROOT } else { 'E:\CODEX\AI深度研究\cognition-app' }
$script:CognitionDataRoot = if ($env:COGNITION_DATA_ROOT) { $env:COGNITION_DATA_ROOT } else { 'E:\CODEX\AI深度研究\cognition' }
$script:TaskpackRoot = if ($env:AIKE_TASKPACK_ROOT) { $env:AIKE_TASKPACK_ROOT } else { 'D:\AI知识整合体系\taskpacks' }
$script:BackupRoot = if ($env:AIKE_BACKUP_ROOT) { $env:AIKE_BACKUP_ROOT } else { Join-Path $script:RepoRoot 'backups' }
$script:QdrantContainer = if ($env:AIKE_QDRANT_CONTAINER) { $env:AIKE_QDRANT_CONTAINER } else { 'ai-kb-qdrant' }
$script:DockerDesktop = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'

function Ensure-Dirs {
    New-Item -ItemType Directory -Force -Path $script:LogRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $script:RuntimeRoot | Out-Null
}

function Write-IntegrationLog([string]$Level, [string]$Message) {
    Ensure-Dirs
    $path = Join-Path $script:LogRoot ('research-os-' + (Get-Date -Format 'yyyyMMdd') + '.log')
    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss'), $Level, $Message
    Add-Content -Path $path -Value $line -Encoding UTF8
    Get-ChildItem $script:LogRoot -Filter 'research-os-*.log' -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

function Get-Json([string]$Url, [int]$TimeoutSec = 5) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec $TimeoutSec -ErrorAction Stop
        $body = $null
        if ($r.Content) { try { $body = $r.Content | ConvertFrom-Json } catch { } }
        return @{ ok = ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300); status = [int]$r.StatusCode; body = $body }
    } catch {
        return @{ ok = $false; status = 0; body = $null; error = $_.Exception.Message }
    }
}

function Wait-Http([string]$Url, [int]$TimeoutSec, [int]$IntervalSec = 2) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if ((Get-Json $Url 4).ok) { return $true }
        Start-Sleep -Seconds $IntervalSec
    }
    return $false
}

function Test-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { return $false }
    & docker info *> $null
    return ($LASTEXITCODE -eq 0)
}

function Get-PortPid([int]$Port) {
    $c = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return [int]$c.OwningProcess }
    return $null
}

function Stop-Tree([int]$Pid) {
    if (-not $Pid -or $Pid -le 0) { return }
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & taskkill /PID $Pid /T /F *> $null
    $ErrorActionPreference = $old
}

function Read-Pids {
    if (-not (Test-Path $script:PidsFile)) { return $null }
    try { return (Get-Content -Raw -Encoding UTF8 $script:PidsFile | ConvertFrom-Json) } catch { return $null }
}

function Save-Pids([object]$Pids) {
    $Pids | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -Path $script:PidsFile
}

function Start-Cognition {
    $home = Get-Json "http://127.0.0.1:$($script:CogPort)/" 3
    if ($home.ok) {
        Write-Host 'Cognition already running.' -ForegroundColor Green
        return $null
    }
    $bat = Join-Path $script:CognitionAppRoot 'start.bat'
    if (-not (Test-Path $bat)) {
        Write-Host "WARN  Cognition start.bat not found: $bat" -ForegroundColor Yellow
        Write-IntegrationLog 'WARN' "Cognition start.bat missing: $bat"
        return $null
    }
    $out = Join-Path $script:LogRoot 'cognition-console.out.log'
    $err = Join-Path $script:LogRoot 'cognition-console.err.log'
    $p = Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c','start.bat') -WorkingDirectory $script:CognitionAppRoot -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
    Write-Host "Cognition starting (PID $($p.Id))..." -ForegroundColor Yellow
    if (-not (Wait-Http "http://127.0.0.1:$($script:CogPort)/" 180 3)) {
        Write-Host 'WARN  Cognition did not become ready; KE can still be started.' -ForegroundColor Yellow
        Write-IntegrationLog 'WARN' 'Cognition startup timeout'
    } else {
        Write-Host 'Cognition is ready.' -ForegroundColor Green
    }
    return $p.Id
}

function Ensure-Qdrant {
    if (-not (Test-Docker)) {
        if (Test-Path $script:DockerDesktop) {
            Write-Host 'Docker unavailable; starting Docker Desktop...' -ForegroundColor Yellow
            Start-Process $script:DockerDesktop | Out-Null
            $deadline = (Get-Date).AddSeconds(180)
            while ((Get-Date) -lt $deadline -and -not (Test-Docker)) { Start-Sleep 5 }
        }
    }
    if (-not (Test-Docker)) {
        Write-Host 'WARN  Docker unavailable; semantic retrieval may remain degraded.' -ForegroundColor Yellow
        Write-IntegrationLog 'WARN' 'Docker unavailable'
        return $false
    }
    $state = (& docker ps -a --filter "name=$($script:QdrantContainer)" --format '{{.State}}' 2>$null | Select-Object -First 1)
    if (-not $state) {
        & docker run -d --name $script:QdrantContainer -p 127.0.0.1:6333:6333 -p 127.0.0.1:6334:6334 -v qdrant_storage:/qdrant/storage --restart unless-stopped qdrant/qdrant:v1.19.0 | Out-Null
    } elseif ($state -notmatch 'running') {
        & docker start $script:QdrantContainer | Out-Null
    }
    if (Wait-Http 'http://127.0.0.1:6333/readyz' 60 2) {
        Write-Host 'Qdrant ready.' -ForegroundColor Green
        return $true
    }
    Write-Host 'WARN  Qdrant not ready.' -ForegroundColor Yellow
    return $false
}

function Start-KE {
    if ((Get-Json "http://127.0.0.1:$($script:KePort)/api/health" 3).ok) {
        Write-Host 'Knowledge Engine already running.' -ForegroundColor Green
        return $null
    }
    if (-not (Test-Path $script:Python)) {
        Write-Host "FAIL  Python venv missing: $($script:Python)" -ForegroundColor Red
        return $null
    }
    $out = Join-Path $script:LogRoot 'ke-console.out.log'
    $err = Join-Path $script:LogRoot 'ke-console.err.log'
    $args = @('-m','uvicorn','app.main:create_app','--factory','--app-dir','backend','--host','127.0.0.1','--port',"$($script:KePort)")
    $p = Start-Process -FilePath $script:Python -ArgumentList $args -WorkingDirectory $script:RepoRoot -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
    Write-Host "Knowledge Engine starting (PID $($p.Id))..." -ForegroundColor Yellow
    if (Wait-Http "http://127.0.0.1:$($script:KePort)/api/health" 330 5) {
        Write-Host 'Knowledge Engine is ready.' -ForegroundColor Green
    } else {
        Write-Host 'WARN  KE did not become ready; Cognition remains independently usable.' -ForegroundColor Yellow
        Write-IntegrationLog 'WARN' 'KE startup timeout'
    }
    return $p.Id
}

function Invoke-Start {
    Ensure-Dirs
    # Product shell first: Cognition remains useful while semantic services warm.
    $cogPid = Start-Cognition
    if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$($script:CogPort)/" | Out-Null }
    $null = Ensure-Qdrant
    $kePid = Start-KE
    Save-Pids ([ordered]@{
        started_at = (Get-Date).ToString('o')
        cognition_pid = $cogPid
        ke_pid = $kePid
        cognition_port_pid = Get-PortPid $script:CogPort
        ke_port_pid = Get-PortPid $script:KePort
    })
    Write-IntegrationLog 'INFO' 'runtime start completed'
    Invoke-Health
}

function Invoke-Stop {
    $p = Read-Pids
    if ($p) {
        if ($p.cognition_pid) { Stop-Tree ([int]$p.cognition_pid) }
        if ($p.cognition_port_pid) { Stop-Tree ([int]$p.cognition_port_pid) }
        if ($p.ke_pid) { Stop-Tree ([int]$p.ke_pid) }
        if ($p.ke_port_pid) { Stop-Tree ([int]$p.ke_port_pid) }
    } else {
        Write-Host 'WARN  PID record missing; no broad process kill will be attempted.' -ForegroundColor Yellow
    }
    if ($StopQdrant -and (Test-Docker)) { & docker stop $script:QdrantContainer | Out-Null }
    Remove-Item $script:PidsFile -Force -ErrorAction SilentlyContinue
    Write-IntegrationLog 'INFO' 'runtime stop completed'
    Write-Host 'Runtime stop completed.' -ForegroundColor Green
}

function Invoke-Health {
    $fail = 0; $warn = 0
    function Show([string]$Verdict, [string]$Name, [string]$Detail) {
        if ($Verdict -eq 'FAIL') { $script:fail++ }
        if ($Verdict -eq 'WARN') { $script:warn++ }
        $color = if ($Verdict -eq 'PASS') { 'Green' } elseif ($Verdict -eq 'WARN') { 'Yellow' } else { 'Red' }
        Write-Host ('{0,-5} {1,-24} {2}' -f $Verdict,$Name,$Detail) -ForegroundColor $color
    }

    $cog = Get-Json "http://127.0.0.1:$($script:CogPort)/" 5
    if ($cog.ok) { Show 'PASS' 'Cognition UI' "http=$($cog.status)" } else { Show 'FAIL' 'Cognition UI' 'unreachable' }

    $retrieval = Get-Json "http://127.0.0.1:$($script:CogPort)/api/retrieval/health" 5
    if ($retrieval.ok -and $retrieval.body.retrieval) {
        if ($retrieval.body.retrieval.reachable -eq $true) { Show 'PASS' 'Cognition -> KE' 'retrieval proxy reachable' }
        else { Show 'WARN' 'Cognition -> KE' 'proxy serving with KE unavailable/fallback' }
    } else { Show 'WARN' 'Cognition -> KE' 'retrieval health unavailable' }

    $ke = Get-Json "http://127.0.0.1:$($script:KePort)/api/health" 8
    if (-not $ke.ok) { Show 'WARN' 'Knowledge Engine' 'unreachable; Cognition can still run' }
    elseif ($ke.body.status -eq 'ok') { Show 'PASS' 'Knowledge Engine' 'status=ok' }
    else { Show 'WARN' 'Knowledge Engine' "status=$($ke.body.status)" }

    $qd = Get-Json 'http://127.0.0.1:6333/readyz' 4
    if ($qd.ok) { Show 'PASS' 'Qdrant' 'ready' } else { Show 'WARN' 'Qdrant' 'unavailable; lexical/archives may still work' }

    if (Test-Path $script:TaskpackRoot) {
        $completed = @(Get-ChildItem (Join-Path $script:TaskpackRoot 'completed') -Directory -ErrorAction SilentlyContinue).Count
        $archive = @(Get-ChildItem (Join-Path $script:TaskpackRoot 'archive') -Directory -ErrorAction SilentlyContinue).Count
        Show 'PASS' 'TaskPack storage' "root=$($script:TaskpackRoot) completed=$completed archive=$archive"
    } else { Show 'WARN' 'TaskPack storage' "missing root=$($script:TaskpackRoot)" }

    if ($script:fail -gt 0) { Write-Host 'OVERALL: FAIL' -ForegroundColor Red; return 1 }
    if ($script:warn -gt 0) { Write-Host 'OVERALL: WARN' -ForegroundColor Yellow; return 0 }
    Write-Host 'OVERALL: PASS' -ForegroundColor Green
    return 0
}

function Copy-TreeFiltered([string]$Source, [string]$Destination, [string[]]$ExcludedNames) {
    if (-not (Test-Path $Source)) { return 0 }
    $count = 0
    Get-ChildItem -Path $Source -Recurse -Force | ForEach-Object {
        $rel = $_.FullName.Substring($Source.Length).TrimStart('\')
        if ($_.PSIsContainer) {
            if ($ExcludedNames -contains $_.Name) { return }
            New-Item -ItemType Directory -Force -Path (Join-Path $Destination $rel) | Out-Null
        } else {
            if ($ExcludedNames -contains $_.Name) { return }
            $dest = Join-Path $Destination $rel
            New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) | Out-Null
            Copy-Item $_.FullName $dest -Force
            $script:count++
        }
    }
    return $script:count
}

function Invoke-Backup {
    Ensure-Dirs
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $root = Join-Path $script:BackupRoot $stamp
    $cogDest = Join-Path $root 'cognition'
    $taskDest = Join-Path $root 'taskpacks'
    New-Item -ItemType Directory -Force -Path $cogDest,$taskDest | Out-Null

    $cognitionFiles = Copy-TreeFiltered $script:CognitionDataRoot $cogDest @('index.qlite','index.qlite-wal','index.qlite-shm','backups')

    $taskFiles = 0
    foreach ($name in @('completed','archive','failed')) {
        $src = Join-Path $script:TaskpackRoot $name
        if (Test-Path $src) {
            $dst = Join-Path $taskDest $name
            New-Item -ItemType Directory -Force -Path $dst | Out-Null
            $taskFiles += Copy-TreeFiltered $src $dst @()
        }
    }

    $goldenRuns = Join-Path $script:RepoRoot 'data\taskpack_golden\runs'
    if (Test-Path $goldenRuns) {
        $dst = Join-Path $root 'taskpack_runs'
        New-Item -ItemType Directory -Force -Path $dst | Out-Null
        $taskFiles += Copy-TreeFiltered $goldenRuns $dst @()
    }

    $files = @(Get-ChildItem $root -Recurse -File | ForEach-Object {
        [pscustomobject]@{
            path = $_.FullName.Substring($root.Length).TrimStart('\').Replace('\','/')
            size = $_.Length
            sha256 = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
        }
    })
    $manifest = [ordered]@{
        backup_id = $stamp
        created_at = (Get-Date).ToString('o')
        sources = @{
            cognition = $script:CognitionDataRoot
            taskpacks = $script:TaskpackRoot
        }
        policy = @{
            cognition = 'Tier1 formal Markdown; derived index excluded'
            taskpacks = 'Tier1B completed/archive/failed research artifacts; outbox/processing excluded'
            qdrant_sqlite = 'rebuildable; not primary backup'
        }
        counts = @{ cognition_files = $cognitionFiles; taskpack_files = $taskFiles; total_files = $files.Count }
        files = $files
    }
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 (Join-Path $root 'manifest.json')

    if ($VerifyBackup) {
        $bad = 0
        foreach ($f in $files) {
            $full = Join-Path $root $f.path.Replace('/','\')
            if (-not (Test-Path $full)) { $bad++; continue }
            $hash = (Get-FileHash $full -Algorithm SHA256).Hash.ToLower()
            if ($hash -ne $f.sha256) { $bad++ }
        }
        if ($bad -gt 0) { throw "backup verification failed: $bad file(s)" }
    }
    Write-IntegrationLog 'INFO' "backup completed: $root"
    Write-Host "Backup completed: $root" -ForegroundColor Green
}

switch ($Action) {
    'start'  { Invoke-Start; break }
    'stop'   { Invoke-Stop; break }
    'health' { $code = Invoke-Health; exit $code }
    'backup' { Invoke-Backup; break }
}
