from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from llm.client import build_provider, load_models_config
from outline.evaluation import compute_quality
from outline.generator import generate_once
from outline.io_utils import maybe_truncate
from outline.prompt_strategies import PromptOptions, build_messages
from rag.embedder import load_embed_config
from rag.enricher import (
    confidence_from_coverage,
    enrich_page,
    snippets_from_research_chunks,
)
from rag.query_rewriter import page_context_from_outline
from rag.research import research_page
from rag.retriever import HybridRetriever
from rag.store import corpus_path

# 加载 .env 文件中的环境变量
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
MODELS_CONFIG = BACKEND_ROOT / "config" / "models.json"
ENV_FILE = BACKEND_ROOT / ".env"

# 自动加载 .env 文件
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
    print(f"✓ 已加载环境变量配置: {ENV_FILE}")
else:
    print(f"⚠ 未找到 .env 文件: {ENV_FILE}")


class MessageItem(BaseModel):
    role: Literal["system", "user", "assistant"]
    text: str = ""


class OutlineRequest(BaseModel):
    conversationId: str | None = None
    messages: List[MessageItem] = Field(default_factory=list)
    pdfText: str = ""
    provider: str = "qwen"
    strategy: Literal["baseline", "few_shot", "cot_silent"] = "baseline"
    schema: Literal["on", "off"] = "on"
    minSlides: int = Field(default=10, ge=1, le=100)
    maxSlides: int = Field(default=18, ge=1, le=100)
    # —— RAG 相关（默认关闭，旧客户端无影响） ——
    useRag: bool = False
    corpusId: str = ""
    ragMode: Literal["vector", "bm25", "hybrid"] = "hybrid"
    ragRewriteThreshold: float = Field(default=0.45, ge=0.0, le=1.0)
    ragMaxRounds: int = Field(default=2, ge=1, le=3)
    ragMaxSnippets: int = Field(default=8, ge=1, le=20)
    ragSkipLowConfidence: bool = False
    ragLowThreshold: float = Field(default=0.4, ge=0.0, le=1.0)


