# FocusLock

Bloqueador de foco para Windows. Te deja la PC y el navegador clavados hasta
que completing **2 Lecturas** de tu proyecto de estudios en TickTick.

El desbloqueo de emergencia existe, pero hay que **escribir 300 palabras y
estar 5 minutos Tecleando** para pasarlo. Queda registrado con fecha y texto,
para releerlo la próxima vez que te agarre la tentación.

---

## Cómo funciona

```
┌─ Tu sesión normal (sin permisos) ──────────────┐
│   FocusLock.exe (GUI)  ──pipe──┐                │
│   Extensión Chrome/Firefox ────┤                │
└────────────────────────────────┼────────────────┘
                                 ▼
┌─ Servicio de Windows (LocalSystem, autoarranque) ┐
│  · lee TickTick y acredita Lecturas               │
│  · aplica/quita claves IFEO en HKLM               │
│  · vigilante de procesos cada 0.8 s               │
│  · servidor HTTP local para las extensiones       │
└───────────────────────────────────────────────────┘
```

El servicio es el dueño real del bloqueo. La GUI solo le pide cosas por un named
pipe, así que **funciona sin permisos de administrador**. Solo la instalación
inicial necesita elevación, y es una sola vez.

#> **Antes de nada: procesos que FocusLock nunca va a matar.** Están en
> `rules.NEVER_BLOCK` y no se pueden desactivar desde la configuración, ni
> siquiera con confirmación explícita. Incluye `explorer.exe` (el shell de
> Windows: si muere se te cae el escritorio entero), `userinit.exe`, el núcleo
> de sesión (`lsass`, `csrss`, `winlogon`, `services`), antivirus, y
> `OpenCode.exe`. Editar la lista de bloqueados no los alcanza: la regla misma
> devuelve False para esos nombres.
>
> `explorer.exe` **no va** en la lista de permitidos a propósito. Esa lista la
> podés editar vos; `NEVER_BLOCK` no. Si estuviera solo en permitidos, un día
> la sacás por error y perdés el acceso igual.

## Las tres capas de bloqueo

| Capa | Qué hace | Se esquiva… |
|---|---|---|
| **IFEO** | Windows ni siquiera arranca el programa: lo sustituye por un aviso | Necesitás admin para borrar las claves de `HKLM` |
| **Vigilante** | Detecta en 0.8 s y mata el proceso si Somehow arrancó | Kill manual desde el Administrador de tareas |
| **Extensión** | Bloquea dominios y cierra pestañas ya abiertas | Desactivar la extensión (sí, podés) |

La extensión es la capa más débil y es deliberado: no tenés forma de bloquear
una extensión desde otro proceso sinque el usuario lo note. El IFEO es la que
aguanta.

### Por qué el IFEO es la capa que importa

`HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution
Options\<programa>.exe` con un valor `Debugger` hace que Windows **no ejecute**
el programa: ejecuta el debugger en su lugar. El programa bloqueado no llega a
cargar ni a pintar una ventana.

Y como vive en `HKLM`, un usuario normal no lo puede tocar. Se necesita
elevación para desarmarlo, que es justo el punto: la tentación no debería
bastar con abrir una consola.

---

## Instalación

Abrí PowerShell **como Administrador** en esta carpeta:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

Eso instala dependencias, registra el servicio de Windows, lo arranca y
verifica que responda. Para dejar el token configurado de una:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1 -Token "tp_..."
```

Después, **sin permisos**, abrís la app:

```powershell
python -m focuslock gui
```

Para desinstalar (como Administrador):

```powershell
python -m focuslock uninstall
```

---

## Configurar las extensiones del navegador

Las extensiones converse con el servicio por HTTP en `127.0.0.1`. La
dirección incluye un token aleatorio, así que no se puede adivinar ni usar
desde otro lado.

**Chrome / Edge / Brave** (Chromium, Manifest V3)

1. `chrome://extensions` → activá **Modo de desarrollador**
2. **Cargar descomprimida** → elegí `extension/chrome`
3. Abrí las opciones de la extensión, pegá la dirección que muestra
   FocusLock en *Ajustes → Extensión del navegador* y guardá

