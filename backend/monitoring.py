from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar


logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parent
DEFAULT_METRICS_PATH = BACKEND_ROOT / "logs" / "api_usage_metrics.json"
RECENT_ERROR_LIMIT = 50

ERROR_LLM_API = "llm_api_error"
ERROR_EMBEDDING = "embedding_error"
ERROR_TIMEOUT = "timeout_error"
ERROR_WEB_SEARCH = "web_search_error"
ERROR_CONFIG = "config_error"
ERROR_PARSE = "parse_error"
ERROR_UNKNOWN = "unknown_error"

T = TypeVar("T")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_stats() -> Dict[str, Any]:
    return {
        "request_count": 0,
        "success_count": 0,
        "failure_count": 0,
        "total_elapsed_ms": 0.0,
        "avg_elapsed_ms": 0.0,
        "max_elapsed_ms": 0.0,
    }


def _new_snapshot() -> Dict[str, Any]:
    now = _utc_now()
    return {
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "totals": _empty_stats(),
        "by_provider": {},
        "by_api_type": {},
        "by_operation": {},
        "by_error_category": {},
        "recent_errors": [],
    }


def _clean_key(value: Optional[str], fallback: str) -> str:
    text = str(value or "").strip()
    return text if text else fallback


def classify_api_error(exc: BaseException, *, api_type: str = "") -> str:
    """Classify external API failures into coarse debugging categories."""
    exc_name = exc.__class__.__name__.lower()
    message = str(exc).lower()
    api_type = api_type.lower()
    combined = f"{exc_name} {message}"

    if "timeout" in combined or isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return ERROR_TIMEOUT
    if api_type == "embedding" or "embed" in combined or "embedding" in combined:
        return ERROR_EMBEDDING
    if api_type == "web_search" or "serp" in combined or "jina" in combined or "search" in combined:
        return ERROR_WEB_SEARCH
    if isinstance(exc, (KeyError, ValueError)) or "api key" in combined or "config" in combined:
        return ERROR_CONFIG
    if isinstance(exc, (json.JSONDecodeError, TypeError)) or "json" in combined or "parse" in combined:
        return ERROR_PARSE
    if api_type == "llm" or "llm" in combined or "chat" in combined or "model" in combined:
        return ERROR_LLM_API
    return ERROR_UNKNOWN


def user_facing_error(exc: BaseException, *, api_type: str = "") -> str:
    category = classify_api_error(exc, api_type=api_type)
    message = str(exc).strip() or exc.__class__.__name__
    return f"{category}: {message}"


