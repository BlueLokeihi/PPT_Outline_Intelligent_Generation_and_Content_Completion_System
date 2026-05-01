from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


JSONDict = Dict[str, Any]


@dataclass(frozen=True)
class Evidence:
    text: str          # 摘录原文（已截断到展示长度）
    source: str        # 文件名或 URL
    score: float       # 检索得分（hybrid RRF / vector 余弦 / BM25 原始分）
    chunk_index: int = -1


@dataclass(frozen=True)
class OutlinePage:
    title: str
    bullets: List[str]
    notes: str = ""
    evidences: Optional[List[Evidence]] = None


@dataclass(frozen=True)
class OutlineChapter:
    title: str
    pages: List[OutlinePage]


@dataclass(frozen=True)
class Outline:
    title: str
    chapters: List[OutlineChapter]
    assumptions: Optional[List[str]] = None

    def to_dict(self) -> JSONDict:
        return {
            "title": self.title,
            "chapters": [
                {
                    "title": chapter.title,
                    "pages": [
                        _page_to_dict(page) for page in chapter.pages
                    ],
                }
                for chapter in self.chapters
            ],
            **({"assumptions": list(self.assumptions)} if self.assumptions else {}),
        }


def _page_to_dict(page: OutlinePage) -> JSONDict:
    out: JSONDict = {
        "title": page.title,
        "bullets": list(page.bullets),
        "notes": page.notes,
    }
    if page.evidences:
        out["evidences"] = [
            {
                "text": e.text,
                "source": e.source,
                "score": e.score,
                "chunk_index": e.chunk_index,
            }
            for e in page.evidences
        ]
    return out
