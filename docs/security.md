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

Project directories must be explicitly listed in `config/projects.json`. The first
release includes project metadata in the prompt, but does not automatically read files.
This makes the initial security boundary easier to audit.

