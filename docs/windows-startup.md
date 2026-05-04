# Windows Startup

This project is designed to run on an always-on Windows computer.

## Power Settings

Open Windows power settings and configure:

- Turn off display: allowed.
- Sleep: never.
- Hibernate: off, if you want the bot to be reachable at all times.

## Simple Startup Folder

Create a PowerShell script outside the repository, for example:

```powershell
Set-Location "C:\path\to\telegram-codex-companion"
.\scripts\run-pocket-codex.ps1
```

Then place a shortcut to that script in:

```text
shell:startup
```

## Task Scheduler

For a more reliable setup, create a Windows Task Scheduler task:

- Trigger: at log on.
- Action: start `powershell.exe`.
- Arguments:

```powershell
-ExecutionPolicy Bypass -File "C:\path\to\run-pocket-codex.ps1"
```

For long-term unattended use, consider running the bot under a dedicated Windows user
account with limited filesystem permissions.
