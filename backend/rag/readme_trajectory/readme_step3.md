# RAG 模块 · Step 3：基于大纲节点的查询改写 + 多轮检索

把 [Step 2](readme_step2.md) 的检索器变成"以 PPT 页面为单位"使用：让 LLM 替每一页
写出 2-3 条短 query 去检索；如果首轮召回质量差，再让 LLM 看着首轮结果改写一次。

这正对应作业要求中：
> 探索基于大纲节点的查询改写与多轮检索策略

---

## 1. 设计目标

| 目标 | 怎么做 |
|---|---|
| 每页 PPT 自动产出可检索的 query | LLM 看页面上下文（章节+页+草稿要点+演讲备注）直接产出短 query |
| 多 query 覆盖不同知识维度 | Prompt 强约束：从 `定义/事实/数据/案例/对比/历史/影响/方法` 选不重复标签 |
| 召回弱时再尝试 | 反馈式改写：把首轮 query + 首轮召回片段一并喂给 LLM，让它"换一种问法" |
| 多 query 结果聚合不重复 | 同一 chunk 跨 query 出现时，取最高 score；按 score 降序取 top-k |
| 失败可观测 | 每页输出每轮的 queries / coverage / per-query 命中明细，便于 debug |

---

## 2. 新增文件

```
backend/rag/
├── query_rewriter.py          (新增) LLM 改写：首轮 + 反馈轮
├── research.py                (新增) 单页编排 + CLI
└── test_outlines/
    ├── demo_aligned.json              对齐 demo 语料的测试大纲
    └── demo_aligned_research.json     研究结果导出（自动生成）
```

不改动 [retriever.py](retriever.py) / [embedder.py](embedder.py) / [bm25.py](bm25.py) / [store.py](store.py)。
LLM 调用复用现有 [llm/client.py](../llm/client.py) 的 `build_provider` + `chat_text_sync`。

---

## 3. 用法

### 3.1 准备一个大纲 JSON

