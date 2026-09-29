<#
.SYNOPSIS
    Instala TickFence: dependencias, servicio de Windows y registro inicial.

.DESCRIPTION
    Hay que ejecutarlo UNA vez como Administrador. A partir de ahi, la app
    funciona sin permisos: el servicio corre como LocalSystem y es el que
    aplica los bloqueos.

.PARAMETER Token
    Token de TickTick (formato tp_...). Se guarda cifrado con DPAPI.

.PARAMETER Desinstalar
    Desinstala en vez de instalar. Lo usa el desinstalador de Inno Setup.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install.ps1
    powershell -ExecutionPolicy Bypass -File install.ps1 -Token "tp_..."
    powershell -ExecutionPolicy Bypass -File install.ps1 -Desinstalar
#>
[CmdletBinding()]
param(
    [string]$Token = "",
    [string]$Python = "python",
    [switch]$Desinstalar
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

# --------------------------------------------------------------- desinstalar
if ($Desinstalar) {
    Step "Desinstalando"
    Push-Location $root
    try {
        & $Python -m focuslock uninstall 2>&1 | ForEach-Object { Write-Host "    $_" }
    } finally { Pop-Location }
    Write-Host ""
    Write-Host "  Servicio, IFEO y accesos directos desinstalados." -ForegroundColor Green
    Write-Host "  Los datos quedan en C:\ProgramData\TickFence por si volves." -ForegroundColor Green
    exit 0
}

# --------------------------------------------------------------- admin check
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Este instalador necesita permisos de Administrador." -ForegroundColor Red
    Write-Host "Cierra PowerShell, clic derecho en PowerShell -> 'Ejecutar como administrador', y volve a correrlo."
    exit 1
}

Step "Entorno"

# La version minima se valida ACA y no en el instalador de Inno. Razon: este
# script es el camino de verdad, se lo puede correr a mano, y un chequeo en dos
# lugares termina divergiendo. Ademas el error sale con su mensaje y no
# tapado por el log del instalador.
$pyTexto = (& $Python -c "import sys; print(str(sys.version_info[0]) + '.' + str(sys.version_info[1]))" 2>&1)
$pyNumero = (& $Python -c "import sys; print(sys.version_info[0] * 100 + sys.version_info[1])" 2>&1)
if ($LASTEXITCODE -ne 0 -or -not ($pyNumero -match '^\d+$')) {
    Write-Host "No se pudo ejecutar Python. Revisá que esté en el PATH." -ForegroundColor Red
    Write-Host "    $pyTexto"
    exit 1
}
$pyVersion = [int]$pyNumero
if ($pyVersion -lt 311) {
    Write-Host "TickFence necesita Python 3.11 o superior y tenés $pyTexto." -ForegroundColor Red
    exit 1
}
Ok "Python $pyTexto"

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
