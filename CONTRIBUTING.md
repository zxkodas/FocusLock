# Contributing to TickFence

This is not a normal desktop app. Before you change anything, read this file
all the way through: some of the rules below exist because breaking them took
the author's desktop down.

## Running the tests

```powershell
git clone https://github.com/zxkodas/TickFence
cd TickFence
python -m pip install -r requirements.txt
.\run_tests.ps1
```

That is 10 suites, 255 tests, about two minutes. `-Quick` skips `test_guard`,
which is the only genuinely slow one.

```powershell
python -m tests.test_focuslock TestSecrets.test_roundtrip   # one test
python -m tests.test_ui                                     # one suite
```

**Each suite runs in its own process, and that is not optional.** `test_ui`
creates a `QApplication` and Qt allows exactly one per process; share it and
the second suite dies in a way that looks like a product bug. That is why
`run_tests.ps1` shells out instead of importing.

If something is misbehaving at runtime, run this before opening an issue:

```powershell
python -m focuslock doctor
```

## What not to break

### `NEVER_BLOCK` is not the allowlist

`focuslock/rules.py` has a `NEVER_BLOCK` set that `match_program()` checks
**before** the user's allowlist. Moving those names into the user-editable
allowlist reintroduces a bug that once killed `explorer.exe` and locked the
author out of their own machine. `explorer.exe` must never appear in
`programs.allowed` either.

The same goes for `general.start_locked`: it stays `false`. Launching the app
must never block anything on its own.

### There is no "deactivate lock" button

By design. The toggle becomes a disabled "Lock active" label while the lock
is on. Do not add a way to switch it off from the UI; the emergency unlock is
the only exit and it has to stay uncomfortable.

### Comments in Spanish, README in English

Code comments, docstrings, GUI strings and CLI help are **Spanish**. The
README, changelogs and GitHub metadata are **English**. Match whatever file
you are editing — that rule is not a preference, it is what keeps the history
readable.

### Never commit a credential

`.gitignore` already excludes `config.json` and `state.json`, which hold the
DPAPI-encrypted TickTick token under `C:\ProgramData\TickFence`. A real
token was committed once and had to be scrubbed from history. In tests, use a
fake with the right shape: `"tp_" + "0" * 32`.

## Things that will surprise you

**Two copies of the code exist and they drift.** The Windows service runs
from site-packages, not from your working folder. After editing:

```powershell
python -m focuslock.install_pkg
Restart-Service TickFenceSvc
```

Symptom of forgetting: the change "does nothing" and the source looks right.

**`test_guard` kills real processes.** It copies `pythonw.exe` to
`TickFenceTestBlocked.exe` and lets a real `ProcessGuard` terminate it. It
only ever touches its own PIDs, and that guarantee is what
`rules.NEVER_BLOCK` is verified by. Do not run it on a machine you are
working on, and never add a real system binary to it.

**The extension has two copies that must stay identical.**
`extension/chrome/` and `extension/firefox/` share `sw.js`, `popup.js` and
`popup.html` byte for byte; only the manifests differ. `test_extension`
enforces it. If you need browser-specific text, it belongs in `i18n.js`
keyed by the system language, not in a diverged copy.

**The installer is not a frozen exe, on purpose.** The block holds because
Windows starts a real service (`pythonservice.exe`) registered in `HKLM` with
`pythonClassString`. A PyInstaller console exe cannot be that service: launched
from the SCM it detaches and dies with error 1066. `installer/TickFence.iss`
does what `install.ps1` does instead.

**`test_imports` is not redundant.** It walks the source and checks every
`win32X.attr` against the real pywin32 module, because those symbols live in
non-obvious modules (`win32api.StartService` is in `win32service`,
`win32pipe.CreateFile` is in `win32file`). Guessing where they live caused
several failed installs on the author's machine, which is why the test exists.

## Adding a string

1. Write the literal in **English** and wrap it: `tr("Active lock")`.
2. Add the Spanish to the `ES` table in `focuslock/i18n.py`.
3. Bump the test-count badge in the README.

Step 2 is not optional. `test_i18n` fails the build if a `tr()` call site has
no entry, and that is the whole point: the failure mode of shipping two
languages is forgetting a new string, not mistranslating one.

If the text reaches `tr()` through a variable — the navigation labels and the
emergency prompt hints do — the AST scan cannot see it, and `_literales_tr()`
in `test_i18n` has to be taught about that table.

Two surfaces cannot use `i18n` at all:

- **`focuslock/stub.py`** runs outside the package and must start even when
  `focuslock` is not importable, so its two tables are duplicated there on
  purpose and `test_i18n` compares them by key.
- **The browser extension** follows `navigator.language` rather than reading
  TickFence's config.

## Style

- Comments explain *why*, not *what*. Several of them explain a bug that was
  already fixed, which is the only reason they exist.
- Keep `gate.py` free of I/O. It takes a client and a store so the entire
  unlock decision is testable without a network.
- New tests go in the suite that owns the concern, not in a new file. A tenth
  suite means a tenth process in `run_tests.ps1`.

## Sending a change

Open a pull request against `master`. CI runs the suite on Python 3.11 and
3.14; both must be green. If CI catches something your machine did not, that
is a bug in the tests, not in your change — add the test that catches it.
