from __future__ import annotations

from typing import Any, Dict, Tuple

from jsonschema import Draft202012Validator


def get_outline_schema() -> Dict[str, Any]:
    # 结构为：章节 — 页 — 要点 — 备注
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["title", "chapters"],
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string", "minLength": 1, "maxLength": 200},
            "assumptions": {
                "type": "array",
                "items": {"type": "string", "minLength": 1, "maxLength": 200},
                "minItems": 0,
                "maxItems": 20,
            },
            "chapters": {
                "type": "array",
                "minItems": 1,
                "maxItems": 30,
                "items": {
                    "type": "object",
                    "required": ["title", "pages"],
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string", "minLength": 1, "maxLength": 200},
                        "pages": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 60,
                            "items": {
                                "type": "object",
                                "required": ["title", "bullets", "notes"],
                                "additionalProperties": False,
                                "properties": {
                                    "title": {"type": "string", "minLength": 1, "maxLength": 200},
                                    "bullets": {
                                        "type": "array",
                                        "minItems": 1,
                                        "maxItems": 10,
                                        "items": {"type": "string", "minLength": 1, "maxLength": 200},
                                    },
                                    "notes": {"type": "string", "maxLength": 1200},
                                },
                            },
                        },
                    },
                },
            },
        },
    }


def validate_outline(data: Dict[str, Any]) -> Tuple[bool, str]:
    validator = Draft202012Validator(get_outline_schema())
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    if not errors:
        return True, ""

    err = errors[0]
    path = ".".join([str(p) for p in err.path])
    return False, f"{path}: {err.message}" if path else err.message
