from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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
    print(f"[OK] Loaded env: {ENV_FILE}")
else:
    print(f"[WARN] .env not found: {ENV_FILE}")


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


class OutlineSavePage(BaseModel):
    title: str = ""
    bullets: List[str] = Field(default_factory=list)
    notes: str = ""
    evidences: Optional[List[Dict[str, Any]]] = None
    conflicts: Optional[List[Dict[str, Any]]] = None


class OutlineSaveChapter(BaseModel):
    title: str = ""
    pages: List[OutlineSavePage] = Field(default_factory=list)


class OutlineSaveBody(BaseModel):
    title: str = ""
    assumptions: Optional[List[str]] = None
    chapters: List[OutlineSaveChapter] = Field(default_factory=list)


class OutlineSaveRequest(BaseModel):
    conversationId: Optional[str] = None
    outline: OutlineSaveBody


class OutlineVersionRequest(BaseModel):
    conversationId: Optional[str] = None
    outline: OutlineSaveBody
    sourceType: Literal["generated", "edited", "rag", "restored"] = "edited"
    provider: Optional[str] = None
    strategy: Optional[str] = None
    schemaMode: Optional[Literal["on", "off"]] = None
    useRag: bool = False
    summary: str = ""


class OutlineExportRequest(BaseModel):
    conversationId: Optional[str] = None
    outline: OutlineSaveBody
    format: Literal["markdown", "html", "pptx", "json"] = "markdown"
    report: Optional[Dict[str, Any]] = None


class CorpusBuildRequest(BaseModel):
    corpusId: str
    provider: str = "qwen"
    model: str = ""
    chunkSize: int = Field(default=500, ge=100, le=2000)
    overlap: int = Field(default=80, ge=0, le=500)


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
        try:
            version = _write_outline_version(
                conversation_id=request.conversationId,
                outline=response["outline"],
                source_type="rag" if response.get("rag", {}).get("used") else "generated",
                provider=provider,
                strategy=strategy,
                schema_mode=schema,
                use_rag=bool(response.get("rag", {}).get("used")),
            )
            response["version"] = {
                "versionId": version["versionId"],
                "createdAt": version["createdAt"],
                "sourceType": version["sourceType"],
                "summary": version["summary"],
            }
        except Exception:
            pass
        return response

    response["error"] = result.error or "生成失败"
    return response


def _clean_text(value: str, fallback: str) -> str:
    text = (value or "").strip()
    return text if text else fallback


def _clean_list(items: Optional[List[str]]) -> List[str]:
    if not items:
        return []
    return [item.strip() for item in items if item and item.strip()]


def _normalize_outline(outline: OutlineSaveBody) -> Dict[str, Any]:
    chapters: List[Dict[str, Any]] = []
    for chapter in outline.chapters:
        pages: List[Dict[str, Any]] = []
        for page in chapter.pages:
            page_payload: Dict[str, Any] = {
                "title": _clean_text(page.title, "未命名页面"),
                "bullets": _clean_list(page.bullets),
                "notes": page.notes or "",
            }
            if page.evidences:
                page_payload["evidences"] = page.evidences
            if page.conflicts:
                page_payload["conflicts"] = page.conflicts
            pages.append(page_payload)
        chapters.append({
            "title": _clean_text(chapter.title, "未命名章节"),
            "pages": pages,
        })

    payload: Dict[str, Any] = {
        "title": _clean_text(outline.title, "未命名大纲"),
        "chapters": chapters,
    }

    if outline.assumptions:
        payload["assumptions"] = _clean_list(outline.assumptions)

    return payload


def _safe_token(value: Optional[str]) -> str:
    if not value:
        return "session"
    token = re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_")
    return token[:48] or "session"


def _versions_root(conversation_id: Optional[str]) -> Path:
    return BACKEND_ROOT / "outline" / "versions" / _safe_token(conversation_id)


def _outline_summary(outline: Dict[str, Any]) -> str:
    chapters = outline.get("chapters") or []
    page_count = sum(len(ch.get("pages") or []) for ch in chapters)
    return f"{len(chapters)} chapters, {page_count} pages"


