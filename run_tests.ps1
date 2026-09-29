<#
.SYNOPSIS
    Corre todas las pruebas de TickFence.

.DESCRIPTION
    Lanza cada suite en un proceso propio y muestra un resumen. Separar los
    procesos evita que un test que deja estado global (parches, singletons de
    Qt, variables de sesion) contamine al siguiente.

    test_guard y test_ui matan procesos y crean ventanas reales de forma
    controlada, pero ninguno toca explorer.exe ni OpenCode.exe: esa garantia
    esta en rules.NEVER_BLOCK y hay tests que la verifican.

    Sin argumentos corren las 10 suites. -Quick deja afuera test_guard, que es
    la unica que tarda de verdad.
#>
[CmdletBinding()]
param(
    [string]$Python = "python",
    [switch]$Quick   # omite test_guard, que es el que tarda
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $root

# Las 10 suites. Cada una va en su propio proceso (ver .DESCRIPTION).
$suites = @(
    "tests.test_focuslock"
    "tests.test_win32"
    "tests.test_imports"
    "tests.test_ifeo"
    "tests.test_stub"
    "tests.test_ui"
    "tests.test_extension"
    "tests.test_installer"
    "tests.test_i18n"
)
if (-not $Quick) { $suites += "tests.test_guard" }

$failed = @()

foreach ($suite in $suites) {
    Write-Host "==> $suite" -ForegroundColor Cyan
    $out = & $Python -m $suite 2>&1
    $code = $LASTEXITCODE

    $line = $out | Select-String -Pattern "^(Ran |OK$|FAILED)" | Select-Object -Last 2
    $line | ForEach-Object { Write-Host "    $_" }

    # Detalle de los fallos, si hubo.
    $out | Select-String -Pattern "^(FAIL|ERROR):" | ForEach-Object {
        Write-Host "    $($_.Line)" -ForegroundColor Red
    }

    if ($code -ne 0) { $failed += $suite }
    Write-Host ""
}

Pop-Location

if ($failed.Count -eq 0) {
    Write-Host "Todas las suites pasan." -ForegroundColor Green
    exit 0
}

Write-Host "Fallaron: $($failed -join ', ')" -ForegroundColor Red
exit 1
