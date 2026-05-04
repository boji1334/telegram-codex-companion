# Security

Pocket Codex is intended to be private by default.

## Access Control

Use `TELEGRAM_ALLOWED_USER_IDS` for the strongest simple setup. A Telegram username is
not enough because usernames can change. Numeric user ids are stable.

If you use the `/claim` flow, set a long random `BOT_SETUP_TOKEN`, authorize your own
account once, then remove the token from `.env` and restart the bot.

## Secret Handling

Keep these out of Git:

- `.env`
- `data/`
- `*.sqlite3`
- Telegram bot tokens
- OpenAI API keys

The included `.gitignore` excludes local secrets and state by default.

## Network Exposure

Polling mode means your computer opens an outbound connection to Telegram. You do not
need to expose a local HTTP server to the public internet.

Use webhooks only if you have a clear reason and can put the service behind HTTPS,
authentication, logging, and rate limits.

## Project Access

Project directories must be explicitly listed in `config/projects.json`.

Command execution is disabled unless both of these are true:

- `.env` contains `POCKET_CODEX_COMMANDS_ENABLED=true`.
- The selected project contains `allow_shell=true`.

`/run` and `/ssh` are intended for read-only inspection. The runner blocks common delete,
move, copy, install, permission, process-kill, reboot, destructive Git, and output-redirection
commands, and it enforces a timeout plus output truncation. This is a guardrail, not a full
OS sandbox. Only enable command execution on a private bot, with numeric Telegram user-id
allowlisting, for projects you trust.

Keep SSH passwords in `.env`, an ignored local file, an SSH agent, or a private key store.
Never commit passwords, tokens, private keys, `config/projects.json`, or command output logs.
