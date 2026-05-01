"""BM25 词法检索：jieba 分词 + rank_bm25。

- 分词：中文用 jieba.cut_for_search（搜索引擎分词，召回更全），英文按字母段拆并小写
- 索引落盘：tokens.jsonl（每行 = 一个 chunk 的 token 列表）
- 加载：从 tokens.jsonl 重建 BM25Okapi（重建很快，无需 pickle 整个对象）
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import jieba
from rank_bm25 import BM25Okapi


# 关闭 jieba 启动日志
jieba.setLogLevel(60)


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[一-鿿]")


def tokenize(text: str) -> List[str]:
    """中英混合分词。

    - 中文：jieba 搜索引擎模式
    - 英文/数字：按 \\w+ 切，小写化
    - 长度 < 2 的中文字符也保留（数字、年份）
    """
    if not text:
        return []
    text = text.lower()
    tokens: List[str] = []
    # 先把英文/数字串单独抽出，避免被 jieba 切碎
    for piece in re.split(r"([A-Za-z0-9_\.\-]+)", text):
        if not piece:
            continue
        if re.fullmatch(r"[A-Za-z0-9_\.\-]+", piece):
            # 英文/数字段：按非字母数字分隔
            tokens.extend([t for t in re.split(r"[\.\-_]+", piece) if t])
        else:
            # 中文段：jieba search 模式
            for tok in jieba.cut_for_search(piece):
                tok = tok.strip()
                if tok and not tok.isspace():
                    tokens.append(tok)
    return tokens


@dataclass
class Bm25Hit:
    score: float
    doc_id: int


class Bm25Index:
    """单 corpus 的 BM25 索引。"""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.tokens_path = self.root / "tokens.jsonl"
        self._bm25: Optional[BM25Okapi] = None
        self._size: int = 0

    # ---- 写 -----------------------------------------------------------
    def build(self, texts: List[str]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.tokens_path.open("w", encoding="utf-8") as f:
            for t in texts:
                f.write(json.dumps(tokenize(t), ensure_ascii=False) + "\n")

    # ---- 读 -----------------------------------------------------------
    def _load(self) -> None:
        if self._bm25 is not None:
            return
        if not self.tokens_path.exists():
            raise FileNotFoundError(f"BM25 tokens 文件不存在: {self.tokens_path}")
        corpus: List[List[str]] = []
        for line in self.tokens_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                corpus.append(json.loads(line))
        if not corpus:
            raise RuntimeError("BM25 索引为空")
        self._bm25 = BM25Okapi(corpus)
        self._size = len(corpus)

    def search(self, query: str, *, k: int = 5) -> List[Bm25Hit]:
        self._load()
        assert self._bm25 is not None
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        scores = self._bm25.get_scores(q_tokens)
        # 取 top-k
        idx = scores.argsort()[::-1][:k]
        return [Bm25Hit(score=float(scores[i]), doc_id=int(i)) for i in idx if scores[i] > 0]

    @property
    def size(self) -> int:
        self._load()
        return self._size
