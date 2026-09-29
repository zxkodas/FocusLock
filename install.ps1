<#
.SYNOPSIS
    Instala TickFence: dependencias, servicio de Windows y registro inicial.

.DESCRIPTION
    Hay que ejecutarlo UNA vez como Administrador. A partir de ahi, la app
    funciona sin permisos: el servicio corre como LocalSystem y es el que
    aplica los bloqueos.

.PARAMETER Token
    Token de TickTick (formato tp_...). Se guarda cifrado con DPAPI.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install.ps1
    powershell -ExecutionPolicy Bypass -File install.ps1 -Token "tp_..."
#>
[CmdletBinding()]
param(
    [string]$Token = "",
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

# --------------------------------------------------------------- admin check
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Este instalador necesita permisos de Administrador." -ForegroundColor Red
    Write-Host "Cierra PowerShell, clic derecho en PowerShell -> 'Ejecutar como administrador', y volve a correrlo."
    exit 1
}

Step "Entorno"
Ok "Python: $(& $Python --version 2>&1)"

# --------------------------------------------------------------- dependencias
Step "Instalando dependencias"
& $Python -m pip install --quiet --upgrade pip
& $Python -m pip install --quiet -r (Join-Path $root "requirements.txt")
Ok "Listo"

# --------------------------------------------------------------- servicio
Step "Instalando y arrancando el servicio de Windows"
$flArgs = @("-m", "focuslock", "install")
if ($Token) { $flArgs += @("--token", $Token) }
Push-Location $root
try {
    & $Python @flArgs
    if ($LASTEXITCODE -ne 0) { throw "La instalación del servicio falló (código $LASTEXITCODE)." }
} finally {
    Pop-Location
}

Step "Verificando que el servicio responda"
$flDoctor = & $Python -m focuslock doctor 2>&1
$flDoctor | ForEach-Object { Write-Host "    $_" }
if ($LASTEXITCODE -ne 0) {
    Warn "El servicio quedó instalado pero no responde. Guardalo para revisarlo."
    Warn "Detalle: $flDoctor"
}

# El servicio corre elevado y crea los archivos con ACL de solo lectura.
# Sin esto, la GUI no puede guardar la configuracion y falla con "Acceso denegado".
Step "Devolviendo la escritura de los archivos al usuario"
$flPerms = & $Python -m focuslock.permissions 2>&1
$flPerms | ForEach-Object { Write-Host "    $_" }
if ($LASTEXITCODE -ne 0) { Warn "No se pudieron ajustar los permisos: $flPerms" }

# --------------------------------------------------------------- resumen
Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  TickFence instalado" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1) Abrí la app (NO como administrador):"
Write-Host "     $Python -m focuslock gui"
Write-Host ""
Write-Host "2) En la pestaña Ajustes -> 'Extensión del navegador':"
Write-Host "     copiá la dirección."
Write-Host "   Chrome  : chrome://extensions -> Modo desarrollador -> Cargar descomprimida"
Write-Host "             -> carpeta '$root\extension\chrome'"
Write-Host "   Firefox : about:debugging#/runtime/this-firefox -> Cargar complemento temporal"
Write-Host "             -> '$root\extension\firefox\manifest.json'"
Write-Host "   Después abrí las opciones de la extensión y pegá la dirección."
Write-Host ""
Write-Host "3) Cargá el token de TickTick en Ajustes si no lo pasaste con -Token."
Write-Host ""
Write-Host "Para desinstalar:  $Python -m focuslock uninstall   (como administrador)"
Write-Host ""