**Firefox** (Manifest V3 con event pages)

1. `about:debugging#/runtime/this-firefox` → **Cargar complemento temporal**
2. Elegí `extension/firefox/manifest.json`
3. Mismo paso: pegá la dirección en las opciones

Ambas extensiones son *fail-open*: si el servicio no responde, no bloquean nada
por su cuenta. El bloqueo real lo sostiene Windows.

---

## Los otros comandos

```powershell
python -m focuslock status    # estado en una línea
python -m focuslock doctor    # diagnóstico: servicio, IFEO, TickTick, vigilante
python -m focuslock console   # motor en primer plano, CON EL VIGILANTE APAGADO
```

`doctor` es el primero que conviene correr si algo no se comporta.

### Por qué `console` no arma el vigilante

`console` corre el motor **en tu sesión de escritorio**, no como servicio. Si
el vigilante de procesos se levantara ahí, mataría programas de la sesión que
estás usando — incluido el escritorio. Por eso viene apagado y hay que pedirlo
a propósito:

```powershell
python -m focuslock console --armar-guard
```

Como servicio (`install`), el vigilante sí va armado, que es lo que tiene que
hacer. La diferencia es dónde corre: en `LocalSystem`, no en tu escritorio.

---

## Cómo se决定 el desbloqueo

El proyecto de TickTick se busca **por nombre** en cada consulta, no por ID
guardado. Si lo renombrás o lo recreás, la app lo sigue sin intervención. El
emoji que TickTick le pone (`📖Estudios`) se ignora al comparar.

Solo cuentan las tareas cuyo **título empieza con** el prefijo configurado
(por defecto `Lectura`). `TP 1`, `Parcial 2` y `Modulo 4` no cuentan nunca.

El crédito se otorga por **transición**: una tarea que la app ya vio
pendiente y después aparece completada. Dos casos que esto evita:

- Instalar la app con 20 Lecturas viejas ya marcadas no te desbloquea nada.
  La primera pasada siembra la línea base sin acreditar.
- Si la API devuelve una lista truncada y una tarea reaparece ya completada,
  no se cuenta como nueva.

Solo se acredita lo que vosmarks en TickTick. **No hay botón de "marcar como
hecha" en FocusLock**, a propósito: sería un atajo que anula el sentido de la
app.

Los créditos no se pierden: si completás una Lectura y después reiniciás la PC,
sigue contando.

---

## La emergencia

Para desbloquear sin tareas hay que:

1. Escribir **300 palabras** en el compromiso.
2. **5 minutos** de escritura real, medidos entre la primera y la última
   pulsación. Cerrar y reabrir el diálogo **no** reinicia el cronómetro.
3. Responder tres preguntas de reflexión, 30 palabras cada una.

La app mide pulsaciones de teclado, no solo caracteres, así que pegar un texto
largo desde el portapapeles no sirve: el ratio de caracteres por pulsación se
dispara y lo rechaza. Tampoco vale con dejar el texto escrito y esperar, porque
el tiempo se cuenta entre pulsaciones.

Si pasa, desbloquea por el tiempo configurado (20 minutos por defecto) y queda
registrado el texto completo en la pestaña **Bitácora**, con fecha y palabras.

Al expirar, se vuelve a bloquear solo.

---

## Dónde están las cosas

| Qué | Dónde |
|---|---|
| Configuración | `C:\ProgramData\FocusLock\config.json` |
| Estado, créditos, bitácora | `C:\ProgramData\FocusLock\state.json` |
| Token de TickTick | en `state.json`, **cifrado con DPAPI** |
| Extensiones | `extension/chrome/`, `extension/firefox/` |
| Tests | `python -m tests.test_focuslock`, `test_imports`, `test_guard` |