支持两种来源：
- 你们 `compare`/`single` 模式产出的 [outline/output/*.json](../outline/output/)（外层有 `meta.outline`，自动识别）
- 直接的 `{title, chapters: [{title, pages: [{title, bullets, notes}]}]}` 结构

参考样例：[test_outlines/demo_aligned.json](test_outlines/demo_aligned.json)

### 3.2 跑研究流程

```powershell
cd backend
# 全部页面
python -m rag.research --corpus demo --outline rag/test_outlines/demo_aligned.json

# 仅某一页
python -m rag.research --corpus demo --outline rag/test_outlines/demo_aligned.json --chapter 1 --page 0

# 导出结果 JSON（供后续 Step 4 enricher 读取）
python -m rag.research --corpus demo --outline rag/test_outlines/demo_aligned.json \
    --out rag/test_outlines/demo_aligned_research.json
```

关键参数：
- `--mode hybrid|vector|bm25`：检索模式（默认 hybrid）
- `--threshold 0.45`：coverage 低于该值则触发第二轮改写（默认 0.45）
- `--max-rounds 2`：最大轮数（设 1 即关闭多轮）
- `--rewrite-provider qwen`：改写所用的 LLM provider
- `--embed-provider qwen`：embedding provider（必须与建索引时一致）

### 3.3 终端输出阅读

```
=== Ch0.P1  Schema 约束与结构化输出 / Schema Off 的失败模式
    bullets=['GLM 在无 Schema 时的输出问题', '...', '...']
  Round1 queries=['GLM无Schema输出格式漂移案例', '...', '...']  coverage=0.715
    final 6 chunks (top score=0.0328)
      [1] exception. This highlights GLM's weakness in structured output robustness ...
```

- `Round1 queries=[...]`：LLM 写出的查询
- `coverage=0.715`：当前最高 vector_score（hybrid/vector 模式），低于 `--threshold` 才触发 Round2
- `final N chunks`：跨多 query 聚合 + 排序后的 top-k

### 3.4 导出 JSON 结构（供 Step 4 用）

```json
{
  "outline_title": "...",
  "corpus": "demo",
  "mode": "hybrid",
  "embedding_model": "text-embedding-v3",
  "rewrite_provider": "qwen",
  "rewrite_model": "qwen-plus",
  "results": [
    {
      "chapter_idx": 0,
      "page_idx": 1,
      "chapter_title": "...",
      "page_title": "...",
      "rounds": [
        {
          "round": 1,
          "queries": ["...", "...", "..."],
          "intent_tags": ["事实", "案例", "对比"],
          "coverage": 0.7151,
          "per_query_hits": { "<query>": [{score,vector_score,bm25_score,source,chunk_index,snippet}, ...], ... }
        }
      ],
      "final_chunks": [
        { "score":..., "vector_score":..., "bm25_score":..., "vector_rank":..., "bm25_rank":...,
          "source":..., "chunk_index":..., "char_start":..., "char_end":..., "text":... },
        ...
      ],
      "error": ""
    },
    ...
  ]
}
```

---

## 4. 设计要点

### 4.1 Prompt 设计（[query_rewriter.py](query_rewriter.py)）

**首轮**：上下文带章节标题 + 页标题 + bullets 草稿 + notes，要求：
- 每条 ≤ 20 字（中文）或 ≤ 8 个英文词
- 多条覆盖不同 intent（标签从 8 个候选挑不重复的）
- 不照抄页标题
- 与整体主题保持一致，不漂移

**反馈轮**：把首轮 queries + top-3 召回片段（截 200 字）一并喂回，要求：
- 避开上一轮已用措辞
- 加入领域同义词（如 transformer→注意力机制）
- 更聚焦关键词、数字、专有名词
- temperature 调高到 0.5（首轮 0.3），鼓励发散

**输出契约**：严格 JSON `{"queries":[...], "intent_tags":[...]}`，复用 [outline/json_extract.py](../outline/json_extract.py) 解析。

### 4.2 多轮触发条件（[research.py](research.py) `_coverage_signal`）

最简单也最可解释的信号：**当前所有 chunk 中 `vector_score` 的最大值**。

| 模式 | coverage 信号 |
|---|---|
| hybrid / vector | `max(vector_score)` |
| bm25 | `max(bm25_score) / 5.0`（BM25 无上界，5.0 是经验"还可以"的下限） |

低于 `--threshold` 触发 Round 2；阈值默认 0.45（实测 demo 语料下，**真正相关**的页都
能跑到 0.6+，**完全无关**的页落在 0.5 上下）。这个阈值会随语料和 embedding 模型变化，
后续 Step 6（评估）可以用网格搜索调到适合自己语料的值。

### 4.3 多 query 结果聚合（[research.py](research.py) `_merge_chunks`）

每个 query 跑一次 `HybridRetriever.search`，得到自己的 top-k；跨 query 合并时：
- 用 `(source, chunk_index)` 当 key 去重
- 同一 chunk 在多个 query 里出现时，**取该 chunk 在所有出现里的最高 score**
- 全局按 score 降序，取 top-k

不做加权平均：因为 query 数量在 2-3 之间浮动，平均会引入"出现次数"偏差，"最高分"
更稳定。

---

## 5. 验收记录

测试索引：49 chunks（[corpus/demo/PPT_Outline_Generation_Strategy_Report.pdf](corpus/demo/)）
测试大纲：[test_outlines/demo_aligned.json](test_outlines/demo_aligned.json)（5 页 × 3 章）
LLM：qwen-plus

| 页面 | Round1 coverage | 触发 Round2 | 结果 |
|---|---|---|---|
| Ch0.P0 Schema On 工程可靠性 | 0.724 | 否 | ✅ Top1 命中 §7.1 / §8.3 Schema On 内容 |
| Ch0.P1 Schema Off 失败模式 | 0.715 | 否 | ✅ Top1 直接命中"GLM's weakness in structured output robustness" |
| Ch1.P0 Few-Shot 效率与规范性 | 0.694 | 否 | ✅ Top3 覆盖实验数据表 + §5.1 + §3.1 |
| Ch1.P1 CoT-Silent 优势场景 | 0.696 | 否 | ✅ Top2 命中 §3.2 CoT Silent — Logic and Depth |
| Ch2.P0 Transformer 注意力（无关页） | 0.535 | ✅ 是（threshold=0.55）| ✅ Round2 改写不同表述（"数学公式推导"→"矩阵运算定义"），coverage 仍 0.535，**正确识别"语料里没有"** |

关键观察：
- 多轮没有"硬救"——当语料确实没相关内容时，第二轮改写也救不回来；这是好事，避免了
  伪造检索结果送给后续 enricher
- LLM 改写的 query 普遍比直接拼 page title 更聚焦（自动加入了"对比数据"、"原理"、
  "失败模式"等 intent 信号词）

---

## 6. 已知限制 / 后续阶段

| 限制 | 处理 |
|---|---|
| coverage 信号比较粗（max vector_score）；无关页可能 0.5 蒙混过关 | Step 6 评估时再校准 threshold；或加入"top-3 平均 + 是否含数字"复合判据 |
| 第二轮改写仍可能召回不到（语料缺失），但不会在 final_chunks 里区分"低质量但保留" | Step 4 enricher 读到 coverage 低于阈值时主动标记"low confidence"，并触发 Web Search（DeepResearch lite） |
| 没有加自定义 jieba 词典，专业术语切分仍可能差强人意 | 如果实际语料发现专业词被切碎再补 |
| LLM 改写每页要花 1-2 次 chat 调用，跑全部页面会比较慢/费 | 后续可以加并发（一次跑多页改写）+ 缓存（同一 page hash → 同一 query 集） |

---

## 7. 常见问题

**Q：为什么 hybrid 的 final score 看起来这么小（0.03 左右）？**
A：hybrid score 是 RRF 分（≈ 1/(60+1) + 1/(60+rank2) ≈ 0.03），不可与 vector 余弦
（0~1）直接对比。看 `vector_score` / `bm25_score` 这两个原始分判断单路命中强度。

**Q：能否只用 query 改写、不用多轮？**
A：可以。`--max-rounds 1` 即关闭。研究阶段仍然有用：你能看到 LLM 把 page 草稿"翻译"
成了什么 query。

**Q：能否换一个 LLM 做改写？**
A：可以。`--rewrite-provider deepseek`/`glm`/`qwen`。改写比较吃指令遵循，建议用
qwen-plus 或 deepseek-chat；GLM-4 在严格 JSON 输出上偶尔不稳，与你们 §3 实验报告中
观察到的现象一致。

**Q：rewrite 输出不是合法 JSON 怎么办？**
A：[query_rewriter.py](query_rewriter.py) 会用 `extract_first_json_object` 兜底（先
直接 `json.loads`，失败再正则抓最大 `{...}` 块），返回 `RewriteResult(error=...)`。
`research.py` 看到 error 会跳过这页并打印原因，不会影响其他页。
