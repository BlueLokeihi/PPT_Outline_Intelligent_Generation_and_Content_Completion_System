"""单页内容浓缩：把检索到的 chunks 压成 PPT 可用的 bullets + notes。

输入：
  - 原页面草稿（chapter title / page title / bullets / notes）
  - 多个外部知识片段（来自 Step 3 research 的 final_chunks）
  - 可选：研究阶段的 coverage 信号（用于决定 confidence 标签）

输出：EnrichResult
  - bullets：3-6 条精炼要点，每条 ≤ 30 字
  - notes：≤ 200 字的演讲提示
  - used_source_ids：LLM 自报使用的片段编号（1-based）
  - evidences：根据 used_source_ids 过滤出来的 chunks 元数据
  - confidence：high / medium / low（基于 coverage）
  - error：解析或生成失败时填写
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from liter_llm import LlmClient

from llm.client import chat_text_sync
from outline.json_extract import extract_first_json_object


# ---- 数据结构 -------------------------------------------------------------

@dataclass
class RetrievedSnippet:
    """喂给 LLM 的输入片段（来自 research final_chunks 的简化形态）。"""
    source: str
    chunk_index: int
    text: str
    score: float = 0.0
    vector_score: Optional[float] = None
    bm25_score: Optional[float] = None


@dataclass
class EnrichResult:
    bullets: List[str]
    notes: str
    used_source_ids: List[int]                  # 1-based 索引
    evidences: List[Dict[str, Any]]             # 与 used_source_ids 对齐的 chunks 元数据
    confidence: str                             # high / medium / low
    raw_text: str = ""
    error: str = ""


# ---- Prompt 构造 ----------------------------------------------------------

_SYSTEM = (
    "你是 PPT 内容补全专家。你将看到一页 PPT 的原始草稿，以及若干来自外部资料的"
    "知识片段，请把它们融合为更精炼的页面内容。"
    "只输出严格 JSON，不要 Markdown 代码块、不要解释文字。"
)


def _format_snippets(snippets: List[RetrievedSnippet], *, max_chars: int) -> str:
    lines: List[str] = []
    for i, s in enumerate(snippets, 1):
        body = s.text.strip().replace("\n", " ")
        if len(body) > max_chars:
            body = body[:max_chars] + "..."
        lines.append(f"  [{i}] (来源: {s.source} #chunk{s.chunk_index})  {body}")
    return "\n".join(lines)


def _build_prompt(
    *,
    overall_topic: str,
    chapter_title: str,
    page_title: str,
    original_bullets: List[str],
    original_notes: str,
    snippets: List[RetrievedSnippet],
    snippet_max_chars: int,
    confidence_hint: str,
) -> List[Dict[str, str]]:
    bullets_block = (
        "\n".join(f"  - {b}" for b in original_bullets) if original_bullets else "  (尚无)"
    )
    snippets_block = (
        _format_snippets(snippets, max_chars=snippet_max_chars)
        if snippets
        else "  (无外部片段)"
    )

    confidence_clause = ""
    if confidence_hint == "low":
        confidence_clause = (
            "注意：本页检索召回质量较弱，外部片段可能与主题相关性不足。"
            "若片段不足以支撑改写，请保留原 bullets 的核心，仅在确信无误时引用片段；"
            "used_sources 可以为空数组。\n"
        )

    user = (
        f"整体主题: {overall_topic}\n"
        f"所在章节: {chapter_title}\n"
        f"本页标题: {page_title}\n"
        f"原 bullets:\n{bullets_block}\n"
        f"原 notes: {original_notes or '(无)'}\n\n"
        "外部知识片段（编号 1..N，每条带来源）：\n"
        f"{snippets_block}\n\n"
        + confidence_clause +
        "改写要求：\n"
        "- 输出 3-6 条 bullets，每条 ≤ 30 字（中文），优先保留可验证的数字、专有名词、年份、来源\n"
        "- 输出 notes，≤ 200 字，给演讲者讲解参考（背景说明、过渡语、案例提示均可）\n"
        "- bullets 与 notes 的事实必须有依据（来自上面片段或与原 bullets 一致）；不要凭空编造数字\n"
        "- 用 used_sources 数组报告你引用的片段编号（1-based 整数）；未使用任何片段则给空数组 []\n\n"
        '严格 JSON 格式：{"bullets":["..."], "notes":"...", "used_sources":[1,3,...]}\n'
    )
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]


# ---- 解析与组装 -----------------------------------------------------------

def _parse(
    raw: str,
    snippets: List[RetrievedSnippet],
    *,
    confidence: str,
) -> EnrichResult:
    obj, err = extract_first_json_object(raw)
    if obj is None:
        return EnrichResult(
            bullets=[], notes="", used_source_ids=[], evidences=[],
            confidence=confidence, raw_text=raw, error=err or "解析失败"
        )

    bullets_raw = obj.get("bullets", []) or []
    notes_raw = obj.get("notes", "") or ""
    used_raw = obj.get("used_sources", []) or []

    if not isinstance(bullets_raw, list):
        return EnrichResult(
            bullets=[], notes="", used_source_ids=[], evidences=[],
            confidence=confidence, raw_text=raw, error="bullets 不是数组"
        )

    bullets: List[str] = []
    for b in bullets_raw:
        s = str(b).strip()
        if not s:
            continue
        bullets.append(s[:200])    # schema 上限 200，再硬截一次防越界
        if len(bullets) >= 10:     # schema 上限 10
            break
    if not bullets:
        return EnrichResult(
            bullets=[], notes="", used_source_ids=[], evidences=[],
            confidence=confidence, raw_text=raw, error="bullets 为空"
        )

    notes = str(notes_raw).strip()[:1200]    # schema 上限 1200

    used_ids: List[int] = []
    seen: set[int] = set()
    for x in used_raw:
        try:
            i = int(x)
        except Exception:
            continue
        if 1 <= i <= len(snippets) and i not in seen:
            seen.add(i)
            used_ids.append(i)

    evidences: List[Dict[str, Any]] = []
    for i in used_ids:
        s = snippets[i - 1]
        ev_text = s.text.strip().replace("\n", " ")
        if len(ev_text) > 400:
            ev_text = ev_text[:400] + "..."
        evidences.append(
            {
                "text": ev_text,
                "source": s.source,
                "score": float(s.score),
                "chunk_index": int(s.chunk_index),
            }
        )

    return EnrichResult(
        bullets=bullets,
        notes=notes,
        used_source_ids=used_ids,
        evidences=evidences,
        confidence=confidence,
        raw_text=raw,
    )


# ---- 公共入口 -------------------------------------------------------------

def confidence_from_coverage(coverage: float) -> str:
    """把 research 阶段的 coverage 信号映射成置信度标签。"""
    if coverage >= 0.65:
        return "high"
    if coverage >= 0.5:
        return "medium"
    return "low"


def enrich_page(
    *,
    overall_topic: str,
    chapter_title: str,
    page_title: str,
    original_bullets: List[str],
    original_notes: str,
    snippets: List[RetrievedSnippet],
    coverage: float,
    client: LlmClient,
    model: str,
    temperature: float = 0.3,
    top_p: float = 0.9,
    max_tokens: int = 1024,
    snippet_max_chars: int = 320,
    max_snippets: int = 8,
) -> EnrichResult:
    confidence = confidence_from_coverage(coverage)
    snips = snippets[:max_snippets]

    messages = _build_prompt(
        overall_topic=overall_topic,
        chapter_title=chapter_title,
        page_title=page_title,
        original_bullets=original_bullets,
        original_notes=original_notes,
        snippets=snips,
        snippet_max_chars=snippet_max_chars,
        confidence_hint=confidence,
    )
    try:
        raw = chat_text_sync(
            client,
            model=model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
        )
    except Exception as e:
        return EnrichResult(
            bullets=[], notes="", used_source_ids=[], evidences=[],
            confidence=confidence, raw_text="", error=str(e)
        )
    return _parse(raw, snips, confidence=confidence)


def snippets_from_research_chunks(chunks: List[Dict[str, Any]]) -> List[RetrievedSnippet]:
    """把 research.py 导出的 final_chunks 转成 enricher 需要的输入。"""
    out: List[RetrievedSnippet] = []
    for c in chunks:
        out.append(
            RetrievedSnippet(
                source=str(c.get("source", "")),
                chunk_index=int(c.get("chunk_index", -1)),
                text=str(c.get("text", "")),
                score=float(c.get("score") or 0.0),
                vector_score=c.get("vector_score"),
                bm25_score=c.get("bm25_score"),
            )
        )
    return out
