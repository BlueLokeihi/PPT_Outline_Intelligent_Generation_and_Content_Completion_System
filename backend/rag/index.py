"""建索引 CLI。

用法（在 backend/ 下运行）：
    python -m rag.index --corpus demo
    python -m rag.index --corpus demo --chunk-size 600 --overlap 80

读取 backend/rag/corpus/<corpus>/ 下的 .txt/.md/.pdf，
切块 → 求向量 → 写入 backend/rag/indexes/<corpus>/。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

from .bm25 import Bm25Index
from .chunker import Chunk, chunk_corpus
from .embedder import EmbedCache, embed_texts, load_embed_config, normalize_rows
from .store import VectorStore, corpus_path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = Path(__file__).resolve().parent
CORPUS_BASE = RAG_ROOT / "corpus"
CACHE_DIR = RAG_ROOT / "cache"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Build FAISS index for a corpus.")
    p.add_argument("--corpus", required=True, help="corpus id（对应 backend/rag/corpus/<id>/）")
    p.add_argument("--config", default=str(BACKEND_ROOT / "config" / "models.json"))
    p.add_argument("--provider", default="qwen", help="使用哪个 provider 的 embedding（默认 qwen）")
    p.add_argument("--model", default="", help="embedding 模型名（默认 text-embedding-v3）")
    p.add_argument("--chunk-size", type=int, default=500)
    p.add_argument("--overlap", type=int, default=80)
    p.add_argument("--no-cache", action="store_true", help="禁用 embedding 磁盘缓存")
    p.add_argument("--no-bm25", action="store_true", help="跳过 BM25 索引构建（仅向量）")
    args = p.parse_args(argv)

    env_file = BACKEND_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)

    src_dir = CORPUS_BASE / args.corpus
    if not src_dir.exists():
        print(f"[ERR] 语料目录不存在: {src_dir}")
        print(f"      请先创建并放入 .txt/.md/.pdf 文档")
        return 2

    total_steps = 4 if args.no_bm25 else 5
    print(f"[1/{total_steps}] 扫描并切块: {src_dir}")
    chunks: List[Chunk] = chunk_corpus(
        src_dir, chunk_size=args.chunk_size, overlap=args.overlap
    )
    if not chunks:
        print("[ERR] 没有可索引的文本片段（目录为空或全部解析失败）")
        return 3
    print(f"      共 {len(chunks)} 个 chunk（来自 "
          f"{len({c.source for c in chunks})} 个文件）")

    print(f"[2/{total_steps}] 加载 embedding 配置: provider={args.provider}")
    cfg = load_embed_config(
        args.config,
        provider=args.provider,
        model=(args.model or None),
    )
    print(f"      model={cfg.model}, dim={cfg.dim}, batch={cfg.batch_size}")

    cache = None
    if not args.no_cache:
        cache_path = CACHE_DIR / f"{args.provider}__{cfg.model}.jsonl"
        cache = EmbedCache(cache_path)
        print(f"      cache: {cache_path} (已存 {len(cache._mem)} 条)")

    print(f"[3/{total_steps}] 调用 embedding API")
    texts = [c.text for c in chunks]
    vectors = embed_texts(texts, cfg=cfg, cache=cache, verbose=True)
    vectors = normalize_rows(vectors)
    print(f"      得到 {vectors.shape[0]} × {vectors.shape[1]} 向量")

    print(f"[4/{total_steps}] 写入 FAISS 索引")
    out_dir = corpus_path(args.corpus)
    store = VectorStore(out_dir)
    metas = [c.to_dict() for c in chunks]
    store.build(vectors=vectors, metas=metas, embedding_model=cfg.model)
    print(f"      已写入: {out_dir}")

    if not args.no_bm25:
        print(f"[5/{total_steps}] 构建 BM25 索引（jieba 分词）")
        bm25 = Bm25Index(out_dir)
        bm25.build([c.text for c in chunks])
        print(f"      已写入: {bm25.tokens_path}")

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
