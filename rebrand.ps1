# Rebrandeo: desinstalar FocusLockSvc e instalar TickFenceSvc.
#
# El servicio esta corriendo con el nombre viejo. Windows no permite renombrar
# un servicio: hay que desinstalarlo y registrar el nuevo. Por eso esto
# necesita Administrador y por eso te lo dejo como archivo para correrlo vos.
#
# Tus datos NO se tocan: config.json y state.json ya estan en
# C:\ProgramData\TickFence con el token y los creditos.

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Paso($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Aviso($msg){ Write-Host "    $msg" -ForegroundColor Yellow }

$admin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Write-Host "Necesita Administrador. Cierra esto, click derecho en" -ForegroundColor Red
    Write-Host "PowerShell -> 'Ejecutar como administrador', y volve a correr:" -ForegroundColor Red
    Write-Host "    .\rebrand.ps1" -ForegroundColor Red
    exit 1
}

Paso "Desinstalando el servicio viejo (FocusLockSvc)"
& python -m focuslock uninstall 2>&1 | ForEach-Object { "    $_" }
Ok "Servicio viejo desinstalado"

Paso "Instalando TickFenceSvc"
Push-Location $root
try {
    & python -m focuslock install
    if ($LASTEXITCODE -ne 0) {
        Aviso "La instalacion fallo. Corre: .\install.ps1"
    } else {
        Ok "Servicio nuevo instalado"
    }
} finally { Pop-Location }

Paso "Permisos de escritura para tu usuario"
& python -m focuslock.permissions 2>&1 | ForEach-Object { "    $_" }

Paso "Verificacion"
Start-Sleep -Seconds 4
$svc = Get-Service -Name "TickFenceSvc" -ErrorAction SilentlyContinue
if ($svc) {
    Ok "TickFenceSvc -> $($svc.Status)"
} else {
    Aviso "TickFenceSvc no aparece. Corre: python -m focuslock doctor"
}
$viejo = Get-Service -Name "FocusLockSvc" -ErrorAction SilentlyContinue
if ($viejo) { Aviso "FocusLockSvc todavia existe: $($viejo.Status)" }
else { Ok "FocusLockSvc ya no esta" }

Write-Host ""
Write-Host "Listo. Abrí la app con:" -ForegroundColor Green
Write-Host "    python -m focuslock gui" -ForegroundColor Green
