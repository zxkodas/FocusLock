# AGENTS.md

Working notes for this repo. Read before changing code.

## Releases

**Release notes list the changes and only what matters.** The user asked for
this explicitly after the 1.1.0 notes. Concretely:

- A bulleted list of what changed since the previous version, worst first.
- Only things a user can act on or would be surprised by: an unsigned binary, a
  signature they have to get, a known caveat.
- No narrative of how the work went, no history of the debugging, no thanks.
- Keep it short. A release with one fix gets a couple of lines, not a page.

Do not put the commit-message story in the release notes. The commit message is
where the reasoning goes.

Before tagging, check that `master` has nothing the tag will not include:
`git log <tag>..master`. If it is non-empty, the published `.exe` is behind the
code. That is how the 1.1.0 `.exe` shipped with the `reset` bug fixed only on
master.

Bump the version in `pyproject.toml` and `installer/TickFence.iss` together;
`tests/test_installer.py` fails if they diverge. The browser extension has its
own numbering and is not touched.

## What this is

A Windows focus blocker. It locks chosen programs and websites until the user
completes N tasks in a TickTick kanban project. Comments, docstrings, GUI
strings and CLI help are **Spanish**; the README and GitHub metadata are
English. Match whatever file you are editing.

## Commands

```powershell
.\run_tests.ps1            # all 8 suites, each in its own process
.\run_tests.ps1 -Quick     # skips test_guard (the slow one)

python -m tests.test_focuslock TestSecrets.test_roundtrip   # single test/class

python -m focuslock doctor     # first thing to run when something is misbehaving
python -m focuslock reset      # factory state: unlocked, counters at zero
python -m focuslock console    # foreground engine, process guard OFF
python -m focuslock.build_xpi  # rebuild the .xpi/.zip for the browser extensions
```

`install` / `uninstall` / `ifeo-reconcile` need **Administrator**. The GUI, the
pipe and the HTTP server do not — that separation is the design.

## Architecture facts that filenames do not tell you

- **The Windows service owns the block, not the GUI.** It runs as `LocalSystem`.
  The GUI is just a client over the named pipe `\\.\pipe\TickFence`. This is why
  the GUI needs no admin rights.
- **IFEO is the hard layer.** `ifeo.py` writes
  `HKLM\...\Image File Execution Options\<exe>` with a `Debugger` value pointing
  at `python -m focuslock --ifeo-stub`. Windows then runs the stub *instead of*
  the program — the program never loads. Because it is in `HKLM`, a normal user
  cannot undo it. The process guard is the second layer, the extension the third
  and weakest (the user can just turn it off).
- **`focuslock/install_pkg.py` exists because `pythonservice.exe` starts with its
  working directory at `C:\Windows\System32` and no `PYTHONPATH`.** The package
  must be pip-installed into site-packages or the service cannot import it. If
  the project folder moves, re-run it.
- **Two copies of the code exist, and they drift.** site-packages is what the
  Windows service and any launch whose working directory is not the project
  import. After editing, `python -m focuslock.install_pkg` refreshes it; the
  shortcut's working directory already points at the project, so a desktop
  launch sees edits immediately. Symptom of forgetting: the change "does
  nothing" and the render looks correct.
- **`gate.py` is deliberately I/O-free**: it takes a client and a store, so the
  whole unlock decision is testable without a network. Keep it that way.
- The extension polls `http://127.0.0.1:47821/state?token=…`. The port is a
  hardcoded default in `server.py`. The server must **accept `Origin: null`**
  (Firefox MV3 popup sends it) and 403 foreign origins — the token is the real
  protection.

## Safety invariants — do not "clean these up"

- **`NEVER_BLOCK` is checked inside `match_program()`, before the allowlist.**
  It is not in `rules.allowed` on purpose: the allowlist is user-editable,
  `NEVER_BLOCK` is not. Moving it into the allowlist reintroduces a bug that
  took the whole desktop down (a guard killed `explorer.exe`). `explorer.exe`
  must never appear in the allowlist either.
- **`console` keeps the process guard off unless `--armar-guard` is passed.**
  It runs in the interactive session, so an armed guard kills your desktop.
  Do not flip the default to "helpful".
- **There is no "deactivate lock" button, by design.** The toggle becomes a
  disabled "Bloqueo activo" label while locked. Do not add a way to switch the
  block off from the UI.
- **The emergency button is enabled only while a lock is active.** Greys out
  otherwise.
