from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List


class BackendBridge:
    def __init__(self) -> None:
        self.project_root = Path(__file__).resolve().parents[2]
        self.backend_root = self.project_root / "backend"
        if str(self.backend_root) not in sys.path:
            sys.path.insert(0, str(self.backend_root))

    def ping(self) -> Dict[str, Any]:
        return {"ok": True, "message": "pywebview bridge is ready"}

    def get_runtime_info(self) -> Dict[str, Any]:
        try:
            from llm.client import load_models_config  # pylint: disable=import-outside-toplevel

            config_path = self.backend_root / "config" / "models.json"
            cfg = load_models_config(str(config_path))
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

    def run_outline(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._run_outline_impl(payload)
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": str(exc),
            }

    def _run_outline_impl(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from llm.client import build_provider  # pylint: disable=import-outside-toplevel
        from outline.evaluation import compute_quality  # pylint: disable=import-outside-toplevel
        from outline.generator import generate_once  # pylint: disable=import-outside-toplevel
        from outline.io_utils import maybe_truncate  # pylint: disable=import-outside-toplevel
        from outline.prompt_strategies import PromptOptions, build_messages  # pylint: disable=import-outside-toplevel

        provider = str(payload.get("provider", "qwen")).strip() or "qwen"
        strategy = str(payload.get("strategy", "baseline")).strip() or "baseline"
        schema = str(payload.get("schema", "on")).strip() or "on"
        min_slides = int(payload.get("minSlides", 10))
        max_slides = int(payload.get("maxSlides", 18))

        if min_slides > max_slides:
            min_slides, max_slides = max_slides, min_slides

        topic_text = self._compose_topic_text(
            messages=payload.get("messages") or [],
            pdf_text=str(payload.get("pdfText", "")),
        )
        topic_text = maybe_truncate(topic_text, max_chars=24000)

        config_path = self.backend_root / "config" / "models.json"
        client, model, defaults, _provider_cfg = build_provider(provider, config_path=str(config_path))

        opts = PromptOptions(
            strategy=strategy,  # type: ignore[arg-type]
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
            return response

        response["error"] = result.error or "生成失败"
        return response

    @staticmethod
    def _compose_topic_text(messages: List[Dict[str, Any]], pdf_text: str) -> str:
        lines: List[str] = ["你将基于以下对话与资料生成 PPT 大纲。"]

        if pdf_text.strip():
            lines.append("\n[PDF资料摘录]\n")
            lines.append(pdf_text.strip())

        lines.append("\n[多轮对话]\n")
        for item in messages:
            role = str(item.get("role", "user"))
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            lines.append(f"{role}: {text}")

        return "\n".join(lines).strip()


def dump_runtime_info() -> str:
    bridge = BackendBridge()
    return json.dumps(bridge.get_runtime_info(), ensure_ascii=False)
