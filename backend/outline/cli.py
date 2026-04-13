from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from llm.client import build_provider

from .evaluation import compute_quality
from .generator import generate_once
from .io_utils import maybe_truncate, read_topic_text
from .prompt_strategies import PromptOptions, build_messages


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Generate structured PPT outline (compare or single).")
    p.add_argument("--mode", default="compare", choices=["compare", "single"], help="运行模式：compare 或 single")
    p.add_argument("--input", required=True, help="输入主题文本文件路径")
    p.add_argument("--config", default="config/models.json", help="模型配置文件（默认 config/models.json）")
    # compare 相关参数（多 provider × 多 strategy）
    p.add_argument("--providers", default="qwen,glm,deepseek", help="(compare) provider列表，用逗号分隔")
    p.add_argument("--strategies", default="baseline,few_shot,cot_silent", help="(compare) 策略列表，用逗号分隔")
    p.add_argument("--runs", type=int, default=3, help="(compare) 每个组合运行次数（稳定性评估）")
    # single 相关参数（单 provider × 单 strategy）
    p.add_argument("--provider", default="", help="(single) provider名称，如 qwen/glm/deepseek")
    p.add_argument(
        "--strategy",
        default="baseline",
        choices=["baseline", "few_shot", "cot_silent"],
        help="(single) Prompt策略",
    )

    # schema：compare 支持 both；single 仅支持 on/off（若传 both 会报错）
    p.add_argument("--schema", default="both", choices=["on", "off", "both"], help="Schema约束：on/off/both")

    p.add_argument("--outdir", default="outline/output", help="输出目录（默认 outline/output）")
    p.add_argument("--max-chars", type=int, default=24000, help="输入文本最大字符数，超出将截断")
    p.add_argument("--min-slides", type=int, default=10)
    p.add_argument("--max-slides", type=int, default=18)

    args = p.parse_args(argv)

    if args.mode == "single":
        return _run_single(args)
    return _run_compare(args)


def _run_compare(args: argparse.Namespace) -> int:
    providers = [x.strip() for x in str(args.providers).split(",") if x.strip()]
    strategies = [x.strip() for x in str(args.strategies).split(",") if x.strip()]

    enforce_modes: List[bool]
    if args.schema == "both":
        enforce_modes = [False, True]
    elif args.schema == "on":
        enforce_modes = [True]
    else:
        enforce_modes = [False]

    # 通过 llm/client.py 统一构建 LLM client（大模型调用集中在一个文件中）
    clients: Dict[str, Any] = {}
    selected_cfg: Dict[str, Any] = {}
    provider_models: Dict[str, str] = {}
    defaults: Any = None
    for provider_name in providers:
        client, model, defaults_i, provider_cfg = build_provider(provider_name, config_path=args.config)
        clients[provider_name] = client
        provider_models[provider_name] = model
        selected_cfg[provider_name] = provider_cfg
        defaults = defaults or defaults_i

    topic_text = read_topic_text(args.input)
    topic_text = maybe_truncate(topic_text, max_chars=args.max_chars)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    summary: Dict[str, Any] = {
        "timestamp": timestamp,
        "mode": "compare",
        "input": args.input,
        "providers": providers,
        "strategies": strategies,
        "schema_modes": ["on" if x else "off" for x in enforce_modes],
        "runs_per_combo": args.runs,
        "models": {k: {"base_url": v.get("base_url"), "model": v.get("model")} for k, v in selected_cfg.items()},
        "defaults": asdict(defaults) if defaults is not None else {},
        "results": [],
    }

    from .evaluation import compute_stability

    for provider_name, client in clients.items():
        model = provider_models[provider_name]
        for strategy in strategies:
            for enforce_schema in enforce_modes:
                run_entries: List[Dict[str, Any]] = []

                for i in range(int(args.runs)):
                    opts = PromptOptions(
                        strategy=strategy,  # type: ignore[arg-type]
                        enforce_schema=enforce_schema,
                        min_slides=args.min_slides,
                        max_slides=args.max_slides,
                    )
                    messages = build_messages(topic_text, opts)

                    r = generate_once(
                        client,
                        provider=provider_name,
                        strategy=strategy,
                        enforce_schema=enforce_schema,
                        messages=messages,
                        model=model,
                        temperature=float(getattr(defaults, "temperature", 0.4)),
                        top_p=float(getattr(defaults, "top_p", 0.9)),
                        max_tokens=int(getattr(defaults, "max_tokens", 4096)),
                    )

                    entry: Dict[str, Any] = {
                        "provider": provider_name,
                        "strategy": strategy,
                        "schema": "on" if enforce_schema else "off",
                        "run": i + 1,
                        "ok": r.ok,
                        "error": r.error,
                        "elapsed_s": round(r.elapsed_s, 3),
                    }

                    if r.outline is not None:
                        entry["outline"] = r.outline
                        entry["quality"] = asdict(compute_quality(r.outline, min_slides=args.min_slides, max_slides=args.max_slides))
                    if r.schema_ok is not None:
                        entry["schema_ok"] = r.schema_ok
                        entry["schema_error"] = r.schema_error

                    fname = f"{timestamp}_{provider_name}_{strategy}_{'schemaOn' if enforce_schema else 'schemaOff'}_run{i+1}.json"
                    (outdir / fname).write_text(json.dumps({"meta": entry, "raw_text": r.raw_text}, ensure_ascii=False, indent=2), encoding="utf-8")
                    run_entries.append(entry)

                combo = {
                    "provider": provider_name,
                    "strategy": strategy,
                    "schema": "on" if enforce_schema else "off",
                    "runs": run_entries,
                }

                total_runs = len(run_entries)
                ok_runs = sum(1 for e in run_entries if e.get("ok"))
                ok_outlines = [e["outline"] for e in run_entries if e.get("ok") and e.get("outline") is not None]
                schema_ok_flags_all = [e.get("schema_ok") for e in run_entries]

                combo["stability"] = asdict(
                    compute_stability(
                        ok_outlines,
                        total_runs=total_runs,
                        ok_runs=ok_runs,
                        schema_ok_flags_all=schema_ok_flags_all,
                    )
                )

                if ok_outlines:
                    qualities = [e.get("quality", {}) for e in run_entries if e.get("quality")]
                    if qualities:
                        combo["avg_quality_overall_0_100"] = round(
                            sum(q.get("overall_score_0_100", 0.0) for q in qualities) / len(qualities),
                            2,
                        )

                summary["results"].append(combo)

    summary_path = outdir / f"{timestamp}_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Done. Summary saved to: {summary_path}")
    return 0


