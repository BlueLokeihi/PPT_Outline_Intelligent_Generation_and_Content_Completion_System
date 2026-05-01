"""统一检索器：vector / bm25 / hybrid 三种模式。

hybrid 用 RRF (Reciprocal Rank Fusion) 融合两路排名：
    rrf_score(d) = sum_over_paths(1 / (rrf_k + rank_in_path(d)))
不需要把 vector 余弦和 BM25 分数归一化到同一量纲。

设计上：检索结果统一返回 RetrievedChunk，包含原文 + 元数据 + 分数 + 来自哪条路径。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import numpy as np

from .bm25 import Bm25Index
from .embedder import EmbedConfig, embed_texts, normalize_rows
from .store import VectorStore


Mode = Literal["vector", "bm25", "hybrid"]


@dataclass
class RetrievedChunk:
    score: float           # 最终融合分（hybrid 是 RRF 分；vector 是余弦；bm25 是 BM25 原始分）
    text: str
    source: str
    chunk_index: int
    char_start: int
    char_end: int
    vector_rank: Optional[int] = None    # 在向量召回里的名次（1-based），未命中为 None
    bm25_rank: Optional[int] = None      # 同上
    vector_score: Optional[float] = None
    bm25_score: Optional[float] = None


class HybridRetriever:
    """共享同一个 corpus 目录下的 FAISS + BM25 索引。"""

    def __init__(self, corpus_dir: Path) -> None:
        self.store = VectorStore(corpus_dir)
        self.bm25 = Bm25Index(corpus_dir)
        self._metas: Optional[List[Dict[str, Any]]] = None

    # ---- 工具：缓存读 metas，避免每次 search 都重读 ----
    def _load_metas(self) -> List[Dict[str, Any]]:
        if self._metas is None:
            self._metas = self.store._load_metas()  # 复用 store 内部读取
        return self._metas

    def _build_chunk(self, doc_id: int) -> RetrievedChunk:
        m = self._load_metas()[doc_id]
        return RetrievedChunk(
            score=0.0,
            text=str(m.get("text", "")),
            source=str(m.get("source", "")),
            chunk_index=int(m.get("chunk_index", -1)),
            char_start=int(m.get("char_start", 0)),
            char_end=int(m.get("char_end", 0)),
        )

    # ---- 单路：vector ----
    def _retrieve_vector(
        self, query: str, *, k: int, embed_cfg: EmbedConfig
    ) -> List[tuple[int, float]]:
        qvec = embed_texts([query], cfg=embed_cfg, cache=None, verbose=False)
        qvec = normalize_rows(qvec)
        # 直接用 FAISS 拿 (doc_id, score)
        import faiss
        index = faiss.read_index(str(self.store.index_path))
        scores, ids = index.search(qvec.astype(np.float32), k)
        out: List[tuple[int, float]] = []
        for s, i in zip(scores[0].tolist(), ids[0].tolist()):
            if i >= 0:
                out.append((int(i), float(s)))
        return out

    # ---- 单路：bm25 ----
    def _retrieve_bm25(self, query: str, *, k: int) -> List[tuple[int, float]]:
        return [(h.doc_id, h.score) for h in self.bm25.search(query, k=k)]

    # ---- 主入口 ----
    def search(
        self,
        query: str,
        *,
        mode: Mode = "hybrid",
        k: int = 5,
        recall_k: int = 20,
        rrf_k: int = 60,
        embed_cfg: Optional[EmbedConfig] = None,
    ) -> List[RetrievedChunk]:
        """检索。

        - mode=vector：仅向量；返回 top-k（按余弦降序）
        - mode=bm25：仅 BM25；返回 top-k（按 BM25 分降序）
        - mode=hybrid：两路各召 recall_k → RRF 融合 → 返回 top-k
        """
        if mode == "vector":
            if embed_cfg is None:
                raise ValueError("vector/hybrid 模式需要 embed_cfg")
            hits = self._retrieve_vector(query, k=k, embed_cfg=embed_cfg)
            out: List[RetrievedChunk] = []
            for rank, (doc_id, score) in enumerate(hits, 1):
                c = self._build_chunk(doc_id)
                c.score = score
                c.vector_rank = rank
                c.vector_score = score
                out.append(c)
            return out

        if mode == "bm25":
            hits = self._retrieve_bm25(query, k=k)
            out = []
            for rank, (doc_id, score) in enumerate(hits, 1):
                c = self._build_chunk(doc_id)
                c.score = score
                c.bm25_rank = rank
                c.bm25_score = score
                out.append(c)
            return out

        # hybrid
        if embed_cfg is None:
            raise ValueError("hybrid 模式需要 embed_cfg")
        vec_hits = self._retrieve_vector(query, k=recall_k, embed_cfg=embed_cfg)
        bm25_hits = self._retrieve_bm25(query, k=recall_k)

        # 收集所有 doc_id 的两路排名/分数
        vec_rank: Dict[int, tuple[int, float]] = {
            doc_id: (rank, score) for rank, (doc_id, score) in enumerate(vec_hits, 1)
        }
        bm25_rank: Dict[int, tuple[int, float]] = {
            doc_id: (rank, score) for rank, (doc_id, score) in enumerate(bm25_hits, 1)
        }

        all_ids = set(vec_rank.keys()) | set(bm25_rank.keys())
        fused: List[tuple[int, float]] = []
        for doc_id in all_ids:
            score = 0.0
            if doc_id in vec_rank:
                score += 1.0 / (rrf_k + vec_rank[doc_id][0])
            if doc_id in bm25_rank:
                score += 1.0 / (rrf_k + bm25_rank[doc_id][0])
            fused.append((doc_id, score))
        fused.sort(key=lambda x: x[1], reverse=True)

        out = []
        for doc_id, rrf_score in fused[:k]:
            c = self._build_chunk(doc_id)
            c.score = rrf_score
            if doc_id in vec_rank:
                c.vector_rank, c.vector_score = vec_rank[doc_id]
            if doc_id in bm25_rank:
                c.bm25_rank, c.bm25_score = bm25_rank[doc_id]
            out.append(c)
        return out
