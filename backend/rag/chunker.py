"""文档加载与切块。

支持 .txt / .md / .pdf；按"双换行 → 句号 → 字符"递归切分，
默认 chunk_size=500、overlap=80，每个块附带元数据。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List


SUPPORTED_EXTS = {".txt", ".md", ".pdf"}


@dataclass
class Chunk:
    text: str
    source: str        # 相对 corpus 根的路径
    chunk_index: int   # 在该源文件中的序号
    char_start: int    # 在源文件清洗后文本中的起始位置
    char_end: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "source": self.source,
            "chunk_index": self.chunk_index,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts: List[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            parts.append("")
    return "\n\n".join(parts)


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def load_document(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _read_pdf(path)
    if ext in {".txt", ".md"}:
        return _read_text_file(path)
    raise ValueError(f"unsupported file type: {path}")


def _normalize(text: str) -> str:
    # 统一换行；折叠 3+ 空行；去掉行尾空白
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_recursive(text: str, chunk_size: int, overlap: int) -> List[tuple[int, int, str]]:
    """递归切分。返回 (start, end, segment) 列表。

    优先级：双换行 > 单换行 > 中英文句号/问号/感叹号 > 空格 > 字符。
    每层只用一个 separator；某段仍超长则用"剩余 separators"递归，避免死循环。
    """
    if len(text) <= chunk_size:
        return [(0, len(text), text)]

    separators = ["\n\n", "\n", "。", ".", "！", "!", "？", "?", " "]

    def _hard_split(seg: str, base: int) -> List[tuple[int, int, str]]:
        return [
            (base + i, base + min(i + chunk_size, len(seg)), seg[i : i + chunk_size])
            for i in range(0, len(seg), chunk_size)
        ]

    def _split(seg: str, base: int, seps: List[str]) -> List[tuple[int, int, str]]:
        if len(seg) <= chunk_size:
            return [(base, base + len(seg), seg)]
        for i, sep in enumerate(seps):
            if sep not in seg:
                continue
            pieces: List[tuple[int, int, str]] = []
            cursor = 0
            for part in _greedy_join(seg, sep, chunk_size):
                pieces.append((base + cursor, base + cursor + len(part), part))
                cursor += len(part)
            out: List[tuple[int, int, str]] = []
            remaining = seps[i + 1 :]
            for s, e, p in pieces:
                if len(p) > chunk_size:
                    if remaining:
                        out.extend(_split(p, s, remaining))
                    else:
                        out.extend(_hard_split(p, s))
                else:
                    out.append((s, e, p))
            return out
        return _hard_split(seg, base)

    raw = _split(text, 0, separators)
    return _apply_overlap(raw, text, overlap)


def _greedy_join(text: str, sep: str, chunk_size: int) -> List[str]:
    """按 sep 切分后，贪心合并到接近 chunk_size 的块。保留 sep 在前一段尾部。"""
    parts = text.split(sep)
    out: List[str] = []
    buf = ""
    for i, part in enumerate(parts):
        piece = part + (sep if i < len(parts) - 1 else "")
        if not buf:
            buf = piece
            continue
        if len(buf) + len(piece) <= chunk_size:
            buf += piece
        else:
            out.append(buf)
            buf = piece
    if buf:
        out.append(buf)
    return out


def _apply_overlap(
    pieces: List[tuple[int, int, str]], full_text: str, overlap: int
) -> List[tuple[int, int, str]]:
    if overlap <= 0 or len(pieces) <= 1:
        return pieces
    out: List[tuple[int, int, str]] = []
    for idx, (s, e, _p) in enumerate(pieces):
        new_s = max(0, s - overlap) if idx > 0 else s
        out.append((new_s, e, full_text[new_s:e]))
    return out


def chunk_document(
    text: str,
    *,
    source: str,
    chunk_size: int = 500,
    overlap: int = 80,
) -> List[Chunk]:
    cleaned = _normalize(text)
    if not cleaned:
        return []
    raw = _split_recursive(cleaned, chunk_size=chunk_size, overlap=overlap)
    chunks: List[Chunk] = []
    for i, (s, e, seg) in enumerate(raw):
        seg = seg.strip()
        if not seg:
            continue
        chunks.append(Chunk(text=seg, source=source, chunk_index=i, char_start=s, char_end=e))
    return chunks


def iter_corpus_files(corpus_dir: Path) -> Iterable[Path]:
    for p in sorted(corpus_dir.rglob("*")):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            yield p


def chunk_corpus(
    corpus_dir: Path,
    *,
    chunk_size: int = 500,
    overlap: int = 80,
) -> List[Chunk]:
    all_chunks: List[Chunk] = []
    for path in iter_corpus_files(corpus_dir):
        try:
            text = load_document(path)
        except Exception as e:
            print(f"[WARN] 跳过无法解析的文件 {path}: {e}")
            continue
        rel = path.relative_to(corpus_dir).as_posix()
        all_chunks.extend(
            chunk_document(text, source=rel, chunk_size=chunk_size, overlap=overlap)
        )
    return all_chunks
