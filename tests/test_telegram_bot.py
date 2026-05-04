from pocket_codex.repository import MessageRecord
from pocket_codex.telegram_bot import PocketCodexTelegramBot, _wait_text

IMAGE_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def test_html_transcript_embeds_images() -> None:
    html = PocketCodexTelegramBot._format_html_transcript(
        "Image History",
        [
            MessageRecord(
                role="user",
                content="看这张图",
                created_at="2026-05-04T00:00:00.000Z",
                images=(IMAGE_DATA_URL,),
            )
        ],
    )

    assert '<div class="image-grid">' in html
    assert '<img src="data:image/' in html
    assert "看这张图" in html


def test_wait_text_cycles_dots_without_timer() -> None:
    assert _wait_text(model="gpt-5.5", frame=0) == "Codex 正在思考.\n模型：gpt-5.5"
    assert _wait_text(model="gpt-5.5", frame=2) == "Codex 正在思考...\n模型：gpt-5.5"
