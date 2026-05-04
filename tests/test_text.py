from pocket_codex.text import chunk_text, compact_label


def test_chunk_text_splits_long_messages() -> None:
    chunks = chunk_text("hello " * 30, limit=25)

    assert len(chunks) > 1
    assert all(len(chunk) <= 25 for chunk in chunks)
    assert " ".join(chunks).replace("  ", " ") == ("hello " * 30).strip()


def test_compact_label_keeps_short_text() -> None:
    assert compact_label("  hello   world  ") == "hello world"


def test_compact_label_truncates_long_text() -> None:
    assert compact_label("a" * 80, limit=10) == "aaaaaaaaa…"

