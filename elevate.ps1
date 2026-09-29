<#
.SYNOPSIS
    Ejecuta un comando de TickFence con permisos de administrador.

.DESCRIPTION
    Se usa desde una sesion normal: relanza PowerShell con -Verb RunAs, lo que
    dispara el dialogo de UAC. Si el usuario cancela, devuelve 1223 (ERROR_CANCELLED)
    y no intenta nada mas.

    Ejecuta el instalador por defecto. Con -Comando se puede pasar cualquier
    subcomando de focuslock.

.EXAMPLE
    .\elevate.ps1
    .\elevate.ps1 -Comando doctor
    .\elevate.ps1 -Comando uninstall
#>
[CmdletBinding()]
param(
    [string]$Comando = "install",
    [string]$Token = "",
    [switch]$Espera   # espera a que termine y devuelve el codigo de salida
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$log = Join-Path $env:TEMP "tickfence-elevated.log"
$errLog = Join-Path $env:TEMP "tickfence-elevated.err"

# El token viaja por variable de entorno, no por linea de comandos: asi no queda
# en el historial de PowerShell ni en la lista de procesos.
if ($Token) { $env:TickFence_TOKEN = $Token }

$argList = @(
    "-NoProfile"
    "-ExecutionPolicy", "Bypass"
    "-Command", @"
`$ErrorActionPreference='Continue'
`$out = '$($log -replace "'", "''")'
`$err = '$($errLog -replace "'", "''")'
Set-Location -LiteralPath '$($root -replace "'", "''")'
`$fl = @('-m','focuslock','$Comando')
if (`$env:TickFence_TOKEN) { `$fl += @('--token', `$env:TickFence_TOKEN) }
# El proceso elevado escribe su propio log: -Verb RunAs no admite
# -RedirectStandardOutput (son conjuntos de parametros excluyentes).
& python @fl *> `$out
`$code = `$LASTEXITCODE
if (`$code -ne 0) { & python @fl 2> `$err | Out-Null }
exit `$code
"@
)

Write-Host "Se va a pedir permisos de administrador (UAC). Aceptá para continuar." -ForegroundColor Cyan
if ($Token) { Write-Host "El token se pasara por variable de entorno, no por linea de comandos." -ForegroundColor DarkGray }
Write-Host ""

Remove-Item $log, $errLog -ErrorAction SilentlyContinue

$proc = Start-Process -FilePath "powershell.exe" -ArgumentList $argList -Verb RunAs -PassThru -Wait
$code = $proc.ExitCode

if ($code -eq 1223) {
    Write-Host "Cancelaste la elevacion. No se instalo nada." -ForegroundColor Yellow
    exit 1223
}

Write-Host ""
Write-Host "--- salida del proceso elevado ---" -ForegroundColor Cyan
if (Test-Path $log) { Get-Content $log } else { Warn "No se genero el log." }
if (Test-Path $errLog) {
    $e = Get-Content $errLog
    if ($e) { Write-Host "--- errores ---" -ForegroundColor Yellow; $e }
}

Remove-Item Env:\TickFence_TOKEN -ErrorAction SilentlyContinue

if ($code -eq 0) {
    Write-Host ""
    Write-Host "Terminó bien." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Terminó con codigo $code" -ForegroundColor Red
}

exit $code
