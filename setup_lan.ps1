# Setup LAN access — abre puerto 8000 en el Firewall de Windows.
# EJECUTAR COMO ADMINISTRADOR (click derecho → Run with PowerShell, o desde una terminal admin).

Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Demo Company Chat — Setup acceso LAN" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════`n" -ForegroundColor Cyan

# Verificar admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
if (-not $isAdmin) {
    Write-Host "❌ Necesitás ejecutar este script como ADMINISTRADOR." -ForegroundColor Red
    Write-Host "   Click derecho sobre el archivo → 'Run with PowerShell' (admin)`n" -ForegroundColor Yellow
    Pause
    exit 1
}

# 1. Detectar IP LAN
Write-Host "1. Detectando IP local..." -ForegroundColor Yellow
$lanIPs = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.PrefixOrigin -in @("Dhcp","Manual") -and
        $_.IPAddress -notlike "169.*" -and
        $_.IPAddress -ne "127.0.0.1" -and
        $_.InterfaceAlias -notlike "*Loopback*" -and
        $_.InterfaceAlias -notlike "*VPN*"
    }

if (-not $lanIPs) {
    Write-Host "   ❌ No detecté ninguna IP LAN. ¿Estás conectado a la red?" -ForegroundColor Red
    Pause; exit 1
}

foreach ($ip in $lanIPs) {
    Write-Host "   → $($ip.IPAddress) ($($ip.InterfaceAlias))" -ForegroundColor Green
}

$primary = $lanIPs[0].IPAddress
Write-Host "`n   IP principal: $primary" -ForegroundColor Green

# 2. Firewall
Write-Host "`n2. Configurando Firewall (puerto 8000)..." -ForegroundColor Yellow
try {
    Get-NetFirewallRule -DisplayName "Demo Company Chat" -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
    New-NetFirewallRule `
        -DisplayName "Demo Company Chat" `
        -Description "Acceso LAN al chatbot Demo Company - puerto 8000" `
        -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow `
        -Profile Private,Domain `
        -ErrorAction Stop | Out-Null
    Write-Host "   ✓ Regla creada para perfiles Private y Domain" -ForegroundColor Green
} catch {
    Write-Host "   ❌ Error: $_" -ForegroundColor Red
    Pause; exit 1
}

# 3. Resumen
Write-Host "`n═══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  ✓ Setup completo" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════`n" -ForegroundColor Cyan
Write-Host "Las otras PCs de la red pueden acceder en:" -ForegroundColor White
Write-Host "  http://${primary}:8000" -ForegroundColor Cyan
Write-Host "`nDesde esta misma PC podés usar:" -ForegroundColor White
Write-Host "  http://localhost:8000" -ForegroundColor Cyan
Write-Host "`n⚠️  Recordá: el server tiene que estar corriendo (start_server.bat)" -ForegroundColor Yellow
Write-Host ""
Pause