- **`general.start_locked` must stay `false`.** Launching the app must never
  block anything on its own.
- No autostart on boot, and no "mark as done" button in TickFence — credits come
  only from TickTick. Both were explicit product decisions.

## The unlock rule, and the part that is easy to get wrong

- **No name filter.** Any task in the project counts. `task_prefix` still exists
  in the config for backward compatibility but is deprecated and unused. Do not
  reintroduce prefix matching.
- **Credit is awarded by change**, not by state: a task counts only if a poll
  saw it pending first. This is what stops installing with 20 old ticked tasks
  from unlocking anything.
- **An empty project counts as finished work.** Recurring TickTick tasks are not
  archived when ticked — they reset to `0` — so there is no observable
  pending→completed transition. The app instead credits tasks that *disappeared*
  from the project. **The single exception is the first poll of a cycle**: with
  no previous baseline there is nothing to compare, so an empty response is
  ignored. If you revert that guard to "reject all empty responses", a user who
  completes every task in the project gets locked with no way out.
- Accepted trade-off, documented in the README: deleting a task by hand also
  counts. That is the price of TickTick not exposing a recurring task's
  completed state.
- Defaults (all configurable in the `Ajustes` tab): 2 tasks, 45 s poll,
  300 words / 5 min of typing / 20 min unlock, 30 words per reflection question.
  They are defaults, not design constants.

## Emergency unlock validation

`emergency.py` counts **keystrokes**, not just characters, and rejects
`chars / keystrokes > 3.0` so pasting a block of text does not pass. Writing
time is measured between keystrokes, so a text left sitting there does not
accumulate time. An idle gap over 15 min restarts the session.

## Testing quirks

- **Each suite must run in its own process.** `test_ui` creates a
  `QApplication` and Qt only allows one per process; sharing would break the
  second suite.
- **`test_guard` kills real processes.** It copies `pythonw.exe` to
  `TickFenceTestBlocked.exe` / `TickFenceTestAllowed.exe` and lets a real
  `ProcessGuard` terminate them. It protects only its own PID. It is the slow
  suite.
- **`test_win32` is not redundant.** It walks the source and checks every
  `win32X.attr` against the real module, because pywin32 symbols live in
  non-obvious modules (`win32api.StartService` is in `win32service`,
  `win32pipe.CreateFile` in `win32file`, …). Guessing module placement caused
  several failed installs; the test exists so nobody has to guess again.
- **`test_imports` catches import errors that only surface when a privileged
  command runs** — and that only happens on the user's machine, with admin.
- `tests/` has no `__init__.py`; run suites as `python -m tests.<name>`.

## Never commit a real credential

A real TickTick token was hardcoded in a test once and had to be removed from
history. Use a fake with the right shape, e.g. `"tp_" + "0" * 32`. `.gitignore`
already excludes `config.json`, `state.json` and the `*.bak*` backups, which hold
the DPAPI-encrypted token and live in `C:\ProgramData\TickFence`.

## Permissions gotcha

The service runs elevated and creates `config.json` / `state.json` read-only.
Without write access the GUI fails to save settings. That is why `install.ps1`
finishes by running `python -m focuslock.permissions`. If the GUI suddenly
cannot save, re-run it as admin.

## Browser extensions

- Chrome manifest uses `background.service_worker`; Firefox uses
  `background.scripts` (event page). They are **not** interchangeable.
- Firefox needs `browser_specific_settings.gecko.data_collection_permissions`
  (`{"required": ["none"]}`) or addons.mozilla.org rejects the upload, and
  `strict_min_version` must be **>= 140** because that key is unknown before it.
  Chrome must not carry `browser_specific_settings` at all.
- `build_xpi` writes `manifest.json` first and uses `ZIP_STORED`; that ordering
  is required.
- **Bump the version in both manifests and `popup.js` `VERSION` together.**
  `test_extension.py` asserts the two manifests match, that the popup's
  `VERSION` equals the manifest's `major.minor`, and that Firefox declares
  `data_collection_permissions` with `strict_min_version >= 140`. Change one and
  the suite fails. (Do not edit these files with `Get-Content | Set-Content`
  from PowerShell — it reads UTF-8 as ANSI and mangles the accented characters.
  Use the `edit` tool or `python`.)
- Chrome loads from the `extension/chrome` **folder** (not the zip); moving or
  deleting the project folder stops it working.
- Unsigned Firefox `.xpi` is refused by Firefox. Signing is done out of band
  through addons.mozilla.org.
