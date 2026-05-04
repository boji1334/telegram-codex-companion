TELEGRAM_MESSAGE_LIMIT = 4096


def chunk_text(text: str, *, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    if not text:
        return [""]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = remaining.rfind(" ", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def compact_label(text: str, *, limit: int = 48) -> str:
    text = " ".join(text.strip().split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
