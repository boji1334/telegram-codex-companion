from __future__ import annotations

import base64
import binascii
import logging
import mimetypes
from html import escape
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlparse

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
from .repository import MessageRecord, Repository
from .text import chunk_text, compact_label

logger = logging.getLogger(__name__)
MAX_HISTORY_IMAGE_SIDE = 1280
HISTORY_IMAGE_JPEG_QUALITY = 82


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
        app.add_handler(CommandHandler("history", self.history))
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

    async def history(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._require_authorized(update):
            return
        state = await self._ensure_state(update)
        session = self.repository.get_session(state.session_id)
        if session is None:
            await update.effective_message.reply_text("当前没有选中的会话。")
            return

        attach_full = bool(context.args and context.args[0].lower() == "all")
        inline_recent = not attach_full
        limit = self.settings.telegram_history_on_open_messages
        if context.args and context.args[0].isdigit():
            limit = max(
                1,
                min(
                    int(context.args[0]),
                    self.settings.telegram_history_export_max_messages,
                ),
            )

        await self._send_session_history(
            update.effective_message,
            session=session,
            limit=limit,
            attach_full=attach_full,
            inline_recent=inline_recent,
        )

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
            await self._send_session_history(
                query.message,
                session=session,
                limit=self.settings.telegram_history_on_open_messages,
                attach_full=True,
                inline_recent=False,
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

    async def _send_session_history(
        self,
        message,
        *,
        session,
        limit: int,
        attach_full: bool,
        inline_recent: bool,
    ) -> None:
        if not session.codex_thread_id or not self.codex_store:
            await message.reply_text("这个会话还没有连接 Codex 桌面历史。")
            return

        recent = self.codex_store.recent_messages(
            thread_id=session.codex_thread_id,
            limit=limit,
        )
        if not recent:
            await message.reply_text("这个 Codex 会话暂时没有可加载的历史。")
            return

        if inline_recent:
            title = f"已加载 Codex 历史：{session.title}"
            body = self._format_transcript(recent)
            for chunk in chunk_text(f"{title}\n最近 {len(recent)} 条：\n\n{body}", limit=3500):
                await message.reply_text(chunk)
        else:
            await message.reply_text(
                f"已连接 Codex 会话：{session.title}\n"
                "完整历史已整理成左右气泡版 HTML，打开附件查看。"
            )

        if attach_full:
            full_messages = self.codex_store.messages(
                thread_id=session.codex_thread_id,
                limit=self.settings.telegram_history_export_max_messages,
            )
            export_path = self._write_history_export(
                session_title=session.title,
                thread_id=session.codex_thread_id,
                messages=full_messages,
            )
            caption = f"左右气泡历史：{session.title}（{len(full_messages)} 条）"
            with export_path.open("rb") as file:
                await message.reply_document(
                    document=file,
                    filename=export_path.name,
                    caption=caption,
                )

    def _write_history_export(
        self,
        *,
        session_title: str,
        thread_id: str,
        messages: list[MessageRecord],
    ) -> Path:
        export_dir = self.settings.data_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        export_path = export_dir / f"codex-history-{thread_id}.html"
        export_path.write_text(
            self._format_html_transcript(session_title, messages),
            encoding="utf-8",
        )
        return export_path

    @staticmethod
    def _format_transcript(messages: list[MessageRecord]) -> str:
        blocks: list[str] = []
        for index, record in enumerate(messages, start=1):
            label = "Codex" if record.role == "assistant" else "你（电脑）"
            content = record.content.strip()
            if record.role == "user" and content.startswith("[Telegram]\n"):
                label = "你（手机）"
                content = content.removeprefix("[Telegram]\n").strip()
            if record.images:
                content = f"{content}\n[图片 {len(record.images)} 张]".strip()
            blocks.append(f"## {index}. {label}\n{content}")
        return "\n\n".join(blocks)

    @staticmethod
    def _format_html_transcript(session_title: str, messages: list[MessageRecord]) -> str:
        bubbles: list[str] = []
        image_cache: dict[str, str | None] = {}
        for record in messages:
            role_class = "assistant" if record.role == "assistant" else "user"
            label = "Codex" if record.role == "assistant" else "你（电脑）"
            content = record.content.strip()
            if record.role == "user" and content.startswith("[Telegram]\n"):
                label = "你（手机）"
                content = content.removeprefix("[Telegram]\n").strip()
            bubble_parts = [
                f'<article class="bubble {role_class}">',
                f'  <div class="meta">{escape(label)}</div>',
            ]
            if content:
                message_text = escape(content).replace(chr(10), "<br>")
                bubble_parts.append(
                    f'  <div class="message-text">{message_text}</div>'
                )
            bubble_parts.extend(_format_image_gallery(record.images, image_cache))
            bubble_parts.append("</article>")
            bubbles.append(
                "\n".join(bubble_parts)
            )

        return "\n".join(
            [
                "<!doctype html>",
                '<html lang="zh-CN">',
                "<head>",
                '<meta charset="utf-8">',
                '<meta name="viewport" content="width=device-width, initial-scale=1">',
                f"<title>{escape(session_title)}</title>",
                "<style>",
                (
                    "body{margin:0;background:#dfeec7;font:16px/1.55 "
                    "-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#111;}"
                ),
                ".page{max-width:980px;margin:0 auto;padding:24px 18px 48px;}",
                "h1{font-size:20px;margin:0 0 18px;text-align:center;}",
                (
                    ".bubble{max-width:72%;box-sizing:border-box;margin:10px 0;"
                    "padding:12px 14px;border-radius:12px;"
                    "box-shadow:0 1px 1px rgba(0,0,0,.08);white-space:normal;}"
                ),
                ".assistant{background:#fff;margin-right:auto;border-top-left-radius:4px;}",
                ".user{background:#d8f7c5;margin-left:auto;border-top-right-radius:4px;}",
                ".meta{font-size:12px;color:#667;margin-bottom:6px;font-weight:600;}",
                ".message-text{overflow-wrap:anywhere;}",
                (
                    ".image-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));"
                    "gap:8px;margin-top:9px;}"
                ),
                (
                    ".image-grid img{display:block;width:100%;height:auto;max-height:72vh;"
                    "object-fit:contain;border-radius:10px;border:1px solid rgba(0,0,0,.08);"
                    "background:#f7f7f7;}"
                ),
                (
                    ".missing-image{font-size:12px;color:#7a5b00;background:#fff8d6;"
                    "border:1px solid #eedb8a;border-radius:8px;padding:8px;}"
                ),
                "pre,code{white-space:pre-wrap;word-break:break-word;}",
                "@media(max-width:640px){.bubble{max-width:92%;}.page{padding:14px 10px 32px;}}",
                "</style>",
                "</head>",
                "<body>",
                '<main class="page">',
                f"<h1>{escape(session_title)}</h1>",
                *bubbles,
                "</main>",
                "</body>",
                "</html>",
            ]
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


def _format_image_gallery(
    images: tuple[str, ...],
    image_cache: dict[str, str | None],
) -> list[str]:
    tags: list[str] = []
    for image_ref in images:
        if image_ref not in image_cache:
            image_cache[image_ref] = _image_ref_to_html_src(image_ref)
        src = image_cache[image_ref]
        if src:
            tags.append(
                f'    <img src="{escape(src, quote=True)}" alt="conversation image" loading="lazy">'
            )
        else:
            tags.append(
                f'    <div class="missing-image">图片暂时无法读取：'
                f"{escape(_short_image_ref(image_ref))}</div>"
            )
    if not tags:
        return []
    return ["  <div class=\"image-grid\">", *tags, "  </div>"]


def _image_ref_to_html_src(image_ref: str) -> str | None:
    if image_ref.startswith("data:image/"):
        return _thumbnail_data_url_from_data_url(image_ref) or image_ref
    if image_ref.startswith(("http://", "https://")):
        return image_ref

    path = _path_from_image_ref(image_ref)
    if path is None or not path.is_file():
        return None
    return _data_url_from_local_image(path)


def _thumbnail_data_url_from_data_url(data_url: str) -> str | None:
    parsed = _parse_data_url(data_url)
    if parsed is None:
        return None
    mime_type, raw = parsed
    return _thumbnail_data_url(raw, mime_type=mime_type)


def _data_url_from_local_image(path: Path) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None

    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    thumbnail = _thumbnail_data_url(raw, mime_type=mime_type)
    if thumbnail:
        return thumbnail
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _thumbnail_data_url(raw: bytes, *, mime_type: str) -> str | None:
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return None

    try:
        with Image.open(BytesIO(raw)) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((MAX_HISTORY_IMAGE_SIDE, MAX_HISTORY_IMAGE_SIDE))
            if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
                background = Image.new("RGB", image.size, "white")
                rgba = image.convert("RGBA")
                background.paste(rgba, mask=rgba.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")

            output = BytesIO()
            image.save(
                output,
                format="JPEG",
                quality=HISTORY_IMAGE_JPEG_QUALITY,
                optimize=True,
                progressive=True,
            )
    except Exception:
        return None

    thumbnail = output.getvalue()
    if mime_type in {"image/jpeg", "image/jpg"} and len(thumbnail) >= len(raw):
        return None
    return f"data:image/jpeg;base64,{base64.b64encode(thumbnail).decode('ascii')}"


def _parse_data_url(data_url: str) -> tuple[str, bytes] | None:
    header, separator, encoded = data_url.partition(",")
    if not separator or ";base64" not in header:
        return None
    mime_type = header.removeprefix("data:").split(";", maxsplit=1)[0] or "image/png"
    try:
        return mime_type, base64.b64decode(encoded, validate=False)
    except (binascii.Error, ValueError):
        return None


def _path_from_image_ref(image_ref: str) -> Path | None:
    if image_ref.startswith("file:"):
        parsed = urlparse(image_ref)
        raw_path = unquote(parsed.path)
        if raw_path.startswith("/") and len(raw_path) > 3 and raw_path[2] == ":":
            raw_path = raw_path[1:]
        return Path(raw_path)
    try:
        return Path(image_ref)
    except OSError:
        return None


def _short_image_ref(image_ref: str) -> str:
    if image_ref.startswith("data:image/"):
        return "内嵌图片数据"
    return image_ref if len(image_ref) <= 120 else f"{image_ref[:117]}..."
