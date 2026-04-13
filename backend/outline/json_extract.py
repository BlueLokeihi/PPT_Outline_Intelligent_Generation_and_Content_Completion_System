from __future__ import annotations

import json
import re
from typing import Any, Dict, Tuple


_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def extract_first_json_object(text: str) -> Tuple[Dict[str, Any] | None, str]:
    """从模型输出中提取第一个 JSON object。

    允许模型偶尔夹杂解释文字；会尝试：
    1) 直接 json.loads
    2) 正则抓取从第一个 { 到最后一个 } 的最大块
    """
    text = text.strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data, ""
        return None, "JSON 根节点不是 object"
    except Exception:
        pass

    m = _JSON_OBJECT_RE.search(text)
    if not m:
        return None, "未找到 JSON object 块"

    candidate = m.group(0)
    try:
        data = json.loads(candidate)
        if isinstance(data, dict):
            return data, ""
        return None, "JSON 根节点不是 object"
    except Exception as e:
        return None, f"JSON 解析失败: {e}"
