from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
RESULTS_DIR = PROJECT_ROOT / "test_results"


TOPICS = [
    "人工智能发展简史",
    "AI Agent 在企业办公中的应用",
    "生成式 AI 对教育的影响",
    "大模型幻觉问题与治理方法",
    "RAG 技术原理与应用场景",
    "软件项目管理中的风险控制",
    "敏捷开发流程介绍",
    "智能 PPT 大纲生成系统项目汇报",
    "多模态人工智能发展趋势",
    "知识库问答系统设计",
    "云原生部署与 Docker Compose",
    "AI 工具提升学习效率的方法",
    "企业数字化转型路线图",
    "开源大模型与闭源大模型对比",
    "软件工程课程项目总结",
    "提示词工程的基本方法",
    "自动化测试在软件交付中的作用",
    "向量检索与关键词检索对比",
    "人工智能安全与伦理",
    "高校课程汇报 PPT 设计方法",
]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


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


def payload(topic: str, idx: int) -> dict[str, Any]:
    return {
        "conversationId": f"success-rate-{idx}-{int(time.time())}",
        "messages": [
            {
                "role": "user",
                "text": f"主题：{topic}\n受众：软件工程课程师生\n目标：生成 4-6 页课程汇报 PPT 大纲。\n要求：每页 3-5 条要点，备注中给出演讲提示。",
            }
        ],
        "provider": "deepseek",
        "strategy": "baseline",
        "schema": "on",
        "minSlides": 4,
        "maxSlides": 6,
        "useRag": False,
    }


def valid_generation(data: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    if data.get("ok") is False:
        return False, str(data.get("error")), {}
    outline = data.get("outline") or {}
    chapters = outline.get("chapters") or []
    pages = [p for c in chapters for p in (c.get("pages") or [])]
    if not outline.get("title") or not chapters or not pages:
        return False, "missing title/chapters/pages", {"outline": outline}
    quality = data.get("quality") or {}
    if data.get("schemaValid") is False:
        return False, "schemaValid=false", {"quality": quality}
    return True, "", {
        "title": outline.get("title"),
        "chapter_count": len(chapters),
        "page_count": len(pages),
        "quality": quality,
        "elapsedS": data.get("elapsedS"),
        "schemaValid": data.get("schemaValid"),
    }


def run(base_url: str | None, runs: int) -> dict[str, Any]:
    server_proc: subprocess.Popen[str] | None = None
    if base_url is None:
        base_url = "http://127.0.0.1:18082"
        server_proc = start_server(base_url)
    rows = []
    try:
        for idx, topic in enumerate(TOPICS[:runs], start=1):
            start = time.perf_counter()
            try:
                resp = requests.post(f"{base_url}/api/outline", json=payload(topic, idx), timeout=180)
                duration = round(time.perf_counter() - start, 3)
                if resp.status_code != 200:
                    rows.append({"idx": idx, "topic": topic, "status": "FAIL", "duration_s": duration, "error": f"HTTP {resp.status_code}: {resp.text[:300]}"})
                    print(f"[FAIL] {idx}/{runs} {topic} HTTP {resp.status_code} ({duration}s)")
                    continue
                ok, error, details = valid_generation(resp.json())
                rows.append({
                    "idx": idx,
                    "topic": topic,
                    "status": "PASS" if ok else "FAIL",
                    "duration_s": duration,
                    "error": error,
                    "details": details,
                })
                print(f"[{'PASS' if ok else 'FAIL'}] {idx}/{runs} {topic} ({duration}s)")
                if error:
                    print(f"    {error}")
            except Exception as exc:  # noqa: BLE001
                duration = round(time.perf_counter() - start, 3)
                rows.append({"idx": idx, "topic": topic, "status": "ERROR", "duration_s": duration, "error": repr(exc)})
                print(f"[ERROR] {idx}/{runs} {topic} ({duration}s) {exc!r}")
        passed = sum(1 for r in rows if r["status"] == "PASS")
        total = len(rows)
        durations = [r["duration_s"] for r in rows]
        return {
            "generated_at": now_iso(),
            "actual_provider": "deepseek",
            "runs": total,
            "passed": passed,
            "success_rate": round(passed / total, 4) if total else 0.0,
            "max_duration_s": max(durations) if durations else None,
            "avg_duration_s": round(sum(durations) / len(durations), 3) if durations else None,
            "rows": rows,
        }
    finally:
        if server_proc is not None:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_proc.kill()


def write(payload_obj: dict[str, Any], label: str) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = RESULTS_DIR / f"{stamp}_{label}.json"
    md_path = RESULTS_DIR / f"{stamp}_{label}.md"
    json_path.write_text(json.dumps(payload_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# DeepSeek Success Rate Test ({label})",
        "",
        f"- Generated at: {payload_obj['generated_at']}",
        f"- Runs: {payload_obj['runs']}",
        f"- Passed: {payload_obj['passed']}",
        f"- Success rate: {payload_obj['success_rate']:.2%}",
        f"- Average duration: {payload_obj['avg_duration_s']}s",
        f"- Max duration: {payload_obj['max_duration_s']}s",
        "",
        "| # | Topic | Status | Duration(s) | Error |",
        "|---:|---|---|---:|---|",
    ]
    for row in payload_obj["rows"]:
        error = (row.get("error") or "").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {row['idx']} | {row['topic']} | {row['status']} | {row['duration_s']} | {error} |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--label", default="deepseek_success_rate")
    parser.add_argument("--base-url", default=None)
    args = parser.parse_args()
    payload_obj = run(args.base_url, args.runs)
    write(payload_obj, args.label)
    return 0 if payload_obj["success_rate"] >= 0.95 else 1


if __name__ == "__main__":
    raise SystemExit(main())
