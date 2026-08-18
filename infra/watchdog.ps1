<#
    Myra site watchdog.

    Checks the PUBLIC url, not a local process. That is deliberate: the failure
    VOS III hit in July was cloudflared alive-but-not-serving, which every
    process-level check reports as healthy. Only an end-to-end request through
    Cloudflare proves a customer can actually reach the site.

    Recovers from, in order of what it has actually seen:
      * Docker Desktop not running after a reboot (the 18 Aug 2026 outage:
        machine rebooted 04:38, Docker never started, Cloudflare served 1033
        until someone noticed)
      * engine up but containers down
      * containers up but the tunnel's edge connection dead

    Silent when healthy. Logs and notifies only when it had to intervene.

    Run by the "Myra site watchdog" scheduled task: at logon, then every 5 min.
#>
[CmdletBinding()]
param(
    # Run the recovery path even if the site looks healthy — for testing.
    [switch]$Force
)

$ErrorActionPreference = 'Continue'

$HealthUrl     = 'https://myra.vyybandasky.online/api/health'
$InfraDir      = $PSScriptRoot
$RepoRoot      = Split-Path -Parent $InfraDir
$ComposeFile   = Join-Path $InfraDir 'docker-compose.yml'
$Docker        = 'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
$DockerDesktop = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
$LogFile       = Join-Path $RepoRoot 'logs\watchdog.log'
$TopicFile     = Join-Path $InfraDir '.ntfy-topic'

function Write-Log([string]$Message) {
    $line = '{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null
    Add-Content -Path $LogFile -Value $line -Encoding utf8
    Write-Verbose $line
}

function Send-Notification([string]$Title, [string]$Body) {
    if (-not (Test-Path $TopicFile)) { return }
    $topic = (Get-Content $TopicFile -Raw).Trim()
    if (-not $topic) { return }
    try {
        Invoke-RestMethod -Uri "https://ntfy.sh/$topic" -Method Post -Body $Body `
            -Headers @{ Title = $Title } -TimeoutSec 15 | Out-Null
    } catch {
        Write-Log "ntfy failed: $($_.Exception.Message)"
    }
}

function Test-Site {
    try {
        $r = Invoke-WebRequest -Uri $HealthUrl -TimeoutSec 15 -UseBasicParsing
        return $r.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-Engine {
    if (-not (Test-Path $Docker)) { return $false }
    & $Docker info --format '{{.ServerVersion}}' *> $null
    return $LASTEXITCODE -eq 0
}

# ── 1. healthy? then do nothing, quietly ──────────────────────────────────
if ((Test-Site) -and -not $Force) { exit 0 }

Write-Log 'site unhealthy — starting recovery'

# ── 2. Docker Desktop ─────────────────────────────────────────────────────
if (-not (Get-Process 'Docker Desktop' -ErrorAction SilentlyContinue)) {
    if (Test-Path $DockerDesktop) {
        Write-Log 'Docker Desktop not running — starting it'
        Start-Process $DockerDesktop
    } else {
        Write-Log "Docker Desktop not found at $DockerDesktop"
        Send-Notification 'Myra is DOWN' "Docker Desktop is missing at $DockerDesktop. Manual fix needed."
        exit 1
    }
}

# ── 3. wait for the engine (a cold start takes a while) ───────────────────
$engineUp = $false
foreach ($i in 1..36) {
    if (Test-Engine) { $engineUp = $true; Write-Log "engine up after ~$($i*5)s"; break }
    Start-Sleep -Seconds 5
}
if (-not $engineUp) {
    Write-Log 'engine did not come up within 180s'
    Send-Notification 'Myra is DOWN' 'Docker engine did not start within 3 minutes. Needs a look.'
    exit 1
}

# ── 4. containers. restart:unless-stopped usually does this for us, but an
#       explicit up -d also covers a container that was stopped by hand. ───
Write-Log 'bringing the stack up'
& $Docker compose -f $ComposeFile up -d 2>&1 | ForEach-Object { Write-Log "  compose: $_" }

# ── 5. did it actually come back? ─────────────────────────────────────────
$recovered = $false
foreach ($i in 1..24) {
    if (Test-Site) { $recovered = $true; Write-Log "site healthy again after ~$($i*5)s"; break }
    Start-Sleep -Seconds 5
}

if ($recovered) {
    Send-Notification 'Myra recovered' 'myra.vyybandasky.online was down and the watchdog brought it back.'
    exit 0
}

Write-Log 'site still unhealthy after recovery attempt'
Send-Notification 'Myra is DOWN' 'The watchdog restarted everything and myra.vyybandasky.online is still unreachable. Needs a look.'
exit 1
