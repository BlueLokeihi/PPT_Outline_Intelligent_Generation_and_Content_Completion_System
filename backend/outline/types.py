from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


JSONDict = Dict[str, Any]


@dataclass(frozen=True)
class OutlinePage:
    title: str
    bullets: List[str]
    notes: str = ""


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
                        {"title": page.title, "bullets": list(page.bullets), "notes": page.notes}
                        for page in chapter.pages
                    ],
                }
                for chapter in self.chapters
            ],
            **({"assumptions": list(self.assumptions)} if self.assumptions else {}),
        }