El token nunca se guarda en texto plano. Usa DPAPI con scope de máquina, que es
lo que permite que el servicio (LocalSystem) y la GUI (usuario) lo lean sin
compartir nada.

---

## Estructura del código

```
focuslock/
  daemon.py     motor: coordina todo (corre en el servicio)
  gate.py       la lógica de la puerta: qué cuenta y cuándo desbloquea
  rules.py      normalización y coincidencia (tareas, sitios, programas)
  ifeo.py       escritura/limpieza de claves de registro
  guard.py      vigilante de procesos
  server.py     HTTP local para las extensiones
  ipc.py        named pipe GUI ↔ servicio
  emergency.py  validación del compromiso escrito
  ticktick.py   cliente de la API (sin dependencias)
  store.py      estado persistente
  config.py     configuración
  secrets.py    cifrado DPAPI
  service.py    envoltorio del servicio de Windows
  stub.py       aviso que muestra IFEO en vez del programa
  ui/           ventana principal y diálogo de emergencia
```

`gate.py` es el corazón y está aislado de I/O: recibe un cliente y un store, y
se puede probar entero sin red.

---

## Probar los cambios

```powershell
.\run_tests.ps1          # las 4 suites, cada una en su proceso
.\run_tests.ps1 -Quick   # omite test_guard, que es el lento
```

O una por vez:

| Suite | Qué cubre |
|---|---|
| `test_focuslock` | reglas, la puerta, emergencia, cifrado DPAPI, servidor HTTP |
| `test_imports` | imports válidos y que la UI solo llame comandos existentes |
| `test_ui` | **construye la ventana y el tray de verdad**, en modo headless |
| `test_guard` | **mata procesos reales** y verifica la protección de `explorer.exe` |

Cada suite va en su propio proceso a propósito. `test_ui` crea un
`QApplication` y Qt solo admite uno por proceso; si compartieran, la segunda
suite que arranque fallaría.

Dos que merecen confianza:

- `test_ui` es lo que atrapó los bugs de `createMenu()` y del doble
  `QApplication`, además del banner que afirmaba "BLOQUEADO" sin tener idea.
  Construye la ventana de verdad, contra un servicio simulado.
- `test_guard` lanza copias de `pythonw.exe` con nombres propios y verifica que
  el vigilante las mate. No toca el `python.exe` real: el runner sería un
  objetivo válido y se mataría a sí mismo. Y hay un bloque entero de tests que
  comprueba que `explorer.exe` y `OpenCode.exe` **nunca** son objetivo, sin
  matar nada.

---

## Límites conocidos

- **La extensión se puede desactivar** desde el navegador. El IFEO no, pero
  las pestañas quedan como puerta trasera mientras el navegador esté abierto.
- **El vigilante mata por nombre de proceso.** Si tenés dos versiones de la
  misma app con nombres distintos, hay que bloquear las dos. Ojo: si una de
  ellas se llama `explorer.exe` o `OpenCode.exe` en tu PC, FocusLock no la va a
  tocar nunca.
- **`console` es un modo de desarrollo, no un modo de uso.** Sirve para ver
  logs y probar la conexión con TickTick. Para el uso diario, instalá el
  servicio.
- **IFEO requiere admin.** Sin elevación el bloqueo duro queda desactivado y
  solo funciona el vigilante. `install.ps1` avisa si falta.
- **La API de TickTick es usada tal cual.** Si TickTick cambia endpoints, hay
  que ajustar `ticktick.py`. El proyecto se busca por nombre justamente para
  que un cambio de ID no rompa nada.
- **Un reinicio de Windows limpia el IFEO** solo si alguien lo borró
  explícitamente; las claves de registro persisten. Pero si el servicio no
  está corriendo, no hay vigilancia.

---

## Antes de dejarlo funcionando

Revocá el token de TickTick y generá uno nuevo. Si compartiste el token en un
chat o lo pegaste en algún lado, da por filtrado: la app lo guarda cifrado,
pero un token filtrado sirve para leer y modificar tus tareas.
