"""统一的大模型调用封装（基于 liter-llm）。

使用示例（在 backend 目录下）：

```powershell
python -c "from llm.client import build_provider; c, model, defaults = build_provider('qwen'); print(model, defaults)"
```
"""
