"""enricher CLI：把 Step 3 research 导出的 JSON 与原 outline 合并，跑逐页浓缩。

用法（在 backend/ 下运行）：
    python -m rag.enrich \\
        --research rag/test_outlines/demo_aligned_research.json \\
        --outline  rag/test_outlines/demo_aligned.json \\
        --out      rag/test_outlines/demo_aligned_enriched.json

输出：
    enriched outline JSON：与原 outline 同结构，但每页 bullets/notes 已被浓缩，
    并附 evidences 数组。原 outline 中未在 research 里出现的页保持不变（会带个
    enrichment.skipped=true 标记，方便后续排查）。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from llm.client import build_provider
from outline.schema import validate_outline

from .enricher import (
    EnrichResult,
    confidence_from_coverage,
    enrich_page,
    snippets_from_research_chunks,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]


# ---- 大纲读取 -------------------------------------------------------------

def _load_outline(path: Path) -> Dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if "outline" not in obj and "meta" in obj and "outline" in (obj.get("meta") or {}):
        obj = obj["meta"]
    if "outline" in obj:
        return obj["outline"]
    if "title" in obj and "chapters" in obj:
        return obj
    raise ValueError("无法识别的 outline JSON 结构（缺少 title/chapters）")


def _load_research(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_research_index(
    research: Dict[str, Any],
) -> Dict[tuple, Dict[str, Any]]:
    """以 (chapter_idx, page_idx) 为 key 建索引。"""
    out: Dict[tuple, Dict[str, Any]] = {}
    for r in (research.get("results") or []):
        key = (int(r.get("chapter_idx", -1)), int(r.get("page_idx", -1)))
        out[key] = r
    return out


def _coverage_for_page(research_entry: Dict[str, Any]) -> float:
    """取 research 里最后一轮的 coverage（最宽松；多轮改写后能拿到的最好情况）。"""
    rounds = research_entry.get("rounds") or []
    if not rounds:
        return 0.0
    return float(rounds[-1].get("coverage") or 0.0)


# ---- 主流程 ---------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Enrich an outline by condensing retrieved chunks into bullets/notes."
    )
    p.add_argument("--research", required=True, help="Step 3 research 导出的 JSON")
    p.add_argument("--outline", required=True, help="原 outline JSON")
    p.add_argument("--out", required=True, help="输出 enriched outline JSON 路径")
    p.add_argument("--config", default=str(BACKEND_ROOT / "config" / "models.json"))
    p.add_argument("--provider", default="qwen", help="enrichment 用的 LLM provider")
    p.add_argument("--max-snippets", type=int, default=8, help="每页喂给 LLM 的最大片段数")
    p.add_argument("--snippet-chars", type=int, default=320, help="单片段截断字符数")
    p.add_argument("--temperature", type=float, default=0.3)
    p.add_argument(
        "--skip-low-confidence",
        action="store_true",
        help="检索 coverage 偏低的页跳过 LLM 调用，保留原 bullets",
    )
    p.add_argument("--low-threshold", type=float, default=0.4,
                   help="低于此 coverage 视为 low confidence")
    args = p.parse_args(argv)

    env_file = BACKEND_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)

    outline = _load_outline(Path(args.outline))
    research = _load_research(Path(args.research))
    research_idx = _build_research_index(research)

    llm_client, llm_model, _defaults, _cfg = build_provider(
        args.provider, config_path=args.config
    )

    overall_topic = str(outline.get("title", ""))
    chapters = outline.get("chapters") or []
    print(f"Outline: {overall_topic}  ({len(chapters)} chapters)")
    print(f"Research entries: {len(research_idx)}")
    print(f"Provider: {args.provider}  model: {llm_model}")
    print("-" * 72)

    enriched_chapters: List[Dict[str, Any]] = []
    page_meta: List[Dict[str, Any]] = []

    t_start = time.time()
    for c_idx, chapter in enumerate(chapters):
        new_pages: List[Dict[str, Any]] = []
        for p_idx, page in enumerate(chapter.get("pages") or []):
            entry = research_idx.get((c_idx, p_idx))
            page_title = str(page.get("title", ""))
            original_bullets = [str(b) for b in (page.get("bullets") or [])]
            original_notes = str(page.get("notes", ""))

            if entry is None:
                new_pages.append({
                    "title": page_title,
                    "bullets": original_bullets or ["(原页面无 bullets)"],
                    "notes": original_notes,
                })
                page_meta.append({
                    "chapter_idx": c_idx, "page_idx": p_idx,
                    "page_title": page_title,
                    "enrichment": "skipped_no_research",
                })
                print(f"[Ch{c_idx}.P{p_idx}] {page_title}  (skip: research 中无此页)")
                continue

            coverage = _coverage_for_page(entry)
            confidence = confidence_from_coverage(coverage)

            if args.skip_low_confidence and coverage < args.low_threshold:
                new_pages.append({
                    "title": page_title,
                    "bullets": original_bullets or ["(原页面无 bullets)"],
                    "notes": original_notes,
                })
                page_meta.append({
                    "chapter_idx": c_idx, "page_idx": p_idx,
                    "page_title": page_title,
                    "enrichment": "skipped_low_confidence",
                    "coverage": round(coverage, 4),
                    "confidence": confidence,
                })
                print(f"[Ch{c_idx}.P{p_idx}] {page_title}  "
                      f"(skip: coverage {coverage:.3f} < {args.low_threshold})")
                continue

            snippets = snippets_from_research_chunks(entry.get("final_chunks") or [])
            print(
                f"[Ch{c_idx}.P{p_idx}] {page_title}  "
                f"coverage={coverage:.3f} ({confidence})  snippets={len(snippets)}"
            )

            r: EnrichResult = enrich_page(
                overall_topic=overall_topic,
                chapter_title=str(chapter.get("title", "")),
                page_title=page_title,
                original_bullets=original_bullets,
                original_notes=original_notes,
                snippets=snippets,
                coverage=coverage,
                client=llm_client,
                model=llm_model,
                temperature=args.temperature,
                snippet_max_chars=args.snippet_chars,
                max_snippets=args.max_snippets,
            )

            if r.error or not r.bullets:
                # 失败：保留原 bullets，记录错误
                new_pages.append({
                    "title": page_title,
                    "bullets": original_bullets or ["(原页面无 bullets)"],
                    "notes": original_notes,
                })
                page_meta.append({
                    "chapter_idx": c_idx, "page_idx": p_idx,
                    "page_title": page_title,
                    "enrichment": "failed",
                    "coverage": round(coverage, 4),
                    "confidence": confidence,
                    "error": r.error,
                })
                print(f"    ERROR: {r.error}")
                continue

            page_dict: Dict[str, Any] = {
                "title": page_title,
                "bullets": r.bullets,
                "notes": r.notes,
            }
            if r.evidences:
                page_dict["evidences"] = r.evidences
            new_pages.append(page_dict)
            page_meta.append({
                "chapter_idx": c_idx, "page_idx": p_idx,
                "page_title": page_title,
                "enrichment": "ok",
                "coverage": round(coverage, 4),
                "confidence": confidence,
                "used_source_ids": r.used_source_ids,
                "n_evidences": len(r.evidences),
            })
            print(f"    bullets={len(r.bullets)}  evidences={len(r.evidences)}  "
                  f"used_sources={r.used_source_ids}")

        enriched_chapters.append({
            "title": str(chapter.get("title", "")),
            "pages": new_pages,
        })

    enriched_outline: Dict[str, Any] = {
        "title": overall_topic,
        "chapters": enriched_chapters,
    }
    if outline.get("assumptions"):
        enriched_outline["assumptions"] = outline["assumptions"]

    schema_ok, schema_err = validate_outline(enriched_outline)
    elapsed = time.time() - t_start

    out_payload = {
        "meta": {
            "source_outline": str(args.outline),
            "source_research": str(args.research),
            "corpus": research.get("corpus"),
            "embedding_model": research.get("embedding_model"),
            "rewrite_provider": research.get("rewrite_provider"),
            "rewrite_model": research.get("rewrite_model"),
            "enrich_provider": args.provider,
            "enrich_model": llm_model,
            "elapsed_s": round(elapsed, 2),
            "schema_ok": schema_ok,
            "schema_error": schema_err,
            "page_meta": page_meta,
        },
        "outline": enriched_outline,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(out_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("-" * 72)
    print(f"Schema valid: {schema_ok}" + (f"  ({schema_err})" if not schema_ok else ""))
    print(f"Elapsed: {elapsed:.2f}s")
    print(f"Saved: {out_path}")
    return 0 if schema_ok else 4


if __name__ == "__main__":
    sys.exit(main())
