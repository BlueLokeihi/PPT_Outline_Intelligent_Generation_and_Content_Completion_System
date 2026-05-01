"""Embedding 调用封装：复用 LlmClient (liter-llm 1.2.0) 调通义 text-embedding-v3。

- 批量发送（默认 16/批），错误自动减半重试
- 磁盘缓存（文本 SHA1 → 向量），重建索引不重复花钱
- 同步 wrap async 调用，方便 CLI 直接用
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from liter_llm import LlmClient

from llm.client import load_models_config


DEFAULT_EMBEDDING = {
    "provider": "qwen",
    "model": "text-embedding-v3",
    "dim": 1024,
    "batch_size": 16,
}


@dataclass
class EmbedConfig:
    api_key: str
    base_url: str
    model: str
    dim: int
    batch_size: int


def _resolve_api_key(provider_cfg: Dict[str, Any]) -> str:
    env = str(provider_cfg.get("api_key_env", "")).strip()
    if env:
        return os.getenv(env, "").strip()
    return str(provider_cfg.get("api_key", "")).strip()


def load_embed_config(
    config_path: str = "config/models.json",
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> EmbedConfig:
    cfg = load_models_config(config_path)
    providers = cfg.get("providers", {})
    p_name = (provider or DEFAULT_EMBEDDING["provider"]).strip()
    if p_name not in providers:
        raise KeyError(f"provider {p_name} 未在 {config_path} 中配置")
    p = providers[p_name]
    api_key = _resolve_api_key(p)
    if not api_key:
        raise RuntimeError(f"未找到 {p_name} 的 API key（环境变量 {p.get('api_key_env')}）")
    embed_cfg = (cfg.get("embedding") or {}).get(p_name, {})
    return EmbedConfig(
        api_key=api_key,
        base_url=str(p.get("base_url")),
        model=str(model or embed_cfg.get("model") or DEFAULT_EMBEDDING["model"]),
        dim=int(embed_cfg.get("dim") or DEFAULT_EMBEDDING["dim"]),
        batch_size=int(embed_cfg.get("batch_size") or DEFAULT_EMBEDDING["batch_size"]),
    )


# ---- 缓存 ----------------------------------------------------------------

def _cache_key(text: str, model: str) -> str:
    h = hashlib.sha1()
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update(text.encode("utf-8"))
    return h.hexdigest()


class EmbedCache:
    """单文件 JSONL 缓存：每行 {key, vec}。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._mem: Dict[str, List[float]] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    self._mem[obj["key"]] = obj["vec"]
                except Exception:
                    continue

    def get(self, key: str) -> Optional[List[float]]:
        return self._mem.get(key)

    def put_many(self, items: Sequence[tuple[str, List[float]]]) -> None:
        if not items:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            for k, v in items:
                if k in self._mem:
                    continue
                self._mem[k] = v
                f.write(json.dumps({"key": k, "vec": v}, ensure_ascii=False) + "\n")


# ---- Embedding 调用 ------------------------------------------------------

def _build_client(cfg: EmbedConfig) -> LlmClient:
    return LlmClient(
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        model_hint=cfg.model,
        timeout=120,
        max_retries=2,
    )


async def _embed_batch(client: LlmClient, model: str, batch: List[str]) -> List[List[float]]:
    """调一次 embedding。返回与 batch 同序的向量列表。"""
    resp = await client.embed(model=model, input=batch)
    # OpenAI 兼容形态：resp.data: [EmbeddingObject(embedding=..., index=...)]
    data = list(getattr(resp, "data", []) or [])
    data.sort(key=lambda x: getattr(x, "index", 0))
    return [list(getattr(d, "embedding", []) or []) for d in data]


async def _embed_with_retry(
    client: LlmClient, model: str, batch: List[str]
) -> List[List[float]]:
    """单次 batch 失败时，二分重试以避免单条超长卡死整批。"""
    try:
        return await _embed_batch(client, model, batch)
    except Exception as e:
        if len(batch) == 1:
            raise RuntimeError(f"embed 单条失败: {e}; 文本前 80 字: {batch[0][:80]}")
        mid = len(batch) // 2
        left = await _embed_with_retry(client, model, batch[:mid])
        right = await _embed_with_retry(client, model, batch[mid:])
        return left + right


def embed_texts(
    texts: List[str],
    *,
    cfg: EmbedConfig,
    cache: Optional[EmbedCache] = None,
    verbose: bool = True,
) -> np.ndarray:
    """对 texts 求向量，返回 (N, dim) 的 float32 矩阵。"""
    if not texts:
        return np.zeros((0, cfg.dim), dtype=np.float32)

    keys = [_cache_key(t, cfg.model) for t in texts]
    vectors: List[Optional[List[float]]] = [None] * len(texts)
    miss_idx: List[int] = []

    if cache is not None:
        for i, k in enumerate(keys):
            v = cache.get(k)
            if v is not None:
                vectors[i] = v
            else:
                miss_idx.append(i)
    else:
        miss_idx = list(range(len(texts)))

    if miss_idx:
        client = _build_client(cfg)
        new_pairs: List[tuple[str, List[float]]] = []

        async def _run() -> None:
            for start in range(0, len(miss_idx), cfg.batch_size):
                slice_idx = miss_idx[start : start + cfg.batch_size]
                batch = [texts[i] for i in slice_idx]
                if verbose:
                    print(
                        f"  embedding batch {start // cfg.batch_size + 1}/"
                        f"{(len(miss_idx) + cfg.batch_size - 1) // cfg.batch_size} "
                        f"(size={len(batch)})"
                    )
                vecs = await _embed_with_retry(client, cfg.model, batch)
                for i, v in zip(slice_idx, vecs):
                    vectors[i] = v
                    new_pairs.append((keys[i], v))

        asyncio.run(_run())

        if cache is not None and new_pairs:
            cache.put_many(new_pairs)

    arr = np.array(vectors, dtype=np.float32)
    if arr.shape[1] != cfg.dim:
        # 模型返回维度与配置不一致时，更新配置而非报错（首次运行常见）
        cfg.dim = arr.shape[1]
    return arr


def normalize_rows(mat: np.ndarray) -> np.ndarray:
    """L2 归一化。空向量留 0。"""
    if mat.size == 0:
        return mat
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return (mat / norms).astype(np.float32)