def _write_outline_version(
    *,
    conversation_id: Optional[str],
    outline: Dict[str, Any],
    source_type: str,
    provider: Optional[str] = None,
    strategy: Optional[str] = None,
    schema_mode: Optional[str] = None,
    use_rag: bool = False,
    summary: str = "",
) -> Dict[str, Any]:
    version_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    created_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    payload = {
        "versionId": version_id,
        "conversationId": conversation_id or "",
        "createdAt": created_at,
        "sourceType": source_type,
        "provider": provider,
        "strategy": strategy,
        "schema": schema_mode,
        "useRag": use_rag,
        "summary": summary or _outline_summary(outline),
        "outline": outline,
    }
    out_dir = _versions_root(conversation_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{version_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def _read_version_file(version_id: str) -> Dict[str, Any]:
    base = BACKEND_ROOT / "outline" / "versions"
    for path in base.glob(f"*/{version_id}.json"):
        return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"version not found: {version_id}")


def _build_markdown(outline: Dict[str, Any], report: Optional[Dict[str, Any]] = None) -> str:
    lines = [f"# {outline.get('title') or 'PPT Outline'}"]
    assumptions = outline.get("assumptions") or []
    if assumptions:
        lines.extend(["", "## 假设前提"])
        lines.extend([f"- {item}" for item in assumptions])
    for c_idx, chapter in enumerate(outline.get("chapters") or [], 1):
        lines.extend(["", f"## {c_idx}. {chapter.get('title') or '未命名章节'}"])
        for p_idx, page in enumerate(chapter.get("pages") or [], 1):
            lines.extend(["", f"### {c_idx}.{p_idx} {page.get('title') or '未命名页面'}"])
            for bullet in page.get("bullets") or []:
                lines.append(f"- {bullet}")
            if page.get("notes"):
                lines.extend(["", f"> {page['notes']}"])
            evidences = page.get("evidences") or []
            if evidences:
                lines.append("")
                lines.append("来源：")
                for ev in evidences:
                    source = ev.get("source") or "unknown"
                    chunk = ev.get("chunk_index")
                    suffix = f" #chunk{chunk}" if isinstance(chunk, int) else ""
                    lines.append(f"- {source}{suffix}: {ev.get('text', '')[:160]}")
            conflicts = page.get("conflicts") or []
            if conflicts:
                lines.append("")
                lines.append("冲突提示：")
                for item in conflicts:
                    lines.append(f"- {item.get('message') or item}")
    if report:
        lines.extend(["", "## 验收报告", "```json", json.dumps(report, ensure_ascii=False, indent=2), "```"])
    return "\n".join(lines) + "\n"


def _build_html(outline: Dict[str, Any], report: Optional[Dict[str, Any]] = None) -> str:
    def esc(value: Any) -> str:
        return (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    body = [f"<h1>{esc(outline.get('title') or 'PPT Outline')}</h1>"]
    for c_idx, chapter in enumerate(outline.get("chapters") or [], 1):
        body.append(f"<section><h2>{c_idx}. {esc(chapter.get('title') or '未命名章节')}</h2>")
        for p_idx, page in enumerate(chapter.get("pages") or [], 1):
            body.append(f"<article><h3>{c_idx}.{p_idx} {esc(page.get('title') or '未命名页面')}</h3><ul>")
            for bullet in page.get("bullets") or []:
                body.append(f"<li>{esc(bullet)}</li>")
            body.append("</ul>")
            if page.get("notes"):
                body.append(f"<p class='notes'>{esc(page['notes'])}</p>")
            evidences = page.get("evidences") or []
            if evidences:
                body.append("<details><summary>Sources</summary><ol>")
                for ev in evidences:
                    body.append(f"<li><strong>{esc(ev.get('source', 'unknown'))}</strong>: {esc(ev.get('text', ''))}</li>")
                body.append("</ol></details>")
            conflicts = page.get("conflicts") or []
            if conflicts:
                body.append("<div class='conflict'><strong>Conflict notes</strong><ul>")
                for item in conflicts:
                    body.append(f"<li>{esc(item.get('message') if isinstance(item, dict) else item)}</li>")
                body.append("</ul></div>")
            body.append("</article>")
        body.append("</section>")
    if report:
        body.append(f"<section><h2>Acceptance Report</h2><pre>{esc(json.dumps(report, ensure_ascii=False, indent=2))}</pre></section>")

    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>PPT Outline Export</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 40px; color: #172033; line-height: 1.55; }
    article { border-top: 1px solid #dbeafe; padding: 14px 0; }
    h1 { color: #1d4ed8; }
    h2 { color: #0f766e; }
    .notes { background: #f8fafc; border-left: 4px solid #60a5fa; padding: 10px 12px; }
    .conflict { background: #fff7ed; border: 1px solid #fdba74; border-radius: 8px; padding: 10px 12px; }
    pre { background: #0f172a; color: #e2e8f0; padding: 16px; border-radius: 8px; overflow: auto; }
  </style>
</head>
<body>
""" + "\n".join(body) + "\n</body>\n</html>\n"


def _build_pptx(outline: Dict[str, Any], out_path: Path) -> None:
    try:
        from pptx import Presentation
        from pptx.util import Pt
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("PPTX export requires python-pptx. Please install backend requirements.") from exc

    prs = Presentation()
    title_slide = prs.slides.add_slide(prs.slide_layouts[0])
    title_slide.shapes.title.text = outline.get("title") or "PPT Outline"
    title_slide.placeholders[1].text = "Generated by PPT Outline System"

    for c_idx, chapter in enumerate(outline.get("chapters") or [], 1):
        section = prs.slides.add_slide(prs.slide_layouts[1])
        section.shapes.title.text = f"{c_idx}. {chapter.get('title') or '未命名章节'}"
        section.placeholders[1].text = f"{len(chapter.get('pages') or [])} pages"
        for p_idx, page in enumerate(chapter.get("pages") or [], 1):
            slide = prs.slides.add_slide(prs.slide_layouts[1])
            slide.shapes.title.text = f"{c_idx}.{p_idx} {page.get('title') or '未命名页面'}"
            frame = slide.placeholders[1].text_frame
            frame.clear()
            for b_idx, bullet in enumerate(page.get("bullets") or ["（暂无要点）"]):
                para = frame.paragraphs[0] if b_idx == 0 else frame.add_paragraph()
                para.text = str(bullet)
                para.level = 0
                para.font.size = Pt(18)
            notes = page.get("notes") or ""
            if notes:
                slide.notes_slide.notes_text_frame.text = notes
    prs.save(out_path)


def _detect_conflicts(evidences: List[Dict[str, Any]], confidence: str) -> List[Dict[str, Any]]:
    """Lightweight, explainable conflict flagging for reviewer-facing RAG output.

    This is intentionally conservative: it marks "possible conflicts" when retrieved
    evidence comes from multiple sources and contains different numeric claims.
    """
    if len(evidences) < 2:
        return []
    numbers_by_source: Dict[str, set[str]] = {}
    for ev in evidences:
        source = str(ev.get("source") or "unknown")
        text = str(ev.get("text") or "")
        nums = set(re.findall(r"\d+(?:\.\d+)?%?|\d{4}", text))
        if nums:
            numbers_by_source.setdefault(source, set()).update(nums)
    if len(numbers_by_source) < 2:
        return []
    all_sets = list(numbers_by_source.values())
    shared = set.intersection(*all_sets) if all_sets else set()
    union = set.union(*all_sets) if all_sets else set()
    if len(union - shared) < 2 and confidence != "low":
        return []
    return [{
        "type": "possible_numeric_conflict",
        "severity": "medium" if confidence != "low" else "high",
        "message": "Multiple sources contain different numeric claims; please confirm before presenting.",
        "sources": sorted(numbers_by_source.keys()),
        "signals": sorted(union - shared)[:12],
    }]


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
                conflicts = _detect_conflicts(er.evidences, confidence)
                if conflicts:
                    page["conflicts"] = conflicts
                elif "conflicts" in page:
                    del page["conflicts"]
            elif "evidences" in page:
                del page["evidences"]
                if "conflicts" in page:
                    del page["conflicts"]

            page_meta.append({
                "chapter_idx": c_idx, "page_idx": p_idx,
                "page_title": page_title,
                "enrichment": "ok",
                "coverage": round(coverage, 4),
                "confidence": confidence,
                "used_source_ids": er.used_source_ids,
                "n_evidences": len(er.evidences),
                "conflicts": page.get("conflicts", []),
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


@app.post("/api/rag/corpora/build")
def api_rag_corpus_build(request: CorpusBuildRequest) -> Dict[str, Any]:
    try:
        corpus_id = _safe_token(request.corpusId)
        src_dir = BACKEND_ROOT / "rag" / "corpus" / corpus_id
        if not src_dir.exists():
            return {"ok": False, "error": f"corpus directory not found: {src_dir}"}
        from rag.index import main as build_index
        args = [
            "--corpus", corpus_id,
            "--provider", request.provider,
            "--chunk-size", str(request.chunkSize),
            "--overlap", str(request.overlap),
        ]
        if request.model.strip():
            args.extend(["--model", request.model.strip()])
        code = build_index(args)
        return {"ok": code == 0, "corpusId": corpus_id, "exitCode": code}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.post("/api/outline")
def api_outline(request: OutlineRequest) -> Dict[str, Any]:
    try:
        return run_outline(request)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.post("/api/outline/save")
def api_outline_save(request: OutlineSaveRequest) -> Dict[str, Any]:
    try:
        outline_payload = _normalize_outline(request.outline)
        out_dir = BACKEND_ROOT / "outline" / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        token = _safe_token(request.conversationId)
        filename = f"{timestamp}_edited_{token}.json"
        out_path = out_dir / filename
        out_path.write_text(
            json.dumps(outline_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "ok": True,
            "file": filename,
            "relativePath": f"outline/output/{filename}",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.post("/api/outline/versions")
def api_outline_version_create(request: OutlineVersionRequest) -> Dict[str, Any]:
    try:
        outline_payload = _normalize_outline(request.outline)
        version = _write_outline_version(
            conversation_id=request.conversationId,
            outline=outline_payload,
            source_type=request.sourceType,
            provider=request.provider,
            strategy=request.strategy,
            schema_mode=request.schemaMode,
            use_rag=request.useRag,
            summary=request.summary,
        )
        return {"ok": True, "version": {k: version.get(k) for k in (
            "versionId", "conversationId", "createdAt", "sourceType",
            "provider", "strategy", "schema", "useRag", "summary",
        )}}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.get("/api/outline/versions")
def api_outline_versions(conversationId: Optional[str] = None) -> Dict[str, Any]:
    try:
        out_dir = _versions_root(conversationId)
        versions: List[Dict[str, Any]] = []
        if out_dir.exists():
            for path in sorted(out_dir.glob("*.json"), reverse=True):
                data = json.loads(path.read_text(encoding="utf-8"))
                versions.append({k: data.get(k) for k in (
                    "versionId", "conversationId", "createdAt", "sourceType",
                    "provider", "strategy", "schema", "useRag", "summary",
                )})
        return {"ok": True, "versions": versions}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "versions": []}


@app.get("/api/outline/versions/{version_id}")
def api_outline_version_get(version_id: str) -> Dict[str, Any]:
    try:
        return {"ok": True, "version": _read_version_file(version_id)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.post("/api/outline/versions/{version_id}/restore")
def api_outline_version_restore(version_id: str) -> Dict[str, Any]:
    try:
        version = _read_version_file(version_id)
        restored = _write_outline_version(
            conversation_id=version.get("conversationId"),
            outline=version["outline"],
            source_type="restored",
            provider=version.get("provider"),
            strategy=version.get("strategy"),
            schema_mode=version.get("schema"),
            use_rag=bool(version.get("useRag")),
            summary=f"Restored from {version_id}",
        )
        return {
            "ok": True,
            "outline": version["outline"],
            "version": {k: restored.get(k) for k in (
                "versionId", "conversationId", "createdAt", "sourceType",
                "provider", "strategy", "schema", "useRag", "summary",
            )},
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.post("/api/outline/export")
def api_outline_export(request: OutlineExportRequest):
    try:
        outline_payload = _normalize_outline(request.outline)
        out_dir = BACKEND_ROOT / "outline" / "exports"
        out_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        token = _safe_token(request.conversationId)
        base = f"{timestamp}_{token}"

        if request.format == "json":
            path = out_dir / f"{base}.json"
            path.write_text(
                json.dumps({"outline": outline_payload, "report": request.report}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return FileResponse(path, media_type="application/json", filename=path.name)

        if request.format == "html":
            path = out_dir / f"{base}.html"
            path.write_text(_build_html(outline_payload, request.report), encoding="utf-8")
            return FileResponse(path, media_type="text/html; charset=utf-8", filename=path.name)

        if request.format == "pptx":
            path = out_dir / f"{base}.pptx"
            _build_pptx(outline_payload, path)
            return FileResponse(
                path,
                media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                filename=path.name,
            )

        path = out_dir / f"{base}.md"
        path.write_text(_build_markdown(outline_payload, request.report), encoding="utf-8")
        return FileResponse(path, media_type="text/markdown; charset=utf-8", filename=path.name)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("http_server:app", host="127.0.0.1", port=8000, reload=False)
