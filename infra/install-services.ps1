# Installs the whole native stack as PROPER Windows Services. Run elevated.
#
# WHY: the 5-minute scheduled task that preceded this flashed a console window
# every single run. That is not fixable from the task side — Task Scheduler
# creates the console host before PowerShell can apply -WindowStyle Hidden.
# Windows Services run in session 0 with no console at all, so there is nothing
# to flash, ever. They also start at boot without anyone logging in, which the
# task could not do (AtLogOn registration needs elevation too).
#
# nssm wraps the console executables (nginx, uvicorn, cloudflared) so the SCM
# can start/stop/restart them properly — a bare `sc.exe create` on a console app
# fails its SCM handshake and Windows reports "did not respond in a timely
# fashion".
#
# Idempotent: an existing service of the same name is removed and recreated.

$ErrorActionPreference = 'Continue'
$nssm = 'C:\Users\DELL\bin\nssm.exe'
$log  = 'C:\Users\DELL\dev\gyygs.ke\logs\install-services.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
function Log($m) { $l = ('[{0:HH:mm:ss}] {1}' -f (Get-Date), $m); Write-Host $l; Add-Content $log $l }

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
        ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Log 'NOT ELEVATED — aborting.'; exit 1
}
Log '=== elevated OK ==='

$logs = 'C:\Users\DELL\dev\gyygs.ke\logs'

$services = @(
  @{ Name='Sustena-API';        Exe='C:\Users\DELL\AppData\Local\Programs\Python\Python311\python.exe';
     Args='-m uvicorn sustena.api.main:app --host 0.0.0.0 --port 9000';
     Dir='C:\Users\DELL\dev\sustena\apps\api';
     Desc='Sustena backend (serves sustena.vyybandasky.online via the vyyb-os tunnel)' },

  @{ Name='Myrah-API';           Exe='C:\Users\DELL\dev\gyygs.ke\.venv-native\Scripts\python.exe';
     Args='-m uvicorn app.main:app --host 127.0.0.1 --port 8010 --proxy-headers --forwarded-allow-ips=*';
     Dir='C:\Users\DELL\dev\gyygs.ke';
     Desc='Myrah quote API (SQLite lead store)' },

  @{ Name='Myrah-Nginx';         Exe='C:\nginx\nginx.exe';
     Args='-p C:\nginx -c C:\Users\DELL\dev\gyygs.ke\infra\nginx-windows.conf';
     Dir='C:\nginx';
     Desc='nginx — Myrah SPA :3000 and LaunchGear :8080' },

  @{ Name='Cloudflared-VyybOS'; Exe='C:\Users\DELL\.cloudflared\cloudflared.exe';
     Args='--config C:\Users\DELL\.cloudflared\config-vyyb-os.yml tunnel run';
     Dir='C:\Users\DELL\.cloudflared';
     Desc='Cloudflare tunnel vyyb-os — sustena.* and app.*' },

  @{ Name='Cloudflared-Myrah';   Exe='C:\Users\DELL\.cloudflared\cloudflared.exe';
     Args='--config C:\Users\DELL\.cloudflared\config-myra.yml tunnel run';
     Dir='C:\Users\DELL\.cloudflared';
     Desc='Cloudflare tunnel myra — myra.*, myracleaning.*, lg.*, launchgear.*' }
)

# ── 1. stop the hand-started processes so the services own the ports cleanly ──
Log '--- stopping manually-started processes ---'
Get-Process nginx, cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
foreach ($p in 8010, 9000) {
    @(Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}
Start-Sleep -Seconds 5

# ── 2. (re)create each service ──
foreach ($s in $services) {
    if (Get-Service $s.Name -ErrorAction SilentlyContinue) {
        Log ('removing existing service {0}' -f $s.Name)
        & $nssm stop   $s.Name confirm | Out-Null
        & $nssm remove $s.Name confirm | Out-Null
        Start-Sleep -Seconds 2
    }
    & $nssm install $s.Name $s.Exe $s.Args        | Out-Null
    & $nssm set $s.Name AppDirectory $s.Dir       | Out-Null
    & $nssm set $s.Name Description  $s.Desc      | Out-Null
    & $nssm set $s.Name Start SERVICE_DELAYED_AUTO_START | Out-Null
    # restart on crash, backing off so a hard-failing service cannot spin
    & $nssm set $s.Name AppExit Default Restart   | Out-Null
    & $nssm set $s.Name AppRestartDelay 5000      | Out-Null
    & $nssm set $s.Name AppStdout ('{0}\{1}.out.log' -f $logs, $s.Name) | Out-Null
    & $nssm set $s.Name AppStderr ('{0}\{1}.err.log' -f $logs, $s.Name) | Out-Null
    & $nssm set $s.Name AppRotateFiles 1          | Out-Null
    Log ('installed {0}' -f $s.Name)
}

# ── 3. start them, API/nginx before the tunnels so nothing fronts a dead port ──
foreach ($s in $services) {
    Start-Service $s.Name -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 4
    Log ('{0} -> {1}' -f $s.Name, (Get-Service $s.Name).Status)
}

# ── 4. retire the flashing task for good ──
foreach ($t in 'MyraNativeStackHeal', 'MyraNativeStack') {
    if (Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $t -Confirm:$false
        Log ('removed scheduled task {0}' -f $t)
    }
}

Start-Sleep -Seconds 12
Log '--- service states ---'
Get-Service Sustena-API, Myrah-API, Myrah-Nginx, Cloudflared-VyybOS, Cloudflared-Myrah |
    ForEach-Object { Log ('  {0,-20} {1,-8} {2}' -f $_.Name, $_.Status, $_.StartType) }

Log '--- hostname check ---'
foreach ($u in 'https://sustena.vyybandasky.online/health',
               'https://app.vyybandasky.online/',
               'https://myra.vyybandasky.online/',
               'https://myracleaning.vyybandasky.online/',
               'https://lg.vyybandasky.online/',
               'https://launchgear.vyybandasky.online/') {
    try   { Log ('  {0} -> {1}' -f $u, (Invoke-WebRequest $u -TimeoutSec 25 -UseBasicParsing).StatusCode) }
    catch { Log ('  {0} -> FAILED' -f $u) }
}
Log '=== INSTALL COMPLETE ==='
