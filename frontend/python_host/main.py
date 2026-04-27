from __future__ import annotations

from pathlib import Path

import webview

from bridge import BackendBridge


def main() -> None:
    frontend_root = Path(__file__).resolve().parents[1]
    dist_index = frontend_root / "dist" / "index.html"

    if not dist_index.exists():
        raise SystemExit(
            "未找到前端构建产物。请先执行 `npm install` 和 `npm run build`，再运行 python_host/main.py"
        )

    api = BackendBridge()
    window = webview.create_window(
        title="PPT Outline Prototype",
        url=dist_index.as_uri(),
        js_api=api,
        width=1450,
        height=930,
        min_size=(1100, 720),
    )

    webview.start(debug=False, window=window)


if __name__ == "__main__":
    main()
