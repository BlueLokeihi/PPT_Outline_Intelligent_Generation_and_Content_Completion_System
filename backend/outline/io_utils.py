from __future__ import annotations

from pathlib import Path


def read_topic_text(path: str, *, encoding: str = "utf-8") -> str:
    return Path(path).read_text(encoding=encoding)


def maybe_truncate(text: str, *, max_chars: int) -> str:
    if max_chars <= 0:
        return text
    if len(text) <= max_chars:
        return text

    head = text[: max_chars // 2]
    tail = text[-(max_chars // 2) :]
    return head + "\n\n[...内容过长已截断...请在生成时以整体结构为主]\n\n" + tail