def _run_single(args: argparse.Namespace) -> int:
    provider = str(args.provider).strip()
    strategy = str(args.strategy).strip()
    if not provider:
        raise SystemExit("single 模式需要 --provider")
    if not strategy:
        raise SystemExit("single 模式需要 --strategy")
    if args.schema == "both":
        raise SystemExit("single 模式下 --schema 仅支持 on/off")

    client, model, defaults, provider_cfg = build_provider(provider, config_path=args.config)
    topic_text = read_topic_text(args.input)
    topic_text = maybe_truncate(topic_text, max_chars=args.max_chars)

    enforce_schema = args.schema == "on"
    opts = PromptOptions(
        strategy=strategy,  # type: ignore[arg-type]
        enforce_schema=enforce_schema,
        min_slides=args.min_slides,
        max_slides=args.max_slides,
    )
    messages = build_messages(topic_text, opts)

    r = generate_once(
        client,
        provider=provider,
        strategy=strategy,
        enforce_schema=enforce_schema,
        messages=messages,
        model=model,
        temperature=defaults.temperature,
        top_p=defaults.top_p,
        max_tokens=defaults.max_tokens,
    )

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    entry: Dict[str, Any] = {
        "timestamp": timestamp,
        "mode": "single",
        "input": args.input,
        "provider": provider,
        "strategy": strategy,
        "schema": "on" if enforce_schema else "off",
        "model": {"base_url": provider_cfg.get("base_url"), "model": provider_cfg.get("model")},
        "defaults": asdict(defaults),
        "ok": r.ok,
        "error": r.error,
        "elapsed_s": round(r.elapsed_s, 3),
    }

    if r.outline is not None:
        entry["outline"] = r.outline
        entry["quality"] = asdict(compute_quality(r.outline, min_slides=args.min_slides, max_slides=args.max_slides))
        if r.schema_ok is not None:
            entry["schema_ok"] = r.schema_ok
            entry["schema_error"] = r.schema_error

    fname = f"{timestamp}_{provider}_{strategy}_{'schemaOn' if enforce_schema else 'schemaOff'}.json"
    out_path = outdir / fname
    out_path.write_text(json.dumps({"meta": entry, "raw_text": r.raw_text}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Done. Saved to: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
