# FocusLock

**A focus blocker for Windows.** It locks the programs and websites you chose
and keeps them locked until you complete **2 tasks** in your TickTick project.

There is an emergency escape hatch. It costs you 300 words and five minutes of
real typing, and it is written down with a timestamp so you can read your own
words back the next time you are tempted.

This is a self-imposed commitment device, not a parental control. Everything it
blocks is on your own machine, under your own account. The whole design is
aimed at one moment: the ten seconds when you are alone and deciding whether to
cheat.

---

## Table of contents

- [What it actually does](#what-it-actually-does)
- [How it works](#how-it-works)
- [The three layers of blocking](#the-three-layers-of-blocking)
- [Why IFEO is the layer that matters](#why-ifeo-is-the-layer-that-matters)
- [Safety: what can never be blocked](#safety-what-can-never-be-blocked)
- [Installation](#installation)
- [Browser extension setup](#browser-extension-setup)
- [Command reference](#command-reference)
- [How unlocking is decided](#how-unlocking-is-decided)
- [The emergency unlock](#the-emergency-unlock)
- [Configuration reference](#configuration-reference)
- [Where things live](#where-things-live)
- [Project layout](#project-layout)
- [Running the tests](#running-the-tests)
- [Known limits](#known-limits)
- [Before you start](#before-you-start)

---

## What it actually does

**Blocking is opt-in.** Opening FocusLock does not lock anything. You press
**Activate lock**, and from that moment the chosen programs will not start and
the chosen sites will not load, until two tasks are completed in TickTick.

Credits are earned only by doing the work in TickTick. There is deliberately
**no "mark as done" button inside FocusLock** — that shortcut would defeat the
entire point of the app.

## How it works

```
┌─ Your normal session (no admin rights) ────────────┐
│    FocusLock GUI  ──────named pipe──────┐          │
│    Browser extension ─────local HTTP────┤          │
└──────────────────────────────────────────┼──────────┘
                                           ▼
┌─ Windows service (LocalSystem, starts on boot) ────┐
│    · polls TickTick and awards credits            │
│    · writes / removes IFEO keys in HKLM           │
│    · process guard, every 0.8 s                    │
│    · local HTTP server for the browser extension  │
└───────────────────────────────────────────────────┘
```

The service is the real owner of the block. The GUI only asks it for things over
a named pipe, which is why **the GUI works without administrator rights**. Only
the one-time install needs elevation.

## The three layers of blocking

| Layer | What it does | How it can be beaten |
|---|---|---|
| **IFEO** | Windows never starts the program at all — it is replaced by a notice | You would need admin rights to delete the `HKLM` keys |
| **Process guard** | Detects a process within 0.8 s and kills it if it slipped through | Killing it by hand from Task Manager |
| **Browser extension** | Blocks domains and closes tabs that are already open | Turning the extension off (yes, you can) |

The extension is the weakest layer, on purpose. There is no way to block an
extension from another process without the user noticing. **IFEO is the layer
that holds.**

### Why IFEO is the layer that matters

`HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution
Options\<program>.exe` with a `Debugger` value makes Windows **not run** the
program — it runs the debugger instead. The blocked program never loads and
never paints a window.

And because it lives in `HKLM`, a normal user cannot touch it. Removing it
requires elevation, which is exactly the point: **opening a console should not
be enough.**

## Safety: what can never be blocked

> **`rules.NEVER_BLOCK` is enforced inside `match_program()` itself.** It is not
> part of your editable allowlist, so it cannot be turned off from the settings —
> not even with explicit confirmation.
>
> It contains the desktop shell (`explorer.exe`, `userinit.exe`, `sihost.exe`,
> `ctfmon.exe`, …), the session core (`lsass.exe`, `csrss.exe`, `winlogon.exe`,
> `services.exe`, `svchost.exe`, …), antivirus (`msmpeng.exe`), FocusLock
> itself, and the entire set of tools you would use to undo the block:
> `cmd.exe`, `powershell.exe`, `taskmgr.exe`, `regedit.exe`, `taskkill.exe`,
> `shutdown.exe`, `msconfig.exe`, `control.exe`, `rundll32.exe`, `mshta.exe`,
> `wscript.exe`, `cscript.exe`.
>
> `explorer.exe` is **not** in the allowlist on purpose. The allowlist is
> editable; `NEVER_BLOCK` is not. If it were only in the allowlist, one day you
> would remove it by accident and lose access to your desktop anyway.

This design came directly out of a bug: an earlier version of the process guard
killed `explorer.exe` and took the whole desktop down with it.

## Installation

Requirements: **Windows 10/11**, **Python 3.11+**, and a **TickTick** account
with a kanban project for your tasks.

> **Note:** this README is in English, but the **GUI is in Spanish**. The tabs are
> `Estado`, `Programas`, `Sitios`, `Ajustes` and `Bitácora`. The code comments are
> Spanish too.

Open **PowerShell as Administrator** in this folder:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

That installs the dependencies, registers the Windows service, starts it, and
verifies that it answers. To set your TickTick token in the same step:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1 -Token "tp_..."
```

Then, **without** admin rights:

```powershell
python -m focuslock gui
```

To remove everything (as Administrator):

```powershell
python -m focuslock uninstall
```

## Browser extension setup

The extensions talk to the service over HTTP on `127.0.0.1:47821`. The URL
carries a random token, so it cannot be guessed or reached from anywhere else.

Open the extension options and paste the address shown in FocusLock under
*Browser extension* (tab `Ajustes` → *Extensión del navegador*).

### Chrome / Edge / Brave (Chromium, Manifest V3)

1. Go to `chrome://extensions` and turn on **Developer mode**
2. **Load unpacked** → select the `extension/chrome` folder
3. Open the extension options, paste the address, save

> This loads the extension from a folder, so if you move or delete the project
> folder Chrome stops blocking. It survives browser restarts, not the folder
> being moved.

### Firefox (Manifest V3, event pages)

Firefox requires extensions to be signed, and an unsigned `.xpi` is refused with
*"this extension has not been verified."* There are two ways to run it:

- **Signed build (recommended).** Sign the extension through
  [addons.mozilla.org](https://addons.mozilla.org/developers/) and install the
  resulting `.xpi` with *Install Add-on From File*. This is permanent.
- **Temporary.** `about:debugging#/runtime/this-firefox` → *Load Temporary
  Add-on* → select `extension/firefox/manifest.json`. This one is **removed
  every time you close the browser**, so it is only useful for testing.

To rebuild the package after changing the extension:

```powershell
python -m focuslock.build_xpi
```

Both extensions are **fail-open**: if the service does not answer, they block
nothing on their own. The real block is held by Windows.

## Command reference

| Command | What it does |
|---|---|
| `python -m focuslock install [--token tp_…]` | Install and start the service (**needs admin**) |
| `python -m focuslock uninstall` | Remove the service, IFEO keys and shortcuts (**needs admin**) |
| `python -m focuslock gui` | Open the main window (no admin needed) |
| `python -m focuslock status` | One-line status summary |
| `python -m focuslock doctor` | **Full diagnostics: service, IFEO, TickTick, guard** |
| `python -m focuslock reset` | Back to factory state: unlocked, counters at zero |
| `python -m focuslock ifeo-reconcile` | Clean up orphaned IFEO keys (works with the service stopped) |
| `python -m focuslock console` | Run the engine in the foreground, **guard off** |

`doctor` is the first thing to run when something is not behaving.

### Why `console` does not arm the guard

`console` runs the engine **in your desktop session**, not as a service. If the
process guard ran there it would kill programs in the session you are using —
including your desktop. So it is off by default and you have to ask for it
explicitly:

```powershell
python -m focuslock console --armar-guard
```

As a service (`install`) the guard *is* armed, because that is what it has to
do. The difference is where it runs: in `LocalSystem`, not on your desktop.

## How unlocking is decided

The TickTick project is looked up **by name** on every poll, not by a stored ID.
If you rename or recreate it, the app keeps working. The emoji TickTick adds to
the name (`📖Studies`) is ignored when comparing.

**Every task in the project counts.** There is no name filter and no prefix:
what matters is that the total drops while the lock is active, not what the task
is called. (`task_prefix` still exists in the config file for backward
compatibility, but it is deprecated and unused.)

A credit is awarded by **change**, not by state. A task only counts if the app
saw it pending first and then saw it completed. That avoids two real bugs:

- Installing the app with 20 old tasks already ticked does not unlock anything.
  The first pass seeds the baseline without awarding credit.
- If the API returns a truncated list and a task reappears already completed, it
  is not counted as new.

**Recurring tasks — the case that actually matters.** Recurring TickTick tasks
are not archived when you tick them; they reset to `0` for the next day. There
is no "pending → completed" transition to observe. So FocusLock also credits a
task **that was registered and is now gone from the project**. Completing all
the tasks in the project counts as finishing the work, not as a glitch.

The trade-off is explicit: **deleting a task by hand also counts.** That is the
price of TickTick not exposing the completed state of a recurring task.

Credits survive a restart. Complete a task, reboot, and it still counts.

## The emergency unlock

To unlock without completing anything:

1. Write **300 words** in the commitment.
2. Type for **5 minutes**, measured from the first keystroke to the last.
   Closing and reopening the dialog **does not** reset the timer.
3. Answer three reflection questions, 30 words each.

The app measures **keystrokes**, not just characters, so pasting a long text
from the clipboard does not work: the characters-per-keystroke ratio spikes and
it is rejected. Leaving a text in place and waiting does not work either,
because the time is measured between keystrokes.

If you get through, the block lifts for the configured window (20 minutes by
default) and the full text is logged with a date and word count in the
**`Bitácora`** tab. When the window expires, the block returns on its own.

## Configuration reference

Everything lives in `C:\ProgramData\FocusLock\config.json`. The defaults, in
full:

| Key | Default | Meaning |
|---|---|---|
| `ticktick.project_name` | `"Estudios"` | Kanban project, matched by name |
| `ticktick.project_id` | `""` | Fallback if you prefer matching by ID |
| `ticktick.required` | `2` | Credits needed to unlock |
| `ticktick.poll_seconds` | `45` | How often TickTick is polled |
| `ticktick.task_prefix` | `""` | **Deprecated and unused** |
| `programs.blocked` | `[]` | Programs to block |
| `programs.allowed` | `notepad.exe`, `Code.exe`, `pycharm64.exe`, `devenv.exe`, `opencode.exe`, `focuslock.exe` | Never block these |
| `programs.use_ifeo` | `true` | Use the hard IFEO block |
| `sites.blocked` | `[]` | Domains to block |
| `sites.allowed` | `docs.python.org`, `stackoverflow.com`, `upt.edu.ar` | Never block these |
| `emergency.min_words` | `300` | Words in the written commitment |
| `emergency.min_minutes` | `5` | Minutes of real typing |
| `emergency.unlock_minutes` | `20` | How long the escape hatch lasts |
| `emergency.history_limit` | `50` | Emergency entries kept in the log |
| `general.start_locked` | `false` | **Opt-in:** never block just because the app opened |
| `general.show_block_notice` | `true` | Show the IFEO notice screen |

`general.start_locked` defaults to `false` on purpose: **launching FocusLock
must never lock anything by itself.** Only the button does.

## Where things live

| What | Where |
|---|---|
| Configuration | `C:\ProgramData\FocusLock\config.json` |
| State, credits, logs | `C:\ProgramData\FocusLock\state.json` |
| TickTick token | inside `state.json`, **encrypted with DPAPI** |
| Service | `FocusLockSvc` ("FocusLock Enforcement Service") |
| GUI ↔ service channel | `\\.\pipe\FocusLock` |
| Extension endpoint | `http://127.0.0.1:47821/state?token=…` |
| Extensions | `extension/chrome/`, `extension/firefox/` |

The token is never stored in plain text. It uses DPAPI at machine scope, which
is what lets the service (`LocalSystem`) and the GUI (your user) both read it
without sharing anything between accounts.

## Project layout

```
focuslock/
  daemon.py     the engine: coordinates everything (runs as the service)
  gate.py       the gate: what counts as work and when it unlocks
  rules.py      normalisation and matching (tasks, sites, programs)
  ifeo.py       writing and cleaning registry keys
  guard.py      the process guard
  server.py     local HTTP server for the extensions
  ipc.py        named pipe between GUI and service
  emergency.py  validation of the written commitment
  ticktick.py   API client (no third-party dependencies)
  store.py      persistent state
  config.py     configuration
  secrets.py    DPAPI encryption
  service.py    Windows service wrapper
  stub.py       the notice IFEO shows instead of your program
  paths.py      paths and platform checks
  local.py      non-service mode, for development
  diag.py       diagnostics
  reset.py      factory reset
  build_xpi.py  packaging for the browser extensions
  ui/           main window and emergency dialog
```

**`gate.py` is the heart and it is isolated from I/O:** it takes a client and a
store, so the whole thing can be tested without a network.

## Running the tests

```powershell
.\run_tests.ps1          # all 8 suites, each in its own process
.\run_tests.ps1 -Quick   # skips test_guard, the slow one
```

Or one at a time:

| Suite | What it covers |
|---|---|
| `test_focuslock` | Rules, the gate, the emergency flow, DPAPI, the HTTP server |
| `test_win32` | Scans the Win32 layer and the pywin32 module layout |
| `test_imports` | Valid imports, and that the UI only calls commands that exist |
| `test_ifeo` | Registry key construction and cleanup |
| `test_stub` | The block notice the stub shows |
| `test_ui` | **Builds the real window and tray**, headless |
| `test_extension` | The two extension manifests and the popup |
| `test_guard` | **Kills real processes** and verifies the `explorer.exe` protection |

**196 tests.** Each suite runs in its own process on purpose: `test_ui` creates
a `QApplication`, and Qt only allows one per process, so a second suite sharing
the process would fail.

Two are worth trusting more than the rest:

- `test_ui` builds the actual window against a simulated service. It is what
  caught the `createMenu()` bug, the double `QApplication`, and the banner that
  claimed "LOCKED" without having any idea.
- `test_guard` launches copies of `pythonw.exe` under its own names and checks
  that the guard kills them. It never touches the real `python.exe` — the test
  runner would be a valid target and would kill itself. A whole block of tests
  verifies that `explorer.exe` and `OpenCode.exe` are **never** targets, without
  killing anything.

## Known limits

- **The browser extension can be turned off.** IFEO cannot, but open tabs stay
  a back door for as long as the browser is running.
- **The process guard matches by process name.** If you have two versions of
  the same app under different names, block both. And if one of them happens to
  be called `explorer.exe` or `OpenCode.exe` on your machine, FocusLock will
  never touch it.
- **`console` is a development mode, not a daily-use mode.** It is for reading
  logs and testing the TickTick connection. Install the service for real use.
- **IFEO requires admin rights.** Without elevation the hard block is disabled
  and only the process guard works. `install.ps1` warns if they are missing.
- **The TickTick API is used as-is.** If TickTick changes its endpoints,
  `ticktick.py` needs updating. The project is matched by name precisely so that
  a change of ID does not break anything.
- **The service must be running.** Registry keys persist across reboots, but
  with the service stopped there is no guard and no polling.
- **Deleting a TickTick task by hand counts as completing it.** This is the
  price of recurring tasks, as described above.

## Before you start

Revoke any TickTick token you have shared in a chat, a screenshot or anywhere
else, and generate a new one. FocusLock stores it encrypted, but **a leaked token
lets someone read and modify your tasks.**

If you revoke a token, re-enter the new one in FocusLock → `Ajustes`, and the
extension will report `invalid token` until you do.
