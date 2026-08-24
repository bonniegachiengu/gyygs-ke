# Restart a native service and PROVE it actually cycled.
#
# WHY THIS EXISTS -- a real incident, 24 Aug 2026:
#
#   Restart-Service Cloudflared-Myra -Force     # returned, no error shown
#   (Get-Service Cloudflared-Myra).Status       # "Running"
#   -> reported as "restarted successfully"
#
# Nothing had restarted. The session was not elevated, the service ACL grants
# start/stop only to SYSTEM and Administrators, and the resulting access-denied
# error was swallowed by $ErrorActionPreference='SilentlyContinue'. The service
# read "Running" because it had never stopped. An edited tunnel config sat
# unapplied for two hours while every check said it was fine.
#
# `Status -eq 'Running'` DOES NOT MEAN A RESTART HAPPENED. It only means
# something is running -- possibly the same process, with the old config still
# in memory. That distinction is the whole point of this script.
#
# A promote that silently does not reload is worse than no promote at all: the
# deploy looks green and the change is not live.
#
# Usage:
#   .\restart-verified.ps1 -ServiceName Cloudflared-Myra -ChildProcess cloudflared
#
# Exits non-zero if the child PID did not change. Never reports success on an
# unverified restart.

[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $ServiceName,
    [Parameter(Mandatory)] [string] $ChildProcess,
    [int] $TimeoutSeconds = 45
)

$ErrorActionPreference = 'Stop'   # deliberately NOT SilentlyContinue

function Child-Pids {
    # ONLY this service's own children.
    #
    # Matching every process of the name is wrong on this machine: there are
    # several python.exe (production API, staging API, Sustena API) and two
    # cloudflared.exe. The first run of this script reported a false FAIL
    # because unrelated pythons "survived" a restart they were never part of --
    # a check that cries wolf gets ignored, which is worse than no check.
    #
    # nssm is the service's process; the real worker is its child.
    $svc = Get-CimInstance Win32_Service -Filter "Name='$ServiceName'" -ErrorAction SilentlyContinue
    if (-not $svc -or -not $svc.ProcessId) { return @() }
    @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$($svc.ProcessId)" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq "$ChildProcess.exe" } |
        ForEach-Object { $_.ProcessId }) | Sort-Object
}

function Fail($msg) { Write-Host "FAIL: $msg" -ForegroundColor Red; exit 1 }

# ── 0. Can this session actually control the service?
#
# Deliberately NOT an "am I Administrator?" test. Once
# infra/grant-service-control.ps1 has run, an ordinary unelevated session CAN
# start and stop these services, and demanding elevation refuses a restart it
# is perfectly able to perform -- which is exactly what this script did the
# first time it was used after the grant landed.
#
# The honest question is "can I control it?", and the only truthful way to ask
# is to try. What must never happen is the failure being SWALLOWED, so the
# attempt runs with -ErrorAction Stop and the real message is surfaced.
$before = Child-Pids
Write-Host "before : $ChildProcess PIDs = $($before -join ',')"

try {
    Stop-Service $ServiceName -Force -ErrorAction Stop
}
catch {
    Write-Host "CANNOT CONTROL '$ServiceName':" -ForegroundColor Yellow
    Write-Host "  $($_.Exception.Message)"
    Write-Host "These services grant start/stop to SYSTEM and Administrators."
    Write-Host "Either run this in an Administrator PowerShell, or apply the"
    Write-Host "one-time grant in infra/grant-service-control.ps1."
    Fail "refusing to report a restart I could not perform"
}
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Service $ServiceName).Status -ne 'Stopped' -and (Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 500
}
if ((Get-Service $ServiceName).Status -ne 'Stopped') { Fail "$ServiceName did not reach Stopped" }

Start-Service $ServiceName
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Service $ServiceName).Status -ne 'Running' -and (Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 500
}
if ((Get-Service $ServiceName).Status -ne 'Running') { Fail "$ServiceName did not come back Running" }

# ── the actual proof: a NEW child process, not merely a Running status
Start-Sleep -Seconds 5
$after = Child-Pids
Write-Host "after  : $ChildProcess PIDs = $($after -join ',')"

$survivors = $before | Where-Object { $after -contains $_ }
if ($survivors) {
    Fail ("PID(s) $($survivors -join ',') survived the restart -- the process did NOT " +
          "cycle and is still running its OLD in-memory config. Do not treat this as deployed.")
}
if (-not $after) { Fail "no $ChildProcess process after start" }

Write-Host "OK: $ServiceName genuinely cycled (all child PIDs are new)." -ForegroundColor Green
exit 0
