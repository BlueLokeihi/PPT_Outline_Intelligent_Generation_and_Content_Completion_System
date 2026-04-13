# llm（大模型调用）

本目录用于统一封装大模型调用，当前基于 `liter-llm`。

## 配置
- 默认读取：`config/models.json`
- 每个 provider 配置包含：`base_url`、`model`、`api_key_env` 等

## 使用方法（代码）

```python
from llm.client import build_provider, chat_text_sync

client, model, defaults, _cfg = build_provider("qwen")
text = chat_text_sync(
    client,
    model=model,
    messages=[{"role": "user", "content": "hello"}],
    temperature=defaults.temperature,
    top_p=defaults.top_p,
    max_tokens=256,
)
print(text)
```