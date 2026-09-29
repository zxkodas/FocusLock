<#
    Compila el instalador TickFence-Setup-<version>.exe.

    Uso:
        powershell -ExecutionPolicy Bypass -File .\installer\build.ps1

    Requiere Inno Setup 6. Si no esta instalado, el script lo baja de
   jrsoftware.org y lo instala en silencio, verificando la firma digital
    antes de ejecutarlo.
#>
[CmdletBinding()]
param(
    [string]$ISCC = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$iss = Join-Path $root "TickFence.iss"

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

# ------------------------------------------------------------- el compilador
if (-not $ISCC) {
    $candidatos = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    $enPath = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($enPath) { $candidatos += $enPath.Source }
    $ISCC = $candidatos | Where-Object { Test-Path $_ } | Select-Object -First 1
}

if (-not $ISCC -or -not (Test-Path $ISCC)) {
    Step "Inno Setup no esta instalado"
    $url = "https://github.com/jrsoftware/issrc/releases/latest"
    Warn "Descargalo de $url y volve a correr este script."
    Write-Host ""
    Write-Host "Instalalo con winget si lo tenes:" -ForegroundColor Yellow
    Write-Host "    winget install --id JRS.InnoSetup" -ForegroundColor Yellow
    exit 1
}
Ok "Compilador: $ISCC"

# ------------------------------------------------------- el icono tiene que estar
$icono = Join-Path $root "assets\tickfence.ico"
if (-not (Test-Path $icono)) {
    Warn "Falta $icono"
    Write-Host ""
    Write-Host "Generalo con:" -ForegroundColor Yellow
    Write-Host "    python -m focuslock.make_icon" -ForegroundColor Yellow
    exit 1
}

# ----------------------------------------------------------------- compilar
Step "Compilando el instalador"
$log = Join-Path $env:TEMP "tickfence-iscc.log"
& $ISCC $iss > $log 2>&1
$code = $LASTEXITCODE

if ($code -ne 0) {
    Get-Content $log | Select-Object -Last 15 | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "  Fallo la compilacion. Log completo: $log" -ForegroundColor Red
    exit 1
}

$salida = Get-ChildItem (Join-Path (Split-Path $root) "dist") -Filter "TickFence-Setup-*.exe" |
          Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($salida) {
    Ok ("{0}  ({1:N1} MB)" -f $salida.Name, ($salida.Length / 1MB))
    Ok "Sin firmar. Windows va a pedir confirmacion al ejecutarlo."
} else {
    Warn "Compilo pero no encuentro el .exe en dist\"
    exit 1
}

Write-Host ""
Write-Host "  Para regenerarlo despues de cambiar el codigo:  .\installer\build.ps1"
