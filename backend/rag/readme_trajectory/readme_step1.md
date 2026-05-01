# RAG 模块 · Step 1：最小检索骨架

本阶段目标：**让本地文档可以被建索引、被语义检索**，为后续的"大纲节点查询改写 / 多轮检索 / 内容浓缩"打地基。
本阶段**不**涉及大纲补全、查询改写、Web Search、评估指标。

---

## 1. 能做什么

- 把 `.txt` / `.md` / `.pdf` 文档放进一个目录，一条命令建出 FAISS 向量索引
- 用一句自然语言（中英均可）从索引里检索 Top-k 相关片段，附得分与来源
- 重建索引时命中 embedding 磁盘缓存，**零 API 调用**

不做的事：BM25 / 混合召回 / RRF / 查询改写 / Web Search / 大纲对接 / 前端 UI / 评估指标。这些放到后续阶段。

---

## 2. 文件结构

```
backend/rag/
├── __init__.py
├── chunker.py          # 文档加载 + 递归切块
├── embedder.py         # 批量 embedding + 磁盘缓存
├── store.py            # FAISS 索引 + 元数据读写
├── index.py            # CLI: 建索引
├── search.py           # CLI: 查询测试
├── corpus/             # ← 你放原始文档（按 corpus id 分目录）
│   └── <corpusId>/
├── indexes/            # ← 自动生成：每个 corpus 的索引
│   └── <corpusId>/
│       ├── index.faiss
│       ├── meta.jsonl
│       └── manifest.json
└── cache/              # ← 自动生成：embedding 缓存（按 provider+模型）
    └── <provider>__<model>.jsonl
```

---

## 3. 快速开始

### 3.1 安装依赖

```powershell
cd backend
pip install -r requirements.txt
```

新增的三个包：`faiss-cpu`、`pypdf`、`numpy`（约 30 MB，纯 CPU，无需 GPU）。

### 3.2 准备语料

把文档放进 `backend/rag/corpus/<corpusId>/`，例如：

```
backend/rag/corpus/demo/
├── reportA.pdf
├── notes.md
└── data.txt
```

### 3.3 建索引

```powershell
cd backend
python -m rag.index --corpus demo
```

可选参数：
- `--provider qwen`：用哪个 provider 的 embedding（默认 qwen，复用 `QWEN_API_KEY`）
- `--model text-embedding-v3`：指定 embedding 模型
- `--chunk-size 500` / `--overlap 80`：切块参数
- `--no-cache`：禁用磁盘缓存（debug 用）

输出示例：
```
[1/4] 扫描并切块: ...corpus/demo
      共 49 个 chunk（来自 1 个文件）
[2/4] 加载 embedding 配置: provider=qwen
      model=text-embedding-v3, dim=1024, batch=16
      cache: ...cache/qwen__text-embedding-v3.jsonl (已存 0 条)
[3/4] 调用 embedding API
  embedding batch 1/4 (size=16)
  ...
[4/4] 写入 FAISS 索引
      已写入: ...indexes/demo
Done.
```

### 3.4 查询

```powershell
python -m rag.search --corpus demo --query "你的问题" -k 5
```

输出每条命中：score（余弦相似度）、source（源文件相对路径）、chunk 序号、文本片段。

---

## 4. 设计要点

### 4.1 切块策略（`chunker.py`）

- **递归字符切分**，分隔符优先级：双换行 → 单换行 → 中英文句号/问号/感叹号 → 空格 → 硬切字符
- 每层只用一个分隔符；某段仍超长时用"剩余 separators"递归，避免死循环
- 默认 `chunk_size=500` / `overlap=80`（约 1-2 个段落，重叠保留上下文）
- 元数据：`source`（相对路径）、`chunk_index`（块序号）、`char_start`/`char_end`（在源清洗后文本中的位置，便于将来溯源高亮）

### 4.2 Embedding 调用（`embedder.py`）

