<#
    Registers (or re-registers) the "Myra site watchdog" scheduled task.

    Idempotent — safe to re-run. Run it once per machine, and again if the repo
    ever moves. Requires no admin rights: it is a per-user task, because Docker
    Desktop is a per-user GUI app and cannot run without a logged-on session.
#>
$ErrorActionPreference = 'Stop'

$TaskName = 'Myra site watchdog'
$Script   = Join-Path $PSScriptRoot 'watchdog.ps1'

if (-not (Test-Path $Script)) { throw "watchdog.ps1 not found next to this script ($Script)" }

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument (
    '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $Script
)

# At logon: covers the reboot case, which is the outage this was built for.
# Every 5 minutes: covers a mid-session crash, and the tunnel going dark while
# the container stays up — which no process-level check would ever notice.
#
# The repetition is bounded at 10 years rather than [TimeSpan]::MaxValue, which
# serialises to P99999999DT23H59M59S and Task Scheduler rejects as out of range.
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$pollTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$triggers = @($logonTrigger, $pollTrigger)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers `
    -Settings $settings -Principal $principal -Force `
    -Description 'Checks myra.vyybandasky.online end-to-end and, if it is unreachable, starts Docker Desktop and the compose stack. Silent when healthy.' | Out-Null

Write-Host "registered: $TaskName"
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State | Format-Table -AutoSize
