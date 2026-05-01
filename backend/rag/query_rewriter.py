"""基于大纲节点的查询改写。

输入：一页 PPT 的上下文（章节标题 + 页标题 + 草稿要点 + 整体主题）
输出：2-3 条用于检索外部资料的短 query，覆盖不同角度（定义 / 事实/数据 / 案例）。

支持两种调用：
- rewrite_queries：首轮，仅看上下文
- rewrite_with_feedback：当首轮检索召回质量低时，把"已用 query + 召回片段"反馈给 LLM 再写一轮
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from liter_llm import LlmClient

from llm.client import chat_text_sync
from outline.json_extract import extract_first_json_object


# ---- 数据结构 -------------------------------------------------------------

@dataclass
class PageContext:
    overall_topic: str        # outline.title
    chapter_title: str
    page_title: str
    bullets: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class RewriteResult:
    queries: List[str]
    intent_tags: List[str]    # 与 queries 一一对应：定义/事实/案例/数据/对比/历史 等
    raw_text: str             # LLM 原始输出（debug 用）
    error: str = ""


# ---- Prompt 构造 ----------------------------------------------------------

_SYSTEM = (
    "你是一个面向 PPT 内容补全的检索查询改写助手。"
    "你会收到一页 PPT 的上下文，需要为它生成用于本地知识库检索的短查询。"
    "只输出严格 JSON，不要 Markdown 代码块、不要解释文字。"
)


def _format_page(ctx: PageContext) -> str:
    bullets = "\n".join(f"  - {b}" for b in ctx.bullets) if ctx.bullets else "  (尚无)"
    return (
        f"整体主题: {ctx.overall_topic}\n"
        f"所在章节: {ctx.chapter_title}\n"
        f"本页标题: {ctx.page_title}\n"
        f"要点草稿:\n{bullets}\n"
        f"演讲备注: {ctx.notes or '(无)'}"
    )


def _build_first_round_prompt(ctx: PageContext, *, max_queries: int) -> List[Dict[str, str]]:
    user = (
        "请基于下面这页 PPT 的上下文，生成 2-"
        f"{max_queries} 条用于检索外部资料的短查询。\n"
        "硬性要求：\n"
        "- 每条查询 ≤ 20 字（中文）或 ≤ 8 个英文词，避免冗长\n"
        "- 多条查询应覆盖不同角度，从以下挑选不重复的标签：\n"
        "  定义 / 事实 / 数据 / 案例 / 对比 / 历史 / 影响 / 方法\n"
        "- 与本页主题相关，但不要照抄页标题\n"
        "- 与整体主题保持一致，不要漂移到无关领域\n\n"
        '严格 JSON 格式：{"queries":["q1","q2",...], "intent_tags":["定义","事实",...]}\n'
        "queries 与 intent_tags 长度相同且一一对应。\n\n"
        "页面上下文：\n"
        f"{_format_page(ctx)}"
    )
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]


def _build_feedback_prompt(
    ctx: PageContext,
    prev_queries: List[str],
    prev_top_snippets: List[str],
    *,
    max_queries: int,
) -> List[Dict[str, str]]:
    snippets_block = (
        "\n".join(f"  [{i+1}] {s}" for i, s in enumerate(prev_top_snippets))
        if prev_top_snippets
        else "  (无召回)"
    )
    user = (
        "之前的检索 query 召回质量不佳，请重写更有针对性的新一轮 query。\n\n"
        f"上一轮使用的 query：{prev_queries}\n"
        "上一轮 top 片段（可能与本页主题无关或太宽泛）：\n"
        f"{snippets_block}\n\n"
        "改写要求：\n"
        "- 避开上一轮 query 已用的措辞\n"
        "- 更聚焦本页要点中的关键词、数字、专有名词\n"
        "- 尝试加入领域同义词（如 transformer→注意力机制）\n"
        f"- 同样输出 2-{max_queries} 条，每条 ≤ 20 字（中文）或 ≤ 8 个英文词\n\n"
        '严格 JSON 格式：{"queries":["q1","q2",...], "intent_tags":["..."]}\n\n'
        "页面上下文：\n"
        f"{_format_page(ctx)}"
    )
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]


# ---- 解析 -----------------------------------------------------------------

def _parse(raw: str, *, max_queries: int) -> RewriteResult:
    obj, err = extract_first_json_object(raw)
    if obj is None:
        return RewriteResult(queries=[], intent_tags=[], raw_text=raw, error=err or "解析失败")

    queries_raw = obj.get("queries", []) or []
    tags_raw = obj.get("intent_tags", []) or []
    if not isinstance(queries_raw, list):
        return RewriteResult(queries=[], intent_tags=[], raw_text=raw, error="queries 不是数组")

    queries: List[str] = []
    seen: set[str] = set()
    for q in queries_raw:
        s = str(q).strip()
        if not s:
            continue
        # 去重 + 截断（兜底，防止 LLM 不守规矩）
        if s in seen:
            continue
        seen.add(s)
        queries.append(s[:60])
        if len(queries) >= max_queries:
            break

    tags: List[str] = []
    for t in tags_raw:
        tags.append(str(t).strip()[:20])
    # 长度对齐
    if len(tags) < len(queries):
        tags.extend([""] * (len(queries) - len(tags)))
    elif len(tags) > len(queries):
        tags = tags[: len(queries)]

    if not queries:
        return RewriteResult(queries=[], intent_tags=[], raw_text=raw, error="queries 为空")
    return RewriteResult(queries=queries, intent_tags=tags, raw_text=raw)


# ---- 公共入口 -------------------------------------------------------------

def rewrite_queries(
    ctx: PageContext,
    *,
    client: LlmClient,
    model: str,
    temperature: float = 0.3,
    top_p: float = 0.9,
    max_tokens: int = 512,
    max_queries: int = 3,
) -> RewriteResult:
    messages = _build_first_round_prompt(ctx, max_queries=max_queries)
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
        return RewriteResult(queries=[], intent_tags=[], raw_text="", error=str(e))
    return _parse(raw, max_queries=max_queries)


def rewrite_with_feedback(
    ctx: PageContext,
    prev_queries: List[str],
    prev_top_snippets: List[str],
    *,
    client: LlmClient,
    model: str,
    temperature: float = 0.5,    # 反馈轮稍高一点，鼓励发散
    top_p: float = 0.9,
    max_tokens: int = 512,
    max_queries: int = 3,
) -> RewriteResult:
    # 截短反馈片段，避免上下文炸裂
    snippets = [s[:200] for s in prev_top_snippets[:5]]
    messages = _build_feedback_prompt(
        ctx, prev_queries, snippets, max_queries=max_queries
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
        return RewriteResult(queries=[], intent_tags=[], raw_text="", error=str(e))
    return _parse(raw, max_queries=max_queries)


# ---- 工具：从 outline JSON 取页面上下文 -----------------------------------

def page_context_from_outline(
    outline: Dict[str, Any], chapter_idx: int, page_idx: int
) -> PageContext:
    chapters = outline.get("chapters") or []
    if not (0 <= chapter_idx < len(chapters)):
        raise IndexError(f"chapter_idx 越界: {chapter_idx}")
    chapter = chapters[chapter_idx]
    pages = chapter.get("pages") or []
    if not (0 <= page_idx < len(pages)):
        raise IndexError(f"page_idx 越界: {page_idx}")
    page = pages[page_idx]
    return PageContext(
        overall_topic=str(outline.get("title", "")),
        chapter_title=str(chapter.get("title", "")),
        page_title=str(page.get("title", "")),
        bullets=[str(b) for b in (page.get("bullets") or [])],
        notes=str(page.get("notes", "")),
    )