app = FastAPI(title="PPT Outline Local API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def compose_topic_text(messages: List[MessageItem], pdf_text: str) -> str:
    lines: List[str] = ["你将基于以下对话与资料生成 PPT 大纲。"]

    if pdf_text.strip():
        lines.append("\n[PDF资料摘录]\n")
        lines.append(pdf_text.strip())

    lines.append("\n[多轮对话]\n")
    for item in messages:
        text = item.text.strip()
        if not text:
            continue
        lines.append(f"{item.role}: {text}")

    return "\n".join(lines).strip()


def run_outline(request: OutlineRequest) -> Dict[str, Any]:
    provider = request.provider.strip() or "qwen"
    strategy = request.strategy
    schema = request.schema
    min_slides = request.minSlides
    max_slides = request.maxSlides

    if min_slides > max_slides:
        min_slides, max_slides = max_slides, min_slides

    topic_text = compose_topic_text(messages=request.messages, pdf_text=request.pdfText)
    topic_text = maybe_truncate(topic_text, max_chars=24000)

    client, model, defaults, _provider_cfg = build_provider(provider, config_path=str(MODELS_CONFIG))

    opts = PromptOptions(
        strategy=strategy,
        enforce_schema=(schema == "on"),
        min_slides=min_slides,
        max_slides=max_slides,
    )
    messages = build_messages(topic_text, opts)

    result = generate_once(
        client,
        provider=provider,
        strategy=strategy,
        enforce_schema=(schema == "on"),
        messages=messages,
        model=model,
        temperature=defaults.temperature,
        top_p=defaults.top_p,
        max_tokens=defaults.max_tokens,
    )

    response: Dict[str, Any] = {
        "ok": bool(result.ok),
        "provider": provider,
        "strategy": strategy,
        "schema": schema,
        "elapsedS": round(float(result.elapsed_s), 3),
    }

    if result.ok and result.outline is not None:
        response["outline"] = result.outline
        response["quality"] = asdict(
            compute_quality(result.outline, min_slides=min_slides, max_slides=max_slides)
        )

        if request.useRag and request.corpusId.strip():
            try:
                rag_meta = _run_rag_pipeline(request, response["outline"])
                response["rag"] = rag_meta
                response["elapsedS"] = round(
                    response["elapsedS"] + float(rag_meta.get("elapsed_s") or 0.0), 3
                )
            except Exception as exc:  # noqa: BLE001
                response["rag"] = {"used": False, "error": str(exc)}
        return response

    response["error"] = result.error or "生成失败"
    return response


# ---- RAG 管道（research + enrich，全在内存中流转） ------------------------

def _run_rag_pipeline(
    request: OutlineRequest, outline: Dict[str, Any]
) -> Dict[str, Any]:
    """跑 research + enrich，原地修改 outline（写回 evidences/bullets/notes）。

    返回 rag meta：corpus、模型信息、各页 coverage/confidence/used_sources。
    """
    t_start = time.time()
    corpus_id = request.corpusId.strip()
    out_dir = corpus_path(corpus_id)

    retriever = HybridRetriever(out_dir)
    manifest = retriever.store.load_manifest()    # 不存在则抛 FileNotFoundError

    embed_cfg = None
    if request.ragMode in ("vector", "hybrid"):
        embed_cfg = load_embed_config(
            str(MODELS_CONFIG),
            provider=request.provider,
            model=manifest.get("embedding_model"),
        )

    llm_client, llm_model, _defaults, _cfg = build_provider(
        request.provider, config_path=str(MODELS_CONFIG)
    )

    overall_topic = str(outline.get("title", ""))
    chapters = outline.get("chapters") or []
    page_meta: List[Dict[str, Any]] = []

    for c_idx, chapter in enumerate(chapters):
        for p_idx, page in enumerate(chapter.get("pages") or []):
            page_title = str(page.get("title", ""))
            ctx = page_context_from_outline(outline, c_idx, p_idx)

            # ---- research：query 改写 + 多轮检索 ----
            r = research_page(
                ctx,
                retriever=retriever,
                embed_cfg=embed_cfg,
                llm_client=llm_client,
                llm_model=llm_model,
                mode=request.ragMode,
                k=6,
                recall_k=20,
                rrf_k=60,
                rewrite_threshold=request.ragRewriteThreshold,
                max_rounds=request.ragMaxRounds,
                verbose=False,
            )
            if r.get("error"):
                page_meta.append({
                    "chapter_idx": c_idx, "page_idx": p_idx,
                    "page_title": page_title,
                    "enrichment": "research_failed",
                    "error": r["error"],
                })
                continue

            rounds = r.get("rounds") or []
            coverage = float(rounds[-1].get("coverage") or 0.0) if rounds else 0.0
            confidence = confidence_from_coverage(coverage)

            # ---- 低置信度 skip 选项 ----
            if request.ragSkipLowConfidence and coverage < request.ragLowThreshold:
                page_meta.append({
                    "chapter_idx": c_idx, "page_idx": p_idx,
                    "page_title": page_title,
                    "enrichment": "skipped_low_confidence",
                    "coverage": round(coverage, 4),
                    "confidence": confidence,
                })
                continue

            # ---- enrich：浓缩为 bullets+notes+evidences ----
            snippets = snippets_from_research_chunks(r.get("final_chunks") or [])
            er = enrich_page(
                overall_topic=overall_topic,
                chapter_title=str(chapter.get("title", "")),
                page_title=page_title,
                original_bullets=ctx.bullets,
                original_notes=ctx.notes,
                snippets=snippets,
                coverage=coverage,
                client=llm_client,
                model=llm_model,
                temperature=0.3,
                max_snippets=request.ragMaxSnippets,
            )
            if er.error or not er.bullets:
                page_meta.append({
                    "chapter_idx": c_idx, "page_idx": p_idx,
                    "page_title": page_title,
                    "enrichment": "failed",
                    "coverage": round(coverage, 4),
                    "confidence": confidence,
                    "error": er.error,
                })
                continue

            # 写回 outline（原地修改）
            page["bullets"] = er.bullets
            page["notes"] = er.notes
            if er.evidences:
                page["evidences"] = er.evidences
            elif "evidences" in page:
                del page["evidences"]

            page_meta.append({
                "chapter_idx": c_idx, "page_idx": p_idx,
                "page_title": page_title,
                "enrichment": "ok",
                "coverage": round(coverage, 4),
                "confidence": confidence,
                "used_source_ids": er.used_source_ids,
                "n_evidences": len(er.evidences),
            })

    return {
        "used": True,
        "corpus": corpus_id,
        "mode": request.ragMode,
        "embedding_model": manifest.get("embedding_model"),
        "index_size": manifest.get("size"),
        "rewrite_threshold": request.ragRewriteThreshold,
        "max_rounds": request.ragMaxRounds,
        "page_meta": page_meta,
        "elapsed_s": round(time.time() - t_start, 3),
    }


@app.post("/api/ping")
def api_ping() -> Dict[str, Any]:
    return {"ok": True, "message": "http api is ready"}


@app.get("/api/runtime-info")
def api_runtime_info() -> Dict[str, Any]:
    try:
        cfg = load_models_config(str(MODELS_CONFIG))
        providers = list((cfg.get("providers") or {}).keys())
        return {
            "ok": True,
            "providers": providers,
            "strategies": ["baseline", "few_shot", "cot_silent"],
        }
    except Exception:
        return {
            "ok": False,
            "providers": ["qwen", "glm", "deepseek"],
            "strategies": ["baseline", "few_shot", "cot_silent"],
        }


@app.get("/api/rag/corpora")
def api_rag_corpora() -> Dict[str, Any]:
    """列出已建好的索引（backend/rag/indexes/<id>/）。"""
    base = BACKEND_ROOT / "rag" / "indexes"
    if not base.exists():
        return {"ok": True, "corpora": []}
    items: List[Dict[str, Any]] = []
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        manifest_path = d / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            import json as _json
            manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
            items.append({
                "id": d.name,
                "size": manifest.get("size"),
                "dim": manifest.get("dim"),
                "embedding_model": manifest.get("embedding_model"),
                "built_at": manifest.get("built_at"),
                "has_bm25": (d / "tokens.jsonl").exists(),
            })
        except Exception:
            continue
    return {"ok": True, "corpora": items}


@app.post("/api/outline")
def api_outline(request: OutlineRequest) -> Dict[str, Any]:
    try:
        return run_outline(request)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("http_server:app", host="127.0.0.1", port=8000, reload=False)
