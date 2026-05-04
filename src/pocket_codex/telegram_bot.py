from __future__ import annotations

import logging
from html import escape
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .codex_store import CodexStore
from .config import Settings
from .openai_responder import OpenAIResponder
from .repository import Repository
from .text import chunk_text, compact_label

logger = logging.getLogger(__name__)


class PocketCodexTelegramBot:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: Repository,
        responder: OpenAIResponder,
        codex_store: CodexStore | None = None,
    ):
        self.settings = settings
        self.repository = repository
        self.responder = responder
        self.codex_store = codex_store

    def build(self) -> Application:
        app = Application.builder().token(self.settings.telegram_bot_token).build()
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help))
        app.add_handler(CommandHandler("whoami", self.whoami))
        app.add_handler(CommandHandler("claim", self.claim))
        app.add_handler(CommandHandler("projects", self.projects))
        app.add_handler(CommandHandler("sessions", self.sessions))
        app.add_handler(CommandHandler("new", self.new_session))
        app.add_handler(CommandHandler("rename", self.rename_session))
        app.add_handler(CommandHandler("status", self.status))
        app.add_handler(CallbackQueryHandler(self.on_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_message))
        return app

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._require_authorized(update):
            return
        await self._ensure_state(update)
        await update.effective_message.reply_text(
            "已经连接。你可以直接发消息，或用 /projects 选择项目，用 /sessions 切换会话。"
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._require_authorized(update):
            return
        await update.effective_message.reply_text(
            "\n".join(
                [
                    "可用命令：",
                    "/projects - 选择项目",
                    "/sessions - 选择当前项目里的 Codex 桌面会话",
                    "/new 标题 - 新建会话",
                    "/rename 标题 - 重命名当前会话",
                    "/status - 查看当前项目和会话",
                    "/whoami - 查看 Telegram user id",
                ]
            )
        )

    async def whoami(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None:
            return
        await update.effective_message.reply_text(f"你的 Telegram user id 是：{user.id}")

    async def claim(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None:
            return
        token = " ".join(context.args).strip()
        if not self.settings.setup_token:
            await update.effective_message.reply_text(
                "这台 Bot 没有启用 /claim。请配置 TELEGRAM_ALLOWED_USER_IDS。"
            )
            return
        if token != self.settings.setup_token:
            await update.effective_message.reply_text("授权码不正确。")
            logger.warning("Rejected claim attempt from Telegram user id %s", user.id)
            return
        self.repository.add_or_update_user(
            user_id=user.id,
            username=user.username,
            display_name=user.full_name,
        )
        await self._ensure_state(update)
        await update.effective_message.reply_text("授权完成。以后你可以直接和我对话。")

    async def projects(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._require_authorized(update):
            return
        await self._send_project_picker(update)

    async def sessions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._require_authorized(update):
            return
        state = await self._ensure_state(update)
        await self._send_session_picker(update, project_id=state.project_id)

    async def new_session(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._require_authorized(update):
            return
        user = update.effective_user
        if user is None:
            return
        state = await self._ensure_state(update)
        title = " ".join(context.args).strip() or "New chat"
        session = self.repository.create_session(
            user_id=user.id,
            project_id=state.project_id,
            title=title,
        )
        await update.effective_message.reply_text(
            f"已新建会话：{escape(session.title)}",
            parse_mode=ParseMode.HTML,
        )

    async def rename_session(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._require_authorized(update):
            return
        state = await self._ensure_state(update)
        title = " ".join(context.args).strip()
        if not title:
            await update.effective_message.reply_text("用法：/rename 新标题")
            return
        self.repository.rename_session(session_id=state.session_id, title=title)
        await update.effective_message.reply_text(
            f"已重命名为：{escape(title[:120])}",
            parse_mode=ParseMode.HTML,
        )

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._require_authorized(update):
            return
        state = await self._ensure_state(update)
        project = self.repository.get_project(state.project_id)
        session = self.repository.get_session(state.session_id)
        project_name = project["name"] if project else state.project_id
        session_title = session.title if session else state.session_id
        await update.effective_message.reply_text(
            f"当前项目：{project_name}\n当前会话：{session_title}\n模型：{self.settings.openai_model}"
        )

    async def on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._require_authorized(update):
            return
        query = update.callback_query
        if query is None or query.data is None or update.effective_user is None:
            return
        await query.answer()
        kind, _, value = query.data.partition(":")
        if kind == "project":
            state = self.repository.set_current_project(
                user_id=update.effective_user.id,
                project_id=value,
            )
            project = self.repository.get_project(state.project_id)
            await query.edit_message_text(f"已切换项目：{project['name'] if project else value}")
            return
        if kind == "session":
            session = self.repository.get_session(value)
            if session is None:
                await query.edit_message_text("这个会话不存在。")
                return
            self.repository.set_current_session(user_id=update.effective_user.id, session_id=value)
            await query.edit_message_text(f"已切换会话：{session.title}")
            return
        if kind == "codex":
            thread = self.codex_store.get_thread(value) if self.codex_store else None
            if thread is None:
                await query.edit_message_text("这个 Codex 会话不存在或暂时无法读取。")
                return
            state = await self._ensure_state(update)
            session = self.repository.get_or_create_codex_session(
                user_id=update.effective_user.id,
                project_id=state.project_id,
                codex_thread_id=thread.id,
                title=thread.title,
            )
            await query.edit_message_text(
                f"已连接 Codex 会话：{session.title}\n"
                "之后手机消息会读取并追加到这个 Codex 会话。"
            )
            return
        if kind == "sessions":
            await query.edit_message_text(
                "选择会话：",
                reply_markup=self._session_markup(update.effective_user.id, value),
            )
            return

    async def on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._require_authorized(update):
            return
        message = update.effective_message
        user = update.effective_user
        if message is None or user is None or not message.text:
            return

        state = await self._ensure_state(update)
        project = self.repository.get_project(state.project_id)
        session = self.repository.get_session(state.session_id)
        if project is None:
            await message.reply_text("当前项目不存在，请用 /projects 重新选择。")
            return

        await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
        self.repository.append_message(
            session_id=state.session_id,
            role="user",
            content=message.text,
        )

        if session and session.codex_thread_id and self.codex_store:
            history = self.codex_store.recent_messages(
                thread_id=session.codex_thread_id,
                limit=self.settings.max_history_messages,
            )
        else:
            history = self.repository.recent_messages(
                session_id=state.session_id,
                limit=self.settings.max_history_messages,
            )
        try:
            answer = await self.responder.reply(
                project_name=project["name"],
                project_path=project["path"],
                project_prompt=project["system_prompt"],
                history=history[:-1],
                user_message=message.text,
            )
        except Exception:
            logger.exception("OpenAI response failed")
            await message.reply_text("这次调用失败了。我已经把错误写进日志，稍后可以重试。")
            return

        self.repository.append_message(
            session_id=state.session_id,
            role="assistant",
            content=answer,
        )
        if session and session.codex_thread_id and self.codex_store:
            self.codex_store.append_exchange(
                thread_id=session.codex_thread_id,
                user_text=message.text,
                assistant_text=answer,
            )
        for chunk in chunk_text(answer):
            await message.reply_text(chunk)

    async def _require_authorized(self, update: Update) -> bool:
        user = update.effective_user
        message = update.effective_message
        if user is None or message is None:
            return False
        if user.id in self.settings.allowed_user_ids or self.repository.has_user(user.id):
            self.repository.add_or_update_user(
                user_id=user.id,
                username=user.username,
                display_name=user.full_name,
            )
            return True
        await message.reply_text(
            "这个 Bot 是私有的。发送 /whoami 查看你的 user id，"
            "然后把它加入 TELEGRAM_ALLOWED_USER_IDS。"
        )
        return False

    async def _ensure_state(self, update: Update):
        user = update.effective_user
        if user is None:
            raise RuntimeError("Missing Telegram user")
        return self.repository.ensure_state(user.id)

    async def _send_project_picker(self, update: Update) -> None:
        projects = self.repository.list_projects()
        buttons = [
            [InlineKeyboardButton(project["name"], callback_data=f"project:{project['id']}")]
            for project in projects
        ]
        await update.effective_message.reply_text(
            "选择项目：",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    async def _send_session_picker(self, update: Update, *, project_id: str) -> None:
        await update.effective_message.reply_text(
            "选择会话：",
            reply_markup=self._session_markup(update.effective_user.id, project_id),
        )

    def _session_markup(self, user_id: int, project_id: str) -> InlineKeyboardMarkup:
        project = self.repository.get_project(project_id)
        if self.codex_store and project is not None:
            project_path = project["path"]
            threads = self.codex_store.list_threads_for_path(
                Path(project_path) if project_path else None,
            )
            if threads:
                return InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                compact_label(thread.title),
                                callback_data=f"codex:{thread.id}",
                            )
                        ]
                        for thread in threads
                    ]
                )

        sessions = self.repository.list_sessions(user_id=user_id, project_id=project_id)
        buttons = [
            [
                InlineKeyboardButton(
                    compact_label(session.title),
                    callback_data=f"session:{session.id}",
                )
            ]
            for session in sessions
        ]
        if not buttons:
            buttons = [
                [
                    InlineKeyboardButton(
                        "还没有会话，先用 /new 新建",
                        callback_data=f"noop:{project_id}",
                    )
                ]
            ]
        return InlineKeyboardMarkup(buttons)
