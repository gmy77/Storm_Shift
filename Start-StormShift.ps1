<#
.SYNOPSIS
    Avvia il bridge METEOHUB e il tunnel pubblico di StormShift.

.DESCRIPTION
    Le credenziali ARCO restano nel Windows Credential Manager. Docker non e'
    necessario per questa modalita': il server Python usa il vault locale e
    cloudflared pubblica solamente i dati radar gia' elaborati.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File C:\Users\gimmy\OneDrive\Desktop\Start-StormShift.ps1 -OpenBrowser
#>

[CmdletBinding()]
param(
    [switch]$OpenBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$desktop = Join-Path $env:USERPROFILE "OneDrive\Desktop"
$serverScript = Join-Path $desktop "stormshift_meteohub_server.py"
$tunnelConfig = Join-Path $env:USERPROFILE ".cloudflared\stormshift.yml"
$cloudflared = "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe"
$dashboardUrl = "https://stormshift.gimmycloud.net/"

function Test-LocalPort {
    param([int]$Port)

    return [bool](Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

if (-not (Test-Path -LiteralPath $serverScript)) {
    throw "Bridge StormShift non trovato: $serverScript"
}
if (-not (Test-Path -LiteralPath $tunnelConfig)) {
    throw "Configurazione tunnel non trovata: $tunnelConfig"
}
if (-not (Test-Path -LiteralPath $cloudflared)) {
    throw "cloudflared non trovato. Reinstalla Cloudflare Tunnel."
}

if (-not (Test-LocalPort -Port 8765)) {
    Start-Process -FilePath "C:\ph\satpy-env\Scripts\python.exe" -ArgumentList "`"$serverScript`"" -WindowStyle Hidden
    Write-Host "Bridge METEOHUB avviato." -ForegroundColor Green
} else {
    Write-Host "Bridge METEOHUB gia' attivo." -ForegroundColor DarkGreen
}

$tunnelActive = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*stormshift.yml*" }
if (-not $tunnelActive) {
    Start-Process -FilePath $cloudflared -ArgumentList "--config `"$tunnelConfig`" tunnel run" -WindowStyle Hidden
    Write-Host "Cloudflare Tunnel avviato." -ForegroundColor Green
} else {
    Write-Host "Cloudflare Tunnel gia' attivo." -ForegroundColor DarkGreen
}

for ($attempt = 1; $attempt -le 12; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/health" -TimeoutSec 5
        if ($health.status -eq "ok") {
            Write-Host "StormShift pronto: $dashboardUrl" -ForegroundColor Cyan
            if ($OpenBrowser) {
                Start-Process $dashboardUrl
            }
            exit 0
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}

throw "Il bridge non ha risposto entro 24 secondi. Controlla le credenziali METEOHUB e la connessione."

