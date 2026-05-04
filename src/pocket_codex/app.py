import logging

from telegram import Update

from .config import load_settings
from .openai_responder import OpenAIResponder
from .repository import Repository
from .telegram_bot import PocketCodexTelegramBot

logger = logging.getLogger(__name__)


def run() -> None:
    settings = load_settings()
    repository = Repository(settings.database_path)
    repository.migrate()
    repository.sync_projects(settings.projects)

    bot = PocketCodexTelegramBot(
        settings=settings,
        repository=repository,
        responder=OpenAIResponder(settings),
    ).build()

    logger.info("Pocket Codex is running in Telegram polling mode.")
    bot.run_polling(allowed_updates=Update.ALL_TYPES)