class ApiUsageMonitor:
    def __init__(
        self,
        metrics_path: Path = DEFAULT_METRICS_PATH,
        *,
        recent_error_limit: int = RECENT_ERROR_LIMIT,
    ) -> None:
        self.metrics_path = metrics_path
        self.recent_error_limit = recent_error_limit
        self._lock = threading.RLock()
        self._data = _new_snapshot()
        self._load()

    def _load(self) -> None:
        with self._lock:
            if not self.metrics_path.exists():
                return
            try:
                raw = self.metrics_path.read_text(encoding="utf-8").strip()
                if not raw:
                    return
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError("metrics root is not an object")
                self._data = self._normalize_snapshot(data)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "api_metrics_load_failed path=%s error=%s",
                    self.metrics_path,
                    exc,
                )
                self._data = _new_snapshot()

    def _normalize_snapshot(self, data: Dict[str, Any]) -> Dict[str, Any]:
        snapshot = _new_snapshot()
        for key in ("version", "created_at", "updated_at"):
            if key in data:
                snapshot[key] = data[key]
        for key in ("totals", "by_provider", "by_api_type", "by_operation", "by_error_category"):
            value = data.get(key)
            if isinstance(value, dict):
                snapshot[key] = value
        errors = data.get("recent_errors")
        if isinstance(errors, list):
            snapshot["recent_errors"] = errors[-self.recent_error_limit :]
        return snapshot

    def _save_locked(self) -> None:
        self.metrics_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.metrics_path.with_name(f"{self.metrics_path.name}.tmp")
        tmp_path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp_path, self.metrics_path)

    def _update_stats(self, stats: Dict[str, Any], *, success: bool, elapsed_ms: float) -> None:
        stats["request_count"] = int(stats.get("request_count", 0)) + 1
        if success:
            stats["success_count"] = int(stats.get("success_count", 0)) + 1
        else:
            stats["failure_count"] = int(stats.get("failure_count", 0)) + 1
        stats["total_elapsed_ms"] = round(float(stats.get("total_elapsed_ms", 0.0)) + elapsed_ms, 3)
        stats["max_elapsed_ms"] = round(max(float(stats.get("max_elapsed_ms", 0.0)), elapsed_ms), 3)
        count = max(int(stats.get("request_count", 0)), 1)
        stats["avg_elapsed_ms"] = round(float(stats["total_elapsed_ms"]) / count, 3)

    def record(
        self,
        *,
        api_type: str,
        provider: Optional[str],
        operation: str,
        success: bool,
        elapsed_ms: float,
        error: Optional[BaseException] = None,
        error_category: Optional[str] = None,
    ) -> None:
        api_type = _clean_key(api_type, "unknown")
        provider = _clean_key(provider, "unknown")
        operation = _clean_key(operation, "unknown")
        elapsed_ms = round(max(float(elapsed_ms), 0.0), 3)

        with self._lock:
            self._data["updated_at"] = _utc_now()
            self._update_stats(self._data["totals"], success=success, elapsed_ms=elapsed_ms)
            for bucket_name, key in (
                ("by_provider", provider),
                ("by_api_type", api_type),
                ("by_operation", f"{api_type}.{operation}"),
            ):
                bucket = self._data[bucket_name]
                stats = bucket.setdefault(key, _empty_stats())
                self._update_stats(stats, success=success, elapsed_ms=elapsed_ms)

            if not success:
                category = error_category or (
                    classify_api_error(error, api_type=api_type) if error else ERROR_UNKNOWN
                )
                category_stats = self._data["by_error_category"].setdefault(category, _empty_stats())
                self._update_stats(category_stats, success=False, elapsed_ms=elapsed_ms)
                err_entry = {
                    "timestamp": _utc_now(),
                    "api_type": api_type,
                    "provider": provider,
                    "operation": operation,
                    "error_category": category,
                    "elapsed_ms": elapsed_ms,
                    "error_type": error.__class__.__name__ if error else "",
                    "message": str(error)[:500] if error else "",
                }
                self._data["recent_errors"].append(err_entry)
                self._data["recent_errors"] = self._data["recent_errors"][-self.recent_error_limit :]
                logger.warning(
                    "api_call_failed api_type=%s provider=%s operation=%s "
                    "error_category=%s elapsed_ms=%.3f error_type=%s error=%s",
                    api_type,
                    provider,
                    operation,
                    category,
                    elapsed_ms,
                    err_entry["error_type"],
                    err_entry["message"],
                )

            try:
                self._save_locked()
            except Exception as exc:  # noqa: BLE001
                logger.warning("api_metrics_save_failed path=%s error=%s", self.metrics_path, exc)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data, ensure_ascii=False))

    def reset(self) -> Dict[str, Any]:
        with self._lock:
            self._data = _new_snapshot()
            self._save_locked()
            return self.snapshot()


monitor = ApiUsageMonitor()


def record_api_call(
    *,
    api_type: str,
    provider: Optional[str],
    operation: str,
    func: Callable[[], T],
) -> T:
    start = time.perf_counter()
    try:
        result = func()
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        monitor.record(
            api_type=api_type,
            provider=provider,
            operation=operation,
            success=False,
            elapsed_ms=elapsed_ms,
            error=exc,
        )
        raise
    elapsed_ms = (time.perf_counter() - start) * 1000
    monitor.record(
        api_type=api_type,
        provider=provider,
        operation=operation,
        success=True,
        elapsed_ms=elapsed_ms,
    )
    return result


async def record_api_call_async(
    *,
    api_type: str,
    provider: Optional[str],
    operation: str,
    func: Callable[[], Awaitable[T]],
) -> T:
    start = time.perf_counter()
    try:
        result = await func()
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        monitor.record(
            api_type=api_type,
            provider=provider,
            operation=operation,
            success=False,
            elapsed_ms=elapsed_ms,
            error=exc,
        )
        raise
    elapsed_ms = (time.perf_counter() - start) * 1000
    monitor.record(
        api_type=api_type,
        provider=provider,
        operation=operation,
        success=True,
        elapsed_ms=elapsed_ms,
    )
    return result
