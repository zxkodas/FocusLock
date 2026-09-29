# Security Policy

## Supported versions

Only the latest release on `master` is supported. There are no long-term
support branches.

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private reporting:

**Security → Report a vulnerability** on this repository.

Include what an attacker could do, and how to reproduce it. You should get an
acknowledgement within a week.

## What this program does that touches the system

TickFence is not a normal desktop app, so it is worth being explicit about
what it touches. None of this is a vulnerability report — it is context for
judging one.

- **It runs as a Windows service as `LocalSystem`.** That is what makes the
  block hard to defeat: a normal user cannot stop it. `LocalSystem` is the
  most privileged account on the machine.
- **It writes to `HKLM`,** under `Image File Execution Options`. Because that
  is `HKLM`, a standard user cannot undo the block on their own.
- **It kills processes** you list in *Programas*, while the lock is active.
  `explorer.exe` and a few system binaries are on a permanent never-block
  list; moving that into the user-editable allowlist previously took the whole
  desktop down.
- **It stores your TickTick token,** encrypted with DPAPI, under
  `C:\ProgramData\TickFence`. It is encrypted to the machine, not to your
  user account.
- **It serves `http://127.0.0.1:47821`** for the browser extension, protected
  by a token rather than by origin. Any local process that obtains the token
  can read the extension's state endpoint. That is a deliberate trade-off for
  a loopback-only, token-gated design.

## A note on running an unsigned installer

The `.exe` in the releases is **not code-signed**. Windows SmartScreen will
warn about it, and that warning is expected. If you do not trust a binary you
downloaded, run from source instead:

```
git clone https://github.com/zxkodas/TickFence
cd TickFence
powershell -ExecutionPolicy Bypass -File install.ps1
```
