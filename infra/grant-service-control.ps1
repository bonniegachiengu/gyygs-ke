# ONE-TIME, RUN ELEVATED ONCE.
#
# Grants this machine's interactive user the right to START and STOP the five
# native Myrah/Sustena services -- and nothing else.
#
# WHY: by default these services grant start/stop to SYSTEM and Administrators
# only. Interactive users get query rights alone, so an unelevated
# `Restart-Service` fails with "Cannot open <service> service on computer '.'".
# On 24 Aug that error was swallowed, `Status` still read "Running", and an
# edited tunnel config sat unapplied for two hours while every check looked
# green. The deploy/promote path cannot depend on a step that fails silently.
#
# After this runs once, deploy and promote scripts can cycle services without
# elevation, and infra/restart-verified.ps1 can PROVE the cycle happened.
#
# WHAT IT CHANGES, precisely: it adds RP (start), WP (stop) and DT
# (pause/continue) to the Interactive Users (IU) entry in each service's
# security descriptor. It does not touch service binaries, accounts, or any
# other service on this machine.
#
# THE TRADE-OFF, stated plainly: any interactive logon session on this machine
# will be able to start/stop these five services. On a single-user development
# laptop that is the intended outcome. On a shared machine, replace `IU` below
# with a specific account SID instead.

#Requires -RunAsAdministrator

$ErrorActionPreference = 'Stop'

$services = @(
    'Cloudflared-Myra',
    'Cloudflared-VyybOS',
    'Myra-API',
    'Myra-Nginx',
    'Sustena-API'
)

# CC LC SW RP WP DT LO CR RC -- query/enumerate/start/stop/pause/interrogate.
# Deliberately WITHOUT: SD (delete), WD (change ACL), WO (change owner).
$IU_ALLOW = '(A;;CCLCSWRPWPDTLOCRRC;;;IU)'

foreach ($svc in $services) {
    $sddl = (& sc.exe sdshow $svc) -join '' -replace '\s', ''
    if (-not $sddl.StartsWith('D:')) { Write-Host "SKIP $svc (could not read SDDL)"; continue }

    if ($sddl -match '\(A;;CCLCSWRPWPDTLOCRRC;;;IU\)') {
        Write-Host "already granted: $svc"
        continue
    }

    # Replace the existing query-only IU entry if present, else append one.
    if ($sddl -match '\(A;;[^)]*;;;IU\)') {
        $new = $sddl -replace '\(A;;[^)]*;;;IU\)', $IU_ALLOW
    } else {
        # Append before any SACL section (S:), otherwise at the end.
        $new = if ($sddl -match '^(D:.*?)(S:.*)$') { $Matches[1] + $IU_ALLOW + $Matches[2] }
               else { $sddl + $IU_ALLOW }
    }

    & sc.exe sdset $svc $new | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Host "granted: $svc" }
    else { Write-Host "FAILED : $svc (sc.exe exit $LASTEXITCODE)" -ForegroundColor Red }
}

Write-Host ""
Write-Host "Verify (from a NORMAL, non-elevated PowerShell):"
Write-Host "  .\infra\restart-verified.ps1 -ServiceName Cloudflared-Myra -ChildProcess cloudflared"
