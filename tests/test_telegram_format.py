from pocket_codex.telegram_format import markdown_to_telegram_html, telegram_html_chunks


def test_markdown_to_telegram_html_renders_common_markdown() -> None:
    html = markdown_to_telegram_html(
        "## 标题\n\n**重点** 和 `code`\n\n- 第一条\n- 第二条\n\n---"
    )

    assert "<b>标题</b>" in html
    assert "<b>重点</b>" in html
    assert "<code>code</code>" in html
    assert "• 第一条" in html
    assert "---" not in html


def test_telegram_html_chunks_escape_unsafe_text() -> None:
    chunks = telegram_html_chunks("看看 <script> & **加粗**")

    assert len(chunks) == 1
    assert "&lt;script&gt;" in chunks[0]
    assert "&amp;" in chunks[0]
    assert "<b>加粗</b>" in chunks[0]
