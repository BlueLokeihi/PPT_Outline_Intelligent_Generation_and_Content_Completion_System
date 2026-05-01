"""命令行查询 CLI。

用法（在 backend/ 下运行）：
    # 默认 hybrid（vector + BM25 + RRF 融合）
    python -m rag.search --corpus demo --query "schema 校验失败" -k 5
    # 仅向量
    python -m rag.search --corpus demo --query "..." --mode vector
    # 仅 BM25
    python -m rag.search --corpus demo --query "..." --mode bm25
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

from .embedder import load_embed_config
from .retriever import HybridRetriever
from .store import corpus_path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Search a corpus index.")
    p.add_argument("--corpus", required=True)
    p.add_argument("--query", required=True)
    p.add_argument("-k", type=int, default=5)
    p.add_argument(
        "--mode",
        default="hybrid",
        choices=["vector", "bm25", "hybrid"],
        help="检索模式（默认 hybrid）",
    )
    p.add_argument("--recall-k", type=int, default=20, help="hybrid 模式下每路召回数")
    p.add_argument("--rrf-k", type=int, default=60, help="RRF 融合常数")
    p.add_argument("--config", default=str(BACKEND_ROOT / "config" / "models.json"))
    p.add_argument("--provider", default="qwen")
    p.add_argument("--model", default="")
    p.add_argument("--snippet", type=int, default=160, help="展示片段最大字符数")
    args = p.parse_args(argv)

    env_file = BACKEND_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)

    out_dir = corpus_path(args.corpus)
    retriever = HybridRetriever(out_dir)

    # 校验索引存在 + 模型一致性
    try:
        manifest = retriever.store.load_manifest()
    except FileNotFoundError as e:
        print(f"[ERR] 找不到索引: {e}\n      请先运行: python -m rag.index --corpus {args.corpus}")
        return 2

    embed_cfg = None
    if args.mode in ("vector", "hybrid"):
        embed_cfg = load_embed_config(
            args.config,
            provider=args.provider,
            model=(args.model or manifest.get("embedding_model")),
        )
        if embed_cfg.model != manifest.get("embedding_model"):
            print(
                f"[WARN] 当前 embedding 模型 ({embed_cfg.model}) 与索引构建时 "
                f"({manifest.get('embedding_model')}) 不一致，结果可能不可用"
            )

    if args.mode in ("bm25", "hybrid"):
        if not retriever.bm25.tokens_path.exists():
            print(
                f"[ERR] 缺少 BM25 索引: {retriever.bm25.tokens_path}\n"
                f"      请重新运行 index（不要加 --no-bm25）"
            )
            return 2

    hits = retriever.search(
        args.query,
        mode=args.mode,  # type: ignore[arg-type]
        k=args.k,
        recall_k=args.recall_k,
        rrf_k=args.rrf_k,
        embed_cfg=embed_cfg,
    )

    print(f"\nQuery: {args.query}")
    print(f"Mode: {args.mode}  k={args.k}"
          + (f"  recall_k={args.recall_k} rrf_k={args.rrf_k}" if args.mode == "hybrid" else ""))
    print(f"Index: {out_dir}  size={manifest.get('size')}  dim={manifest.get('dim')}")
    print("-" * 72)
    for i, h in enumerate(hits, 1):
        snippet = h.text.replace("\n", " ")
        if len(snippet) > args.snippet:
            snippet = snippet[: args.snippet] + "..."
        # 命中 badges
        badges = []
        if h.vector_rank is not None:
            badges.append(f"V#{h.vector_rank}({h.vector_score:.3f})")
        if h.bm25_rank is not None:
            badges.append(f"B#{h.bm25_rank}({h.bm25_score:.3f})")
        badge_str = "  " + " ".join(badges) if badges else ""
        print(f"[{i}] score={h.score:.4f}{badge_str}  source={h.source}  chunk={h.chunk_index}")
        print(f"    {snippet}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
