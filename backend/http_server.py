from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Literal

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from llm.client import build_provider, load_models_config
from outline.evaluation import compute_quality
from outline.generator import generate_once
from outline.io_utils import maybe_truncate
from outline.prompt_strategies import PromptOptions, build_messages

# 加载 .env 文件中的环境变量
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
MODELS_CONFIG = BACKEND_ROOT / "config" / "models.json"
ENV_FILE = BACKEND_ROOT / ".env"

# 自动加载 .env 文件
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
    print(f"✓ 已加载环境变量配置: {ENV_FILE}")
else:
    print(f"⚠ 未找到 .env 文件: {ENV_FILE}")


class MessageItem(BaseModel):
    role: Literal["system", "user", "assistant"]
    text: str = ""


class OutlineRequest(BaseModel):
    conversationId: str | None = None
    messages: List[MessageItem] = Field(default_factory=list)
    pdfText: str = ""
    provider: str = "qwen"
    strategy: Literal["baseline", "few_shot", "cot_silent"] = "baseline"
    schema: Literal["on", "off"] = "on"
    minSlides: int = Field(default=10, ge=1, le=100)
    maxSlides: int = Field(default=18, ge=1, le=100)


app = FastAPI(title="PPT Outline Local API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def compose_topic_text(messages: List[MessageItem], pdf_text: str) -> str:
    lines: List[str] = ["你将基于以下对话与资料生成 PPT 大纲。"]

    if pdf_text.strip():
        lines.append("\n[PDF资料摘录]\n")
        lines.append(pdf_text.strip())

    lines.append("\n[多轮对话]\n")
    for item in messages:
        text = item.text.strip()
        if not text:
            continue
        lines.append(f"{item.role}: {text}")

    return "\n".join(lines).strip()


def run_outline(request: OutlineRequest) -> Dict[str, Any]:
    provider = request.provider.strip() or "qwen"
    strategy = request.strategy
    schema = request.schema
    min_slides = request.minSlides
    max_slides = request.maxSlides

    if min_slides > max_slides:
        min_slides, max_slides = max_slides, min_slides

    topic_text = compose_topic_text(messages=request.messages, pdf_text=request.pdfText)
    topic_text = maybe_truncate(topic_text, max_chars=24000)

    client, model, defaults, _provider_cfg = build_provider(provider, config_path=str(MODELS_CONFIG))

    opts = PromptOptions(
        strategy=strategy,
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


@app.post("/api/ping")
def api_ping() -> Dict[str, Any]:
    return {"ok": True, "message": "http api is ready"}


@app.get("/api/runtime-info")
def api_runtime_info() -> Dict[str, Any]:
    try:
        cfg = load_models_config(str(MODELS_CONFIG))
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


@app.post("/api/outline")
def api_outline(request: OutlineRequest) -> Dict[str, Any]:
    try:
        return run_outline(request)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("http_server:app", host="127.0.0.1", port=8000, reload=False)
