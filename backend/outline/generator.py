from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from liter_llm import LlmClient

from llm.client import chat_text_sync

from .json_extract import extract_first_json_object
from .schema import validate_outline


@dataclass
class GenerateResult:
    provider: str
    strategy: str
    enforce_schema: bool
    ok: bool
    error: str
    elapsed_s: float
    raw_text: str
    outline: Optional[Dict[str, Any]] = None
    schema_ok: Optional[bool] = None
    schema_error: str = ""


def generate_once(
    client: LlmClient,
    *,
    provider: str,
    strategy: str,
    enforce_schema: bool,
    messages: list[dict[str, str]],
    model: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
) -> GenerateResult:
    start = time.time()
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
        return GenerateResult(
            provider=provider,
            strategy=strategy,
            enforce_schema=enforce_schema,
            ok=False,
            error=str(e),
            elapsed_s=time.time() - start,
            raw_text="",
        )

    outline, err = extract_first_json_object(raw)
    if outline is None:
        return GenerateResult(
            provider=provider,
            strategy=strategy,
            enforce_schema=enforce_schema,
            ok=False,
            error=err,
            elapsed_s=time.time() - start,
            raw_text=raw,
        )

    schema_ok = None
    schema_error = ""
    if enforce_schema:
        schema_ok, schema_error = validate_outline(outline)
        if not schema_ok:
            return GenerateResult(
                provider=provider,
                strategy=strategy,
                enforce_schema=enforce_schema,
                ok=False,
                error=f"Schema校验失败: {schema_error}",
                elapsed_s=time.time() - start,
                raw_text=raw,
                outline=outline,
                schema_ok=schema_ok,
                schema_error=schema_error,
            )

    return GenerateResult(
        provider=provider,
        strategy=strategy,
        enforce_schema=enforce_schema,
        ok=True,
        error="",
        elapsed_s=time.time() - start,
        raw_text=raw,
        outline=outline,
        schema_ok=schema_ok,
        schema_error=schema_error,
    )
