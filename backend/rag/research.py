"""逐页研究：query 改写 + 多轮检索 + 结果聚合。

流程（每页独立）：
  1) 用 LLM 把页面上下文写成 2-3 条短 query
  2) 每条 query 跑一次混合检索（默认 hybrid），合并 + 去重 + RRF 排序
  3) 若召回质量低（最高一条 vector_score 低于阈值），用反馈 prompt 让 LLM 改写一轮，再检索一次合并

CLI 用法：
    python -m rag.research --corpus demo --outline path/to/outline.json
    python -m rag.research --corpus demo --outline path/to/outline.json --chapter 0 --page 1
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from llm.client import build_provider

from .embedder import EmbedConfig, load_embed_config
from .query_rewriter import (
    PageContext,
    RewriteResult,
    page_context_from_outline,
    rewrite_queries,
    rewrite_with_feedback,
)
from .retriever import HybridRetriever, RetrievedChunk
from .store import corpus_path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


# ---- 数据结构 -------------------------------------------------------------

@dataclass
class PageResearch:
    chapter_idx: int
    page_idx: int
    page_title: str
    rounds: List[Dict[str, Any]] = field(default_factory=list)
    final_chunks: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""


# ---- 召回质量判定 ---------------------------------------------------------

def _coverage_signal(chunks: List[RetrievedChunk]) -> float:
    """返回当前召回的"质量信号"：取最高的 vector_score（hybrid/vector 模式有效）。

    BM25-only 模式下 vector_score 全为 None，则取 bm25_score / 5.0 当替代信号
    （BM25 分数无上界，5.0 是经验"还可以"的下限）。
    """
    if not chunks:
        return 0.0
    vec_scores = [c.vector_score for c in chunks if c.vector_score is not None]
    if vec_scores:
        return max(vec_scores)
    bm_scores = [c.bm25_score for c in chunks if c.bm25_score is not None]
    if bm_scores:
        return max(bm_scores) / 5.0
    return 0.0


def _merge_chunks(
    by_query: Dict[str, List[RetrievedChunk]], *, top_n: int
) -> List[RetrievedChunk]:
    """跨多个 query 的结果聚合：每个 chunk 取它在各 query 里出现过的最高 score 与最佳 rank。"""
    best: Dict[tuple, RetrievedChunk] = {}
    for q, chunks in by_query.items():
        for c in chunks:
            key = (c.source, c.chunk_index)
            cur = best.get(key)
            if cur is None or c.score > cur.score:
                best[key] = c
    out = sorted(best.values(), key=lambda x: x.score, reverse=True)
    return out[:top_n]


# ---- 单页研究 -------------------------------------------------------------

def research_page(
    ctx: PageContext,
    *,
    retriever: HybridRetriever,
    embed_cfg: Optional[EmbedConfig],
    llm_client: Any,
    llm_model: str,
    mode: str = "hybrid",
    k: int = 6,
    recall_k: int = 20,
    rrf_k: int = 60,
    rewrite_threshold: float = 0.45,
    max_rounds: int = 2,
    verbose: bool = False,
) -> Dict[str, Any]:
    rounds: List[Dict[str, Any]] = []

    # ---- Round 1 ----------------------------------------------------
    rw1: RewriteResult = rewrite_queries(
        ctx, client=llm_client, model=llm_model, max_queries=3
    )
    if rw1.error or not rw1.queries:
        return {
            "rounds": rounds,
            "final_chunks": [],
            "error": f"首轮改写失败: {rw1.error or '无 query'}",
        }

    by_query: Dict[str, List[RetrievedChunk]] = {}
    for q in rw1.queries:
        hits = retriever.search(
            q, mode=mode, k=k, recall_k=recall_k, rrf_k=rrf_k, embed_cfg=embed_cfg
        )
        by_query[q] = hits

    merged = _merge_chunks(by_query, top_n=k)
    coverage = _coverage_signal(merged)

    rounds.append(
        {
            "round": 1,
            "queries": rw1.queries,
            "intent_tags": rw1.intent_tags,
            "coverage": round(coverage, 4),
            "per_query_hits": {
                q: [
                    {
                        "score": round(c.score, 4),
                        "vector_score": c.vector_score,
                        "bm25_score": c.bm25_score,
                        "source": c.source,
                        "chunk_index": c.chunk_index,
                        "snippet": c.text[:120],
                    }
                    for c in chunks
                ]
                for q, chunks in by_query.items()
            },
        }
    )

    if verbose:
        print(f"  Round1 queries={rw1.queries}  coverage={coverage:.3f}")

    # ---- Round 2（条件触发） ----------------------------------------
    if max_rounds >= 2 and coverage < rewrite_threshold:
        prev_snippets = [c.text[:200] for c in merged[:3]]
        rw2 = rewrite_with_feedback(
            ctx,
            prev_queries=rw1.queries,
            prev_top_snippets=prev_snippets,
            client=llm_client,
            model=llm_model,
            max_queries=3,
        )
        if rw2.queries:
            for q in rw2.queries:
                if q in by_query:
                    continue
                hits = retriever.search(
                    q, mode=mode, k=k, recall_k=recall_k, rrf_k=rrf_k, embed_cfg=embed_cfg
                )
                by_query[q] = hits
            merged = _merge_chunks(by_query, top_n=k)
            coverage_after = _coverage_signal(merged)
            rounds.append(
                {
                    "round": 2,
                    "queries": rw2.queries,
                    "intent_tags": rw2.intent_tags,
                    "coverage": round(coverage_after, 4),
                    "trigger_reason": f"round1 coverage {coverage:.3f} < threshold {rewrite_threshold}",
                }
            )
            if verbose:
                print(f"  Round2 queries={rw2.queries}  coverage={coverage_after:.3f}")
        else:
            rounds.append(
                {"round": 2, "queries": [], "error": rw2.error or "改写为空"}
            )

    final = [
        {
            "score": round(c.score, 4),
            "vector_score": c.vector_score,
            "bm25_score": c.bm25_score,
            "vector_rank": c.vector_rank,
            "bm25_rank": c.bm25_rank,
            "source": c.source,
            "chunk_index": c.chunk_index,
            "char_start": c.char_start,
            "char_end": c.char_end,
            "text": c.text,
        }
        for c in merged
    ]

    return {"rounds": rounds, "final_chunks": final, "error": ""}


# ---- CLI ------------------------------------------------------------------

def _load_outline(path: Path) -> Dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    # 兼容 backend/outline/output/*.json（meta.outline）
    if "outline" not in obj and "meta" in obj and "outline" in (obj.get("meta") or {}):
        obj = obj["meta"]
    if "outline" in obj:
        return obj["outline"]
    if "title" in obj and "chapters" in obj:
        return obj
    raise ValueError("无法识别的 outline JSON 结构（缺少 title/chapters）")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Per-page query rewrite + multi-round retrieval."
    )
    p.add_argument("--corpus", required=True)
    p.add_argument("--outline", required=True, help="大纲 JSON 文件路径")
    p.add_argument("--chapter", type=int, default=-1, help="只跑某个章节（默认全部）")
    p.add_argument("--page", type=int, default=-1, help="只跑某一页（需配合 --chapter）")
    p.add_argument("--config", default=str(BACKEND_ROOT / "config" / "models.json"))
    p.add_argument("--rewrite-provider", default="qwen", help="改写用的 LLM provider")
    p.add_argument("--embed-provider", default="qwen", help="向量检索用的 embedding provider")
    p.add_argument("--mode", default="hybrid", choices=["vector", "bm25", "hybrid"])
    p.add_argument("-k", type=int, default=6)
    p.add_argument("--recall-k", type=int, default=20)
    p.add_argument("--rrf-k", type=int, default=60)
    p.add_argument("--threshold", type=float, default=0.45,
                   help="coverage 低于该值则触发第二轮改写")
    p.add_argument("--max-rounds", type=int, default=2)
    p.add_argument("--out", default="", help="导出 JSON 路径（可选）")
    args = p.parse_args(argv)

    env_file = BACKEND_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)

    outline = _load_outline(Path(args.outline))
    chapters = outline.get("chapters") or []
    print(f"Outline: {outline.get('title')}  ({len(chapters)} chapters)")

    retriever = HybridRetriever(corpus_path(args.corpus))
    try:
        manifest = retriever.store.load_manifest()
    except FileNotFoundError as e:
        print(f"[ERR] 找不到索引: {e}")
        return 2

    embed_cfg = None
    if args.mode in ("vector", "hybrid"):
        embed_cfg = load_embed_config(
            args.config,
            provider=args.embed_provider,
            model=manifest.get("embedding_model"),
        )

    llm_client, llm_model, _defaults, _cfg = build_provider(
        args.rewrite_provider, config_path=args.config
    )

    results: List[Dict[str, Any]] = []
    for c_idx, chapter in enumerate(chapters):
        if args.chapter >= 0 and c_idx != args.chapter:
            continue
        pages = chapter.get("pages") or []
        for p_idx, _page in enumerate(pages):
            if args.page >= 0 and p_idx != args.page:
                continue
            ctx = page_context_from_outline(outline, c_idx, p_idx)
            print(f"\n=== Ch{c_idx}.P{p_idx}  {ctx.chapter_title} / {ctx.page_title}")
            print(f"    bullets={ctx.bullets}")
            r = research_page(
                ctx,
                retriever=retriever,
                embed_cfg=embed_cfg,
                llm_client=llm_client,
                llm_model=llm_model,
                mode=args.mode,
                k=args.k,
                recall_k=args.recall_k,
                rrf_k=args.rrf_k,
                rewrite_threshold=args.threshold,
                max_rounds=args.max_rounds,
                verbose=True,
            )
            if r.get("error"):
                print(f"    ERROR: {r['error']}")
            else:
                print(f"    final {len(r['final_chunks'])} chunks (top score={r['final_chunks'][0]['score'] if r['final_chunks'] else 'n/a'})")
                for i, fc in enumerate(r["final_chunks"][:3], 1):
                    snip = fc["text"].replace("\n", " ")[:120]
                    print(f"      [{i}] {snip}...")
            results.append(
                {
                    "chapter_idx": c_idx,
                    "page_idx": p_idx,
                    "chapter_title": ctx.chapter_title,
                    "page_title": ctx.page_title,
                    **r,
                }
            )

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(
                {
                    "outline_title": outline.get("title"),
                    "corpus": args.corpus,
                    "mode": args.mode,
                    "embedding_model": manifest.get("embedding_model"),
                    "rewrite_provider": args.rewrite_provider,
                    "rewrite_model": llm_model,
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\n已导出: {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
