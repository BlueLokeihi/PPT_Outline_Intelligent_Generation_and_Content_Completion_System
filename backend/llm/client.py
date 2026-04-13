from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from liter_llm import LlmClient


@dataclass(frozen=True)
class GenerationDefaults:
    temperature: float
    top_p: float
    max_tokens: int


def load_models_config(config_path: str = "config/models.json") -> Dict[str, Any]:
    return json.loads(Path(config_path).read_text(encoding="utf-8"))


def build_provider(
    provider_name: str,
    *,
    config_path: str = "config/models.json",
) -> Tuple[LlmClient, str, GenerationDefaults, Dict[str, Any]]:
    """构建单个 provider 的 LlmClient，并返回 (client, model, defaults, provider_cfg)。

    provider 配置格式见 backend/config/models.json。
    """
    cfg = load_models_config(config_path)
    providers: Mapping[str, Mapping[str, Any]] = cfg.get("providers", {})
    if provider_name not in providers:
        raise KeyError(f"配置中不存在provider: {provider_name}")

    p = dict(providers[provider_name])

    api_key_env = str(p.get("api_key_env", "")).strip()
    api_key = os.getenv(api_key_env, "").strip() if api_key_env else str(p.get("api_key", "")).strip()

    client = LlmClient(
        api_key=api_key,
        base_url=str(p.get("base_url")) if p.get("base_url") else None,
        model_hint=str(p.get("model")) if p.get("model") else None,
        timeout=int(p.get("timeout_s", 120)),
        max_retries=int(p.get("max_retries", 2)),
        extra_headers=p.get("extra_headers"),
    )

    model = str(p.get("model", "")).strip()
    if not model:
        raise ValueError(f"provider {provider_name} 未配置 model")

    defaults_raw: Mapping[str, Any] = cfg.get("defaults", {})
    defaults = GenerationDefaults(
        temperature=float(defaults_raw.get("temperature", 0.4)),
        top_p=float(defaults_raw.get("top_p", 0.9)),
        max_tokens=int(defaults_raw.get("max_tokens", 4096)),
    )

    return client, model, defaults, p


def chat_text_sync(
    client: LlmClient,
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    top_p: float,
    max_tokens: int,
) -> str:
    """同步方式调用 liter-llm 的 chat（内部 asyncio.run）。"""

    async def _run() -> str:
        resp = await client.chat(
            model=model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
        )
        return str(resp.choices[0].message.content or "")

    return asyncio.run(_run())
