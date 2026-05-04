# Deployment Guide

This guide describes a Windows home deployment using Telegram polling. It does
not require a public IP address, a domain name, webhook hosting, or an open port.

## 1. Create A Telegram Bot

1. Open Telegram and search for `@BotFather`.
2. Send `/newbot`.
3. Choose a display name, for example `Pocket Codex`.
4. Choose a unique username ending in `bot`, for example `your_name_codex_bot`.
5. BotFather returns a token. Keep it private and put it only in `.env`.

If a token is ever exposed, send `/revoke` to `@BotFather`, choose your bot, and
replace the old token in `.env`.

## 2. Clone And Install

```powershell
git clone https://github.com/boji1334/telegram-codex-companion.git
Set-Location .\telegram-codex-companion
conda env create -p .\.conda -f environment.yml
```

The environment is project-local, so dependencies live under `.conda/` inside
the repository directory. This folder is ignored by Git.

## 3. Configure Secrets

```powershell
Copy-Item .env.example .env
notepad .env
```

Minimum configuration:

```env
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
OPENAI_API_KEY=your-openai-or-gateway-key
TELEGRAM_ALLOWED_USER_IDS=
```

If you use an OpenAI-compatible gateway, set:

```env
OPENAI_MODEL=gpt-5.5
OPENAI_MODEL_CHOICES=gpt-5.5,gpt-5.4,gpt-5.4-mini
OPENAI_BASE_URL=http://your-compatible-api-host:port
```

If you use the official OpenAI API, leave `OPENAI_BASE_URL` empty and choose a
model available to your account.

## 4. Configure Projects

```powershell
Copy-Item .\config\projects.example.json .\config\projects.json
notepad .\config\projects.json
```

Example:

```json
[
  {
    "id": "general",
    "name": "General Chat",
    "path": null,
    "system_prompt": "General personal conversation. Answer in the user's preferred language."
  },
  {
    "id": "steel_cxx",
    "name": "steel_cxx",
    "path": "D:/code/steel_cxx",
    "system_prompt": "This session is for the steel_cxx project."
  }
]
```

Project paths are allowlisted. Codex Desktop sync uses these paths to match
Telegram projects to local Codex threads.

## 5. Optional: Enable Read-Only Commands And SSH

Command execution is disabled by default. For a private, allowlisted deployment,
you can turn it on in `.env`:

```env
POCKET_CODEX_COMMANDS_ENABLED=true
POCKET_CODEX_COMMAND_TIMEOUT_SECONDS=60
POCKET_CODEX_COMMAND_OUTPUT_MAX_CHARS=0
POCKET_CODEX_COMMAND_INLINE_MAX_CHARS=3500
```

Then enable it only for trusted projects in `config/projects.json`:

```json
{
  "id": "steel_cxx",
  "name": "steel_cxx",
  "path": "D:/code/steel_cxx",
  "system_prompt": "This session is for the steel_cxx project.",
  "allow_shell": true,
  "ssh_target": "user@example.com",
  "ssh_remote_path": "/srv/steel_cxx",
  "ssh_executable": "ssh",
  "ssh_hostkey": "",
  "ssh_password_env": "STEEL_CXX_SSH_PASSWORD"
}
```

Daily examples:

```text
/ssh nvidia-smi
/ssh tail -n 80 artifacts/server_logs/overnight_expand_fixed_gpu0.out
/ssh find artifacts -type f | grep -E "step9|trend|result|metrics|summary" | wc -l
/run Get-ChildItem -Recurse artifacts | Select-Object -Last 50
```

`/run` executes in the local project folder. `/ssh` executes `cd ssh_remote_path && command`
on the remote host. Output is sent back to Telegram and saved into the active conversation,
so the next message can ask the model to analyze it.

Plain chat can also use these tools automatically. After enabling this section, a message
like `看一下服务器训练结果怎么样` gives the model access to the same read-only SSH/local
commands, so it can inspect logs and artifacts before answering instead of asking you to
paste command output manually.

The runner is intentionally read-only: it blocks common delete, move, install, permission,
process-kill, reboot, destructive Git, and output-redirection commands. Treat this as a
guardrail, not a sandbox; only enable it for a private bot and trusted projects.

