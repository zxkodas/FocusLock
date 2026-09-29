; Instalador de TickFence para Windows.
;
; Por que NO es un .exe congelado con Python adentro: el bloqueo dura porque
; Windows arranca un servicio real (pythonservice.exe) registrado en HKLM con
; pythonClassString. Un ejecutable de PyInstaller no puede ser ese servicio: al
; lanzarlo desde el SCM se desconecta y muere con error 1066. Por eso este
; instalador hace lo mismo que install.ps1: deja el codigo donde Python lo
; encuentra, registra el servicio de verdad y crea los accesos.

#define AppName "TickFence"
#define AppVersion "1.0.0"
#define AppPublisher "zxkodas"
#define AppURL "https://github.com/zxkodas/TickFence"

[Setup]
AppId={{7C4E9A21-3B5D-4F18-9E62-1D8A3F5B7C90}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
DefaultDirName={autopf}\TickFence
DefaultGroupName=TickFence
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=TickFence-Setup-{#AppVersion}
SetupIconFile=assets\tickfence.ico
UninstallDisplayIcon={app}\tickfence.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
MinVersion=10.0
PrivilegesRequired=admin

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "..\focuslock\*"; DestDir: "{app}\focuslock"; \
  Excludes: "__pycache__\*,*.pyc"; Flags: recursesubdirs ignoreversion
Source: "..\extension\*"; DestDir: "{app}\extension"; \
  Excludes: "__pycache__\*,*.pyc"; Flags: recursesubdirs ignoreversion
Source: "assets\tickfence.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\pyproject.toml"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\install.ps1"; DestDir: "{app}"; Flags: ignoreversion

; La licencia viaja con el programa: es GPL y hay que distribuirla.
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Run]
; No hay entradas con postinstall a proposito. El orden entre las entradas de
; [Run] y CurStepChanged(ssPostInstall) no esta garantizado, y abrir la ventana
; antes de que el servicio este configurado muestra una app que no bloquea
; nada. El arranque de la ventana se hace desde el codigo, al final.

[UninstallRun]
; El log va a {tmp}, no a {app}: Inno borra {app} al desinstalar y ahi el log
; ya no existiria. Tampoco a {userappdata}: con PrivilegesRequired=admin la
; instalacion corre en la cuenta de Administrador y no en la del usuario.
Filename: "cmd.exe"; RunOnceId: "TickFenceDesinstalar"; \
  Parameters: "/c powershell -NoProfile -ExecutionPolicy Bypass -File ""{app}\install.ps1"" -Desinstalar > ""{tmp}\tickfence-uninstall.log"" 2>&1"; \
  WorkingDir: "{app}"; Flags: runhidden waituntilterminated

[Code]
{ El preprocesador de Inno toma como directiva toda linea que arranca con '#',
  asi que un #13#10 al comienzo de una continuacion rompe la compilacion. Por
  eso el salto de linea va en una constante con nombre. }
const
  CR = #13#10;

{ ---------------------------------------------------------------- helpers }

{ Solo se comprueba que Python responda. La version minima la valida
  install.ps1, que es el camino de verdad: se lo puede correr a mano y ahi el
  error sale con su mensaje, no tapado por el log del instalador. Un chequeo
  en dos lugares termina divergiendo. }
function HayPython(): Boolean;
var
  Codigo: Integer;
begin
  Result := Exec(ExpandConstant('{sys}\cmd.exe'), '/c python --version',
                 '', SW_HIDE, ewWaitUntilTerminated, Codigo) and (Codigo = 0);
end;

{ ------------------------------------------------------------ instalacion }

(* Corre install.ps1 y devuelve su codigo de salida.

   Va desde el codigo y no desde [Run] a proposito: [Run] no expone el codigo
   de salida, asi que un fallo de la instalacion pasaria desapercibido. Con Exec
   lo tenemos, y el log queda en la carpeta de instalacion para leer el detalle.

   Los comentarios van con parentesis y no con llaves porque las llaves no
   anidan: escribir la ruta de {app} adentro cerraria el comentario antes de
   tiempo y el error aparece dos lineas mas abajo, donde no se busca. *)
function CorrerInstalacion(): Integer;
var
  Codigo: Integer;
  Comando: String;
begin
  Comando := '/c powershell -NoProfile -ExecutionPolicy Bypass -File "';
  Comando := Comando + ExpandConstant('{app}\install.ps1');
  Comando := Comando + '" > "' + ExpandConstant('{app}\install.log') + '" 2>&1';
  Codigo := -1;
  Exec(ExpandConstant('{sys}\cmd.exe'), Comando, ExpandConstant('{app}'),
       SW_HIDE, ewWaitUntilTerminated, Codigo);
  Result := Codigo;
end;

(* pythonw del PATH, no {app}\pythonw.exe: Python no se instala dentro de {app},
   vive en el sistema. *)
procedure AbrirLaApp;
var
  Codigo: Integer;
begin
  ShellExec('open', 'pythonw', '-m focuslock gui', ExpandConstant('{app}'),
            SW_SHOWNORMAL, ewNoWait, Codigo);
end;

(* En Inno Setup 6.7 esto es un 'procedure'. La documentacion muestra
   'function ... : Boolean' y con esa forma el compilador responde
   "Invalid prototype for 'CurStepChanged'", sin explicar por que. *)
procedure CurStepChanged(CurStep: TSetupStep);
var
  Codigo: Integer;
begin
  if CurStep <> ssPostInstall then
    Exit;

  Codigo := CorrerInstalacion();
  if Codigo <> 0 then
  begin
    (* La app quedo copiada pero el servicio no esta. Decirlo es la diferencia
       entre "no funciona" y "se que falta y donde mirar". *)
    MsgBox('Los archivos de TickFence quedaron instalados, pero la configuracion fallo.' + CR + CR +
           'Codigo de salida: ' + IntToStr(Codigo) + CR +
           'Detalle en:' + CR + ExpandConstant('{app}\install.log') + CR + CR +
           'El servicio de Windows es el que aplica el bloqueo. Sin el, los ' +
           'programas bloqueados abren igual.',
           mbError, MB_OK);
    Exit;
  end;

  (* recien ahora se abre la ventana: el servicio ya esta. *)
  AbrirLaApp;
end;

{ ------------------------------------------------------------------ entrada }

{ Python tiene que estar antes de tocar nada: el servicio y el IFEO dependen de
  el. Sin esto el instalador "terminaria bien" y la app no bloquearia nada:
  el error se veria recien cuando se abre un programa bloqueado. }
function InitializeSetup(): Boolean;
var
  Codigo: Integer;
begin
  Result := True;
  if HayPython() then
    Exit;

  if MsgBox('TickFence necesita Python 3.11 o superior y no lo encuentra.' + CR +
             CR + 'Instalalo desde python.org y volve a abrir este instalador.' + CR +
             CR + 'Queres que abra el sitio de descargas ahora?',
             mbConfirmation, MB_YESNO) = IDYES then
    ShellExec('open', 'https://www.python.org/downloads/windows/',
              '', '', SW_SHOWNORMAL, ewNoWait, Codigo);
  Result := False;
end;
