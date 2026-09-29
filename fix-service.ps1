# El uninstall de TickFence limpia TickFenceSvc, no FocusLockSvc: el servicio
# viejo quedo vivo, toma pythonservice.exe y el puerto 47821, y el nuevo muere
# al arrancar. Esto para el viejo a mano y arranca el nuevo.
#
# Corre esto como Administrador.

$ErrorActionPreference = "Continue"
function Paso($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "    $m" -ForegroundColor Green }
function Av($m)   { Write-Host "    $m" -ForegroundColor Yellow }

$admin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Write-Host "Necesita Administrador. Cierra esto, PowerShell como" -ForegroundColor Red
    Write-Host "Administrador, y corre de nuevo: .\fix-service.ps1" -ForegroundColor Red
    exit 1
}

Paso "Parando y borrando el servicio viejo (FocusLockSvc)"
$sc = "$env:SystemRoot\System32\sc.exe"
& $sc stop FocusLockSvc 2>&1 | Out-Null
Start-Sleep -Seconds 4
& $sc delete FocusLockSvc 2>&1 | ForEach-Object { "    $_" }
Start-Sleep -Seconds 2

if (Get-Service -Name "FocusLockSvc" -ErrorAction SilentlyContinue) {
    Av "FocusLockSvc todavia esta. Borro a la fuerza en el siguiente paso."
} else {
    Ok "FocusLockSvc borrado"
}

Paso "Verifico que el puerto 47821 quedo libre"
$puerto = Get-NetTCPConnection -LocalPort 47821 -State Listen -ErrorAction SilentlyContinue
if ($puerto) {
    Av " todavia lo tiene pid $($puerto.OwningProcess). Lo mato."
    Stop-Process -Id $puerto.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
}
if (Get-NetTCPConnection -LocalPort 47821 -State Listen -ErrorAction SilentlyContinue) {
    Av "el puerto sigue ocupado: cerra TickFence si la tenes abierta y repeti"
} else {
    Ok "puerto 47821 libre"
}

Paso "Borro TickFenceSvc para reinstalarlo limpio"
& $sc stop TickFenceSvc 2>&1 | Out-Null
Start-Sleep -Seconds 2
& $sc delete TickFenceSvc 2>&1 | ForEach-Object { "    $_" }
Start-Sleep -Seconds 2

Paso "Instalo TickFenceSvc"
Push-Location $PSScriptRoot
try {
    & python -m focuslock install
} finally { Pop-Location }

Paso "Verificacion"
Start-Sleep -Seconds 5
foreach ($n in @("FocusLockSvc", "TickFenceSvc")) {
    $s = Get-Service -Name $n -ErrorAction SilentlyContinue
    if ($s) { Write-Host ("    {0,-14} {1}" -f $s.Name, $s.Status) -ForegroundColor Yellow }
    else { Ok "$n no esta" }
}
$t = Get-Service -Name "TickFenceSvc" -ErrorAction SilentlyContinue
if ($t -and $t.Status -eq "Running") {
    Ok "TickFenceSvc CORRIENDO"
    Write-Host ""
    Write-Host "Probalo:" -ForegroundColor Green
    Write-Host "    python -m focuslock gui" -ForegroundColor Green
} else {
    Av "TickFenceSvc no quedo corriendo. Corré: python -m focuslock doctor"
}