- 直接复用 [llm/client.py](../llm/client.py) 的 `liter_llm.LlmClient`，**不引入新 SDK**
- API key 从环境变量取（与现有 chat 流程一致），统一在 [config/models.json](../config/models.json) 里配置
- 默认模型：`text-embedding-v3`（DashScope 通义嵌入，1024 维）
- **批量发送**：默认 16 条/批
- **失败二分重试**：单批超长报错时，自动二分递归，避免一条问题文本拖垮整批
- **磁盘缓存**：按 `SHA1(model + "\x00" + text)` 当 key，写 JSONL 文件，跨次重建可复用

### 4.3 向量库（`store.py`）

- 用 FAISS `IndexFlatIP`（内积），向量入库前已 L2 归一化 → **score 等价余弦相似度**，范围 [-1, 1]，越大越相关
- 三个文件：
  - `index.faiss`：FAISS 二进制索引
  - `meta.jsonl`：每行一个 chunk 的元数据 + 原文（与 FAISS 内部 id 一一对应）
  - `manifest.json`：embedding 模型、维度、大小、构建时间（搜索时用于校对模型一致）
- 数据量 < 10 万 chunks 时，平铺索引完全够用，无需 IVF/HNSW

### 4.4 模型一致性保护

`search.py` 会校对 `manifest.json` 里记录的 embedding 模型与当前用的是否一致；若不一致打印警告——**不同模型的向量空间不通用**，混用会得到无意义的结果。

---

## 5. 验收记录（已通过）

| 项目 | 结果 |
|---|---|
| `corpus/demo/PPT_Outline_Generation_Strategy_Report.pdf` 建索引 | ✅ 49 chunks，1024 维 |
| `--query "schema 校验失败"` | Top1 score=0.6731，命中 GLM schema-off 失败段落 |
| `--query "few-shot 提示策略效果"`（中文 query → 英文文档） | Top1 score=0.7054，正中 §3.1 Few-Shot Prompting |
| 重跑 `index` 验证缓存 | ✅ "已存 49 条"，无 `embedding batch` 日志 = 零 API 调用 |

---

## 6. 已知限制 / 后续阶段处理

| 限制 | 后续阶段 |
|---|---|
| 仅向量召回，对数字/术语不够鲁棒 | Step 2：加 BM25 + RRF 混合检索 |
| 一次只能问一个 query，不知道一个 page 应该查什么 | Step 3：基于大纲节点的查询改写（LLM 生成 2-3 条 query） |
| 检索片段还没"压"成 PPT bullets | Step 4：内容浓缩 + 大纲补全（enricher） |
| 没有 HTTP 端点，前端用不到 | Step 5：FastAPI 接口 + 前端知识库管理 Tab |
| 没有 RAG 前后对比指标 | Step 6：扩展 [outline/evaluation.py](../outline/evaluation.py) |
| 每个 corpus 当前只能整体重建，不能增量 | 视需要，可在 Step 5 顺手加 |

---

## 7. 常见问题

**Q：报 `未找到 qwen 的 API key（环境变量 QWEN_API_KEY）`？**
A：检查 `backend/.env` 是否设置了 `QWEN_API_KEY=...`。运行 CLI 会自动加载该文件。

**Q：embedding 维度对不上？**
A：首次调用时若实际返回维度与代码默认不同，`embedder.py` 会自动以实际维度为准并写进 manifest，不会报错。

**Q：可以换成别的 embedding 模型吗？**
A：可以。命令行加 `--model your-model-name`；或在 [config/models.json](../config/models.json) 顶层加：
```json
"embedding": {
  "qwen": { "model": "text-embedding-v3", "dim": 1024, "batch_size": 16 }
}
```

**Q：rebuild 时想强制重新计算？**
A：删除 `backend/rag/cache/<provider>__<model>.jsonl`，或加 `--no-cache`。

**Q：FAISS 在 Windows 装不上？**
A：用 `pip install faiss-cpu`（不是 `faiss`），目前已发布 cp310/cp311 的 win-amd64 wheel。本项目已在 Python 3.10 + Windows 11 验证通过。