## 6. Enable Codex Desktop Sync

Codex sync is enabled by default:

```env
CODEX_SYNC_ENABLED=true
CODEX_HOME=C:/Users/your-user-name/.codex
```

When sync is enabled:

- `/sessions` lists matching local Codex Desktop threads.
- Telegram messages are appended to the selected Codex rollout file.
- Codex Desktop can inherit mobile messages after reopening the thread.
- Selecting a thread in Telegram sends a bubble-style HTML transcript export.
- The HTML transcript embeds mobile-friendly image thumbnails from Codex history.
- `/history` resends the full HTML transcript.
- `/model` changes the active GPT model for future replies.

## 7. First Run

Validate configuration:

```powershell
.\.conda\python.exe -m pocket_codex --check-config
```

Start the bot:

```powershell
.\scripts\run-pocket-codex.ps1
```

Open Telegram, open your bot, and send:

```text
/whoami
```

Copy the numeric user id into `.env`:

```env
TELEGRAM_ALLOWED_USER_IDS=123456789
```

Restart the bot and send:

```text
/start
/projects
/sessions
```

## 8. Daily Use

Typical flow:

```text
/projects
```

Choose a project.

```text
/sessions
```

Choose a Codex Desktop thread. The bot will attach a bubble-style HTML history
file with text and image thumbnails, then future Telegram messages will continue
that thread.

Useful commands:

- `/status` shows current project, session, and model.
- `/history` sends the full HTML transcript.
- `/model` switches the active GPT model.
- `/ssh` checks remote logs or GPU status for projects with SSH configured.
- `/run` checks local project files on the always-on computer.
- `/projects` switches project.
- `/sessions` switches Codex thread.
- `/exit` exits the current conversation; plain text `exit`, `退出`, or `退出对话`
  works too. Send `/start`, `/projects`, or `/sessions` to enter again.

When you send a normal message, the bot posts a small animated waiting status
until the model reply is ready. Model replies render common Markdown as Telegram
rich text instead of showing raw Markdown markers.

## 9. Windows Always-On Setup

For long-term use:

1. Disable system sleep in Windows power settings.
2. Allow the display to turn off.
3. Start the bot after login with `scripts/run-pocket-codex.ps1`.
4. For a more reliable setup, use Windows Task Scheduler.

See [windows-startup.md](windows-startup.md) for startup options.

## 10. Troubleshooting

If Telegram replies say the model call failed:

- Check `OPENAI_API_KEY`.
- Check `OPENAI_BASE_URL` if using a gateway.
- Check `data/logs/pocket-codex.log` for the detailed exception.
- Use `/model` in Telegram to switch to another configured model and retry.
- Run `.\.conda\python.exe -m pocket_codex --check-config`.
- Restart the bot.

If Telegram cannot see Codex threads:

- Check `CODEX_HOME`.
- Check project paths in `config/projects.json`.
- Open the relevant project/thread once in Codex Desktop so it exists locally.

If Codex Desktop does not show Telegram messages:

- Reopen the thread in Codex Desktop.
- Restart Codex Desktop.
- Confirm that the selected Telegram session is connected to the intended Codex
  thread with `/status`.

If the history view is too long:

- Use `/history` for the HTML file.
- Lower `TELEGRAM_HISTORY_ON_OPEN_MESSAGES` or `TELEGRAM_HISTORY_EXPORT_MAX_MESSAGES`.

If `/ssh` fails:

- Confirm the active project with `/status`.
- Confirm `POCKET_CODEX_COMMANDS_ENABLED=true`.
- Confirm the project has `allow_shell=true` and `ssh_target`.
- If using OpenSSH, configure SSH keys or an agent because password prompts are disabled.
- If using PuTTY `plink.exe`, set `ssh_executable`, optionally `ssh_hostkey`, and keep
  the password in `.env` or another ignored local file.
- Run the same SSH command once from PowerShell to verify host access.

## 11. Files That Must Stay Private

Do not commit:

- `.env`
- `.conda/`
- `data/`
- `config/projects.json`
- `*.sqlite3`
- Codex rollout backups

The included `.gitignore` excludes these by default.
