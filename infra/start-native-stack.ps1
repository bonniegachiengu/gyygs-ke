# Starts the whole native (no-Docker) stack. Idempotent: every component is
# checked before starting, so running this twice is safe and it doubles as a
# repair script, not just a boot script.
#
# Replaces what `docker compose up -d` used to do, plus the two cloudflared
# connectors that used to live in Docker and WSL respectively.
#
#   :8010  Myrah API      (uvicorn, venv, LEAD_STORE=sqlite)
#   :3000  nginx         Myrah SPA + /api proxy
#   :8080  nginx         LaunchGear static
#          cloudflared   vyyb-os tunnel -> sustena.* + app.*
#          cloudflared   myra tunnel    -> myra.* + myracleaning.* + lg.* + launchgear.*
#
# NOTE: cloudflared is NOT installed as a Windows service because creating one
# needs elevation. Registered as a scheduled task instead — same pattern the
# SustenaKeepalive task already uses on this machine.

$ErrorActionPreference = 'SilentlyContinue'
$repo = 'C:\Users\DELL\dev\gyygs.ke'
$cf   = 'C:\Users\DELL\.cloudflared\cloudflared.exe'
$logs = 'C:\Users\DELL\dev\gyygs.ke\logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null

function Test-Port($p) { @(Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue).Count -gt 0 }
function Log($m) { $line = ('[{0:yyyy-MM-dd HH:mm:ss}] {1}' -f (Get-Date), $m); Write-Host $line; Add-Content -Path "$logs\native-stack.log" -Value $line }

# ── 1. Myrah API ──
if (Test-Port 8010) { Log 'API   : already listening on 8010' }
else {
  Start-Process -FilePath "$repo\.venv-native\Scripts\python.exe" `
    -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8010','--proxy-headers','--forwarded-allow-ips=*' `
    -WorkingDirectory $repo `
    -RedirectStandardOutput "$logs\myra-api.out" -RedirectStandardError "$logs\myra-api.err" -WindowStyle Hidden
  Start-Sleep -Seconds 8
  Log ('API   : started -> listening={0}' -f (Test-Port 8010))
}

# ── 2. nginx (serves BOTH 3000 and 8080 from one instance) ──
if (Test-Port 3000) { Log 'NGINX : already listening on 3000' }
else {
  Start-Process -FilePath 'C:\nginx\nginx.exe' -ArgumentList '-p','C:\nginx','-c',"$repo\infra\nginx-windows.conf" -WindowStyle Hidden
  Start-Sleep -Seconds 4
  Log ('NGINX : started -> 3000={0} 8080={1}' -f (Test-Port 3000), (Test-Port 8080))
}

# ── 3. cloudflared connectors ──
# Matched on the config filename so the two tunnels are told apart correctly —
# process name alone cannot distinguish them.
foreach ($t in @(
  @{ Name='vyyb-os'; Cfg='C:\Users\DELL\.cloudflared\config-vyyb-os.yml' },
  @{ Name='myra';    Cfg='C:\Users\DELL\.cloudflared\config-myra.yml'    }
)) {
  $running = @(Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" |
               Where-Object { $_.CommandLine -like "*$($t.Cfg)*" }).Count -gt 0
  if ($running) { Log ('TUNNEL: {0} already running' -f $t.Name) }
  else {
    Start-Process -FilePath $cf -ArgumentList '--config',$t.Cfg,'tunnel','run' `
      -RedirectStandardOutput "$logs\cf-$($t.Name).out" -RedirectStandardError "$logs\cf-$($t.Name).err" -WindowStyle Hidden
    Start-Sleep -Seconds 12
    Log ('TUNNEL: {0} started' -f $t.Name)
  }
}

Log 'native stack check complete'
