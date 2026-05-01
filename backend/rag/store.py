"""FAISS 向量库读写 + 元数据。

每个 corpus 一个目录：
  index.faiss        FAISS 平铺索引（IndexFlatIP，向量已 L2 归一化）
  meta.jsonl         每行一个 chunk 的元数据 + 原文
  manifest.json      索引信息（embedding 模型、dim、size、构建时间）
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass
class SearchHit:
    score: float
    text: str
    source: str
    chunk_index: int
    char_start: int
    char_end: int


class VectorStore:
    """单 corpus 的索引读写。"""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.index_path = self.root / "index.faiss"
        self.meta_path = self.root / "meta.jsonl"
        self.manifest_path = self.root / "manifest.json"

    # ---- 写 -----------------------------------------------------------
    def build(
        self,
        *,
        vectors: np.ndarray,
        metas: List[Dict[str, Any]],
        embedding_model: str,
    ) -> None:
        if vectors.shape[0] != len(metas):
            raise ValueError(f"vectors ({vectors.shape[0]}) 与 metas ({len(metas)}) 数量不一致")
        if vectors.size == 0:
            raise ValueError("无向量可入库")
        import faiss

        self.root.mkdir(parents=True, exist_ok=True)
        dim = int(vectors.shape[1])
        index = faiss.IndexFlatIP(dim)
        index.add(vectors.astype(np.float32))
        faiss.write_index(index, str(self.index_path))

        with self.meta_path.open("w", encoding="utf-8") as f:
            for m in metas:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")

        manifest = {
            "embedding_model": embedding_model,
            "dim": dim,
            "size": int(vectors.shape[0]),
            "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ---- 读 -----------------------------------------------------------
    def load_manifest(self) -> Dict[str, Any]:
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"manifest 不存在: {self.manifest_path}")
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def _load_index(self) -> Any:
        import faiss

        if not self.index_path.exists():
            raise FileNotFoundError(f"索引文件不存在: {self.index_path}")
        return faiss.read_index(str(self.index_path))

    def _load_metas(self) -> List[Dict[str, Any]]:
        if not self.meta_path.exists():
            raise FileNotFoundError(f"meta 文件不存在: {self.meta_path}")
        out: List[Dict[str, Any]] = []
        for line in self.meta_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out

    def search(self, query_vec: np.ndarray, *, k: int = 5) -> List[SearchHit]:
        if query_vec.ndim == 1:
            query_vec = query_vec[None, :]
        index = self._load_index()
        metas = self._load_metas()
        scores, ids = index.search(query_vec.astype(np.float32), k)
        hits: List[SearchHit] = []
        for score, idx in zip(scores[0].tolist(), ids[0].tolist()):
            if idx < 0 or idx >= len(metas):
                continue
            m = metas[idx]
            hits.append(
                SearchHit(
                    score=float(score),
                    text=str(m.get("text", "")),
                    source=str(m.get("source", "")),
                    chunk_index=int(m.get("chunk_index", -1)),
                    char_start=int(m.get("char_start", 0)),
                    char_end=int(m.get("char_end", 0)),
                )
            )
        return hits


def corpus_path(corpus_id: str, *, base: Optional[Path] = None) -> Path:
    """约定的 corpus 索引存放路径：backend/rag/indexes/<corpus_id>/"""
    base = base or Path(__file__).resolve().parent / "indexes"
    return base / corpus_id
