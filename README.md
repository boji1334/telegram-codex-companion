# Pocket Codex

[English](README.md) | [简体中文](README.zh-CN.md)

Pocket Codex is a private Telegram companion for long-running conversations with OpenAI.
It is designed for a personal always-on computer: your phone talks to Telegram, your
computer polls Telegram, stores conversation state in SQLite, and calls the OpenAI API.

The default deployment does not need a public IP address or an exposed port.

## Features

- Private Telegram Bot interface for iPhone, Android, desktop Telegram, and web Telegram.
- Project and session switching with Telegram inline buttons.
- SQLite conversation history stored on your own machine.
- User allowlist and first-time `/claim` setup flow.
- OpenAI Responses API backend.
- GitHub-ready structure with tests, linting, docs, and CI.

## Architecture

```text
Telegram on iPhone
  -> Telegram Bot API
  -> Pocket Codex running on your always-on computer
  -> SQLite local history
  -> OpenAI Responses API
```

## Quick Start

1. Create a Telegram bot with [BotFather](https://t.me/BotFather).
2. Install Anaconda or Miniconda.
3. Create a project-local Conda environment:

```powershell
conda env create -p .\.conda -f environment.yml
.\.conda\python.exe -m pip --version
```

4. Create `.env` from `.env.example` and fill in:

```env
TELEGRAM_BOT_TOKEN=your-telegram-token
OPENAI_API_KEY=your-openai-key
TELEGRAM_ALLOWED_USER_IDS=your-numeric-telegram-user-id
```

5. Create your project config:

```powershell
Copy-Item .\config\projects.example.json .\config\projects.json
```

6. Run the bot:

```powershell
.\.conda\python.exe -m pocket_codex --check-config
.\.conda\python.exe -m pocket_codex
```

You can also start it later with:

```powershell
.\scripts\run-pocket-codex.ps1
```

7. Open Telegram and send `/start` to your bot.

## Telegram Commands

- `/start` connects your authorized account.
- `/projects` opens the project picker.
- `/sessions` opens the session picker for the current project.
- `/new Title` creates a new session in the current project.
- `/rename Title` renames the current session.
- `/status` shows the active project, session, and model.
- `/whoami` shows your Telegram user id.
- `/claim token` authorizes your account when `BOT_SETUP_TOKEN` is configured.

## Configuration

Environment variables:

| Name | Required | Description |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Yes | Token from Telegram BotFather. |
| `OPENAI_API_KEY` | Yes | OpenAI API key. |
| `TELEGRAM_ALLOWED_USER_IDS` | Recommended | Comma-separated Telegram user ids allowed to use the bot. |
| `BOT_SETUP_TOKEN` | Optional | A private token for first-time `/claim`. |
| `OPENAI_MODEL` | Optional | Defaults to `gpt-5.4-mini`. |
| `OPENAI_STORE` | Optional | Defaults to `false`; history is stored locally in SQLite. |
| `POCKET_CODEX_DATA_DIR` | Optional | Defaults to `./data`. |
| `POCKET_CODEX_PROJECTS_FILE` | Optional | Defaults to `./config/projects.json`. |
| `MAX_HISTORY_MESSAGES` | Optional | Defaults to `24`. |

Project config example:

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
    "path": "C:/Users/you/Documents/steel_cxx",
    "system_prompt": "This session is for the steel_cxx project."
  }
]
```

The project path is included as project metadata. This first version does not read files
automatically, which keeps the security boundary simple. File search and explicit file
attachment tools can be added as separate modules.

## Development

```powershell
python -m pip install -e ".[dev]"
ruff check .
pytest
```

## Security Notes

- Never commit `.env`, API keys, Telegram tokens, or the SQLite database.
- Prefer `TELEGRAM_ALLOWED_USER_IDS` for a single-user deployment.
- Use a long random `BOT_SETUP_TOKEN` if you prefer the `/claim` flow.
- Keep polling mode for home deployments unless you specifically need webhooks.
- Project directories are allowlisted through `config/projects.json`.

See [docs/security.md](docs/security.md) and [docs/windows-startup.md](docs/windows-startup.md).

## Roadmap

See [docs/roadmap.md](docs/roadmap.md). The intended next step is explicit file reading
inside allowlisted project folders, followed by Telegram voice-message support.

## Publishing

See [docs/github-publish.md](docs/github-publish.md) for a safe first GitHub push.
