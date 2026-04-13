from __future__ import annotations

import itertools
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional


def flatten_slide_titles(outline: Dict[str, Any]) -> List[str]:
    titles: List[str] = []
    for chapter in outline.get("chapters", []) or []:
        for page in chapter.get("pages", []) or []:
            t = str(page.get("title", "")).strip()
            if t:
                titles.append(t)
    return titles


def flatten_bullets(outline: Dict[str, Any]) -> List[str]:
    bullets: List[str] = []
    for chapter in outline.get("chapters", []) or []:
        for page in chapter.get("pages", []) or []:
            for b in page.get("bullets", []) or []:
                s = str(b).strip()
                if s:
                    bullets.append(s)
    return bullets


@dataclass(frozen=True)
class QualityMetrics:
    slide_count: int
    chapter_count: int
    avg_bullets_per_slide: float
    unique_slide_title_ratio: float
    granularity_score_0_100: float
    hierarchy_score_0_100: float
    coherence_score_0_100: float
    overall_score_0_100: float


def compute_quality(outline: Dict[str, Any], *, min_slides: int = 10, max_slides: int = 18) -> QualityMetrics:
    chapters = outline.get("chapters", []) or []
    chapter_count = len(chapters)

    slide_titles = flatten_slide_titles(outline)
    slide_count = len(slide_titles)

    bullets: List[str] = []
    slide_bullet_counts: List[int] = []
    for chapter in chapters:
        pages = chapter.get("pages", []) or []
        for page in pages:
            bs = page.get("bullets", []) or []
            slide_bullet_counts.append(len(bs))
            bullets.extend([str(x).strip() for x in bs if str(x).strip()])

    avg_bullets = (sum(slide_bullet_counts) / len(slide_bullet_counts)) if slide_bullet_counts else 0.0
    unique_ratio = (len(set(slide_titles)) / len(slide_titles)) if slide_titles else 0.0

    granularity = _range_score(slide_count, min_slides, max_slides) * _range_score(avg_bullets, 3.0, 6.0)

    empty_chapters = sum(1 for c in chapters if not (c.get("pages") or []))
    hierarchy = _range_score(chapter_count, 3, 8) * (
        1.0 if empty_chapters == 0 else max(0.0, 1.0 - empty_chapters / max(1, chapter_count))
    )

    short_bullets = sum(1 for b in bullets if len(b) < 4)
    short_ratio = short_bullets / max(1, len(bullets))
    coherence = (0.6 * unique_ratio + 0.4 * (1.0 - short_ratio))

    granularity_100 = round(_clamp01(granularity) * 100, 2)
    hierarchy_100 = round(_clamp01(hierarchy) * 100, 2)
    coherence_100 = round(_clamp01(coherence) * 100, 2)

    overall = _clamp01(0.4 * _clamp01(granularity) + 0.35 * _clamp01(hierarchy) + 0.25 * _clamp01(coherence))
    overall_100 = round(overall * 100, 2)

    return QualityMetrics(
        slide_count=slide_count,
        chapter_count=chapter_count,
        avg_bullets_per_slide=round(avg_bullets, 2),
        unique_slide_title_ratio=round(unique_ratio, 3),
        granularity_score_0_100=granularity_100,
        hierarchy_score_0_100=hierarchy_100,
        coherence_score_0_100=coherence_100,
        overall_score_0_100=overall_100,
    )


@dataclass(frozen=True)
class StabilityMetrics:
    total_runs: int
    ok_runs: int
    ok_rate: float
    schema_ok_rate: Optional[float]
    avg_pairwise_title_similarity_0_1: Optional[float]


def compute_stability(
    ok_outlines: List[Dict[str, Any]],
    *,
    total_runs: int,
    ok_runs: int,
    schema_ok_flags_all: List[Optional[bool]] | None = None,
) -> StabilityMetrics:
    ok_rate = (ok_runs / total_runs) if total_runs else 0.0

    schema_ok_rate: Optional[float] = None
    if schema_ok_flags_all is not None:
        valid_flags = [f for f in schema_ok_flags_all if f is not None]
        if valid_flags:
            schema_ok_rate = sum(1 for f in valid_flags if f) / len(valid_flags)

    if len(ok_outlines) >= 2:
        title_strings = ["\n".join(flatten_slide_titles(o)) for o in ok_outlines]
        pairs = list(itertools.combinations(title_strings, 2))
        sims = [SequenceMatcher(a=x, b=y).ratio() for x, y in pairs]
        avg_sim = sum(sims) / len(sims) if sims else None
    else:
        avg_sim = None

    return StabilityMetrics(
        total_runs=total_runs,
        ok_runs=ok_runs,
        ok_rate=round(ok_rate, 3),
        schema_ok_rate=round(schema_ok_rate, 3) if schema_ok_rate is not None else None,
        avg_pairwise_title_similarity_0_1=round(avg_sim, 3) if avg_sim is not None else None,
    )


def _range_score(value: float, low: float, high: float) -> float:
    if low <= value <= high:
        return 1.0
    if value < low:
        return _clamp01(1.0 - (low - value) / max(1e-9, low))
    return _clamp01(1.0 - (value - high) / max(1e-9, high))


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))
