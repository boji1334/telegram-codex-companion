from __future__ import annotations

import re
from html import escape, unescape

from .text import chunk_text

TELEGRAM_HTML_LIMIT = 4096
TELEGRAM_HTML_SAFE_LIMIT = 3400


def telegram_html_chunks(text: str, *, limit: int = TELEGRAM_HTML_SAFE_LIMIT) -> list[str]:
    chunks: list[str] = []
    for raw_chunk in chunk_text(text, limit=limit):
        html = markdown_to_telegram_html(raw_chunk)
        if len(html) <= TELEGRAM_HTML_LIMIT:
            chunks.append(html)
            continue
        for smaller_chunk in chunk_text(raw_chunk, limit=max(500, limit // 2)):
            chunks.append(markdown_to_telegram_html(smaller_chunk))
    return chunks or [""]


def markdown_to_telegram_html(text: str) -> str:
    blocks = _split_code_fences(text)
    rendered: list[str] = []
    for is_code, block in blocks:
        if is_code:
            rendered.append(f"<pre><code>{escape(block.strip())}</code></pre>")
        else:
            rendered.append(_render_plain_block(block))
    return "\n".join(part for part in rendered if part).strip()


def html_to_plain_text(html: str) -> str:
    text = re.sub(r"</?(?:b|strong|i|em|u|s|code|pre)>", "", html)
    return unescape(text)


def _split_code_fences(text: str) -> list[tuple[bool, str]]:
    blocks: list[tuple[bool, str]] = []
    cursor = 0
    pattern = re.compile(r"```[^\n]*\n?(.*?)```", re.DOTALL)
    for match in pattern.finditer(text):
        if match.start() > cursor:
            blocks.append((False, text[cursor : match.start()]))
        blocks.append((True, match.group(1)))
        cursor = match.end()
    if cursor < len(text):
        blocks.append((False, text[cursor:]))
    return blocks


def _render_plain_block(block: str) -> str:
    lines: list[str] = []
    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        if stripped in {"---", "***", "___"}:
            lines.append("")
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            lines.append(f"<b>{_render_inline(heading.group(2))}</b>")
            continue

        bullet = re.match(r"^(\s*)[-*]\s+(.+)$", line)
        if bullet:
            indent = " " * (len(bullet.group(1)) // 2)
            lines.append(f"{indent}• {_render_inline(bullet.group(2))}")
            continue

        lines.append(_render_inline(line))
    return "\n".join(lines).strip()


def _render_inline(text: str) -> str:
    escaped = escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"__(.+?)__", r"<b>\1</b>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", escaped)
    return escaped
