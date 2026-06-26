from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
RESULTS_DIR = PROJECT_ROOT / "test_results"


SAMPLE_TOPIC = """主题：人工智能发展简史
受众：软件工程课程师生
目标：生成 6-8 页课程汇报 PPT 大纲，突出时间线、关键技术突破和当前挑战。
要求：每页 3-5 条要点，备注中给出演讲提示。
"""


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Client:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def get(self, path: str, **kwargs: Any) -> requests.Response:
        return requests.get(f"{self.base_url}{path}", timeout=kwargs.pop("timeout", 120), **kwargs)

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        return requests.post(f"{self.base_url}{path}", timeout=kwargs.pop("timeout", 240), **kwargs)


def wait_for_server(base_url: str, timeout_s: int = 30) -> None:
    deadline = time.time() + timeout_s
    last = ""
    while time.time() < deadline:
        try:
            r = requests.post(f"{base_url}/api/ping", json={}, timeout=2)
            if r.status_code == 200:
                return
            last = f"HTTP {r.status_code}: {r.text[:120]}"
        except Exception as exc:  # noqa: BLE001
            last = repr(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server not ready: {last}")


def start_server(base_url: str) -> subprocess.Popen[str]:
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "http_server:app",
            "--host",
            "127.0.0.1",
            "--port",
            base_url.rsplit(":", 1)[-1].replace("/", ""),
        ],
        cwd=BACKEND_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        wait_for_server(base_url)
    except Exception:
        proc.terminate()
        try:
            out, _ = proc.communicate(timeout=5)
        except Exception:
            out = ""
        raise RuntimeError(f"failed to start backend:\n{out}")
    return proc


def result(test_id: str, requirement: str, name: str) -> dict[str, Any]:
    return {
        "id": test_id,
        "requirement": requirement,
        "name": name,
        "status": "NOT_RUN",
        "duration_s": None,
        "details": {},
        "error": "",
        "timestamp": now_iso(),
    }


def run_case(results: list[dict[str, Any]], test_id: str, requirement: str, name: str, fn: Callable[[], dict[str, Any]]) -> None:
    item = result(test_id, requirement, name)
    start = time.perf_counter()
    try:
        item["details"] = fn()
        item["status"] = "PASS"
    except AssertionError as exc:
        item["status"] = "FAIL"
        item["error"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        item["status"] = "ERROR"
        item["error"] = repr(exc)
    item["duration_s"] = round(time.perf_counter() - start, 3)
    item["timestamp"] = now_iso()
    results.append(item)
    print(f"[{item['status']}] {test_id} {name} ({item['duration_s']}s)")
    if item["error"]:
        print(f"    {item['error']}")


def parse_json_response(resp: requests.Response) -> dict[str, Any]:
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:500]}"
    data = resp.json()
    assert data.get("ok", True) is not False, f"ok=false: {data}"
    return data


def outline_payload(*, strategy: str = "baseline", schema: str = "on", use_rag: bool = False, rag_mode: str = "bm25") -> dict[str, Any]:
    return {
        "conversationId": f"deepseek-acceptance-{int(time.time())}",
        "messages": [{"role": "user", "text": SAMPLE_TOPIC}],
        "provider": "deepseek",
        "strategy": strategy,
        "schema": schema,
        "minSlides": 6,
        "maxSlides": 8,
        "useRag": use_rag,
        "corpusId": "development_of_AI",
        "ragMode": rag_mode,
        "ragMaxRounds": 1,
        "ragMaxSnippets": 4,
        "ragConcurrency": 1,
    }


def summarize_outline(data: dict[str, Any]) -> dict[str, Any]:
    outline = data.get("outline") or {}
    chapters = outline.get("chapters") or []
    pages = [p for c in chapters for p in (c.get("pages") or [])]
    assert outline.get("title"), data
    assert chapters, data
    assert pages, data
    return {
        "title": outline.get("title"),
        "chapter_count": len(chapters),
        "page_count": len(pages),
        "quality": data.get("quality"),
        "elapsedS": data.get("elapsedS"),
        "schemaValid": data.get("schemaValid"),
        "rag": data.get("rag"),
    }


def run_tests(base_url: str | None = None) -> list[dict[str, Any]]:
    server_proc: subprocess.Popen[str] | None = None
    if base_url is None:
        base_url = "http://127.0.0.1:18081"
        server_proc = start_server(base_url)
    client = Client(base_url)
    results: list[dict[str, Any]] = []
    try:
        run_case(results, "TC-IP-03", "Input Processing", "Dynamic questionnaire with DeepSeek", lambda: {
            "response": parse_json_response(client.post("/api/questionnaire", json={"topic": SAMPLE_TOPIC, "provider": "deepseek"}))
        })

        run_case(results, "TC-WEB-01", "Input Processing", "Web search source retrieval", lambda: {
            "response": parse_json_response(client.post("/api/search/web", json={"query": "人工智能 发展 简史", "maxResults": 3}))
        })

        for alias, strategy in [
            ("qwen_simulated_by_deepseek", "baseline"),
            ("deepseek", "few_shot"),
            ("glm_simulated_by_deepseek", "cot_silent"),
        ]:
            def run_outline(alias: str = alias, strategy: str = strategy) -> dict[str, Any]:
                data = parse_json_response(client.post("/api/outline", json=outline_payload(strategy=strategy, schema="on")))
                summary = summarize_outline(data)
                summary["model_alias"] = alias
                summary["actual_provider"] = "deepseek"
                summary["strategy"] = strategy
                return summary

            run_case(
                results,
                f"TC-SO-MODEL-{alias.upper()}",
                "Structured Outline",
                f"Simulated model run ({alias}, actual provider=deepseek, strategy={strategy})",
                run_outline,
            )

        run_case(results, "TC-RAG-01", "RAG", "DeepSeek outline generation with BM25 RAG", lambda: summarize_outline(
            parse_json_response(client.post("/api/outline", json=outline_payload(strategy="baseline", schema="on", use_rag=True, rag_mode="bm25")))
        ))
        return results
    finally:
        if server_proc is not None:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_proc.kill()


def write_results(results: list[dict[str, Any]], label: str) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = RESULTS_DIR / f"{stamp}_{label}.json"
    md_path = RESULTS_DIR / f"{stamp}_{label}.md"
    summary: dict[str, int] = {}
    for item in results:
        summary[item["status"]] = summary.get(item["status"], 0) + 1
    payload = {"generated_at": now_iso(), "label": label, "summary": summary, "results": results}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# DeepSeek Acceptance Results ({label})",
        "",
        f"- Generated at: {payload['generated_at']}",
        f"- Summary: {summary}",
        "- Note: qwen/glm model rows are simulated with actual provider `deepseek`, because only DeepSeek API key is available.",
        "",
        "| ID | Requirement | Test | Status | Duration(s) | Notes |",
        "|---|---|---|---|---:|---|",
    ]
    for item in results:
        notes = item["error"] or json.dumps(item["details"], ensure_ascii=False)[:220]
        notes = notes.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {item['id']} | {item['requirement']} | {item['name']} | {item['status']} | {item['duration_s']} | {notes} |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="deepseek")
    parser.add_argument("--base-url", default=None)
    args = parser.parse_args()
    results = run_tests(args.base_url)
    write_results(results, args.label)
    return 0 if all(r["status"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
