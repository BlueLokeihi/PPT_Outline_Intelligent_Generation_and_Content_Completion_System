# RAG 模块 · Step 4：内容浓缩 + 大纲补全（enricher）

把 [Step 3](readme_step3.md) 给每页跑出来的 `final_chunks`（外部知识片段）压成
PPT 可用的精炼内容（3-6 条 bullets + ≤200 字 notes），并保留**溯源**。

这正对应作业要求中：
> 研究如何将检索到的长文本浓缩为适合单页 PPT 呈现的精炼内容（关键数据、核心观点、支撑论据）

---

## 1. 设计目标

| 目标 | 怎么做 |
|---|---|
| 单页可读、信息密度高 | LLM 输出 3-6 条 bullets，每条 ≤30 字（中文），优先保留可验证的数字/专有名词/年份 |
| 不伪造数据 | 强约束 prompt：bullets 与 notes 的事实必须有依据（来自片段或与原 bullets 一致） |
| 溯源可审计 | LLM 自报 `used_sources`（1-based 索引），后端据此回填 evidences 数组 |
| 召回弱时不胡编 | 把 research 阶段 coverage 映射到 confidence 标签（high/medium/low），低置信度提示 LLM 可以保留原 bullets，`used_sources` 可为空 |
| 不破坏老流程 | `evidences` 是 schema 上的**可选**字段；旧的"无 RAG"路径无需输出 |

---

## 2. 新增 / 改动文件

```
backend/
├── outline/
│   ├── types.py        (改动) 增加 Evidence dataclass + OutlinePage.evidences 可选字段
│   └── schema.py       (改动) 允许 page.evidences 字段（additionalProperties 仍然 false）
└── rag/
    ├── enricher.py     (新增) 单页浓缩核心逻辑（pure function，方便后续接 HTTP）
    └── enrich.py       (新增) CLI：research JSON + 原 outline → enriched outline
```

---

## 3. 用法

### 3.1 完整流水线（从主题到含证据的大纲）

```powershell
cd backend

# Step 1：建索引（一次性）
python -m rag.index --corpus demo

# Step 3：跑研究（query 改写 + 多轮检索）
python -m rag.research --corpus demo \
    --outline rag/test_outlines/demo_aligned.json \
    --out     rag/test_outlines/demo_aligned_research.json

# Step 4：浓缩为含证据的大纲
python -m rag.enrich \
    --research rag/test_outlines/demo_aligned_research.json \
    --outline  rag/test_outlines/demo_aligned.json \
    --out      rag/test_outlines/demo_aligned_enriched.json
```

### 3.2 CLI 参数

```
python -m rag.enrich --research ... --outline ... --out ...
    --provider qwen           # enrichment 用的 LLM provider（默认 qwen）
    --max-snippets 8          # 每页喂给 LLM 的最大片段数
    --snippet-chars 320       # 单片段截断字符数（防上下文炸裂）
    --temperature 0.3
    --skip-low-confidence     # 开关：检索 coverage 低的页跳过 LLM，保留原 bullets
    --low-threshold 0.4       # skip 触发阈值
```

### 3.3 输出结构

```jsonc
{
  "meta": {
    "source_outline": "rag/test_outlines/demo_aligned.json",
    "source_research": "rag/test_outlines/demo_aligned_research.json",
    "corpus": "demo",
    "embedding_model": "text-embedding-v3",
    "rewrite_provider": "qwen",
    "rewrite_model": "qwen-plus",
    "enrich_provider": "qwen",
    "enrich_model": "qwen-plus",
    "elapsed_s": 29.74,
    "schema_ok": true,
    "schema_error": "",
    "page_meta": [
      { "chapter_idx": 0, "page_idx": 0, "page_title": "...",
        "enrichment": "ok", "coverage": 0.7242, "confidence": "high",
        "used_source_ids": [2,3,5,6], "n_evidences": 4 },
      ...
    ]
  },
  "outline": {
    "title": "...",
    "chapters": [
      {
        "title": "...",
        "pages": [
          {
            "title": "...",
            "bullets": [ "...", "...", ... ],
            "notes": "...",
            "evidences": [
              {
                "text": "...",                       // 来源片段摘录（≤400 字）
                "source": "report.pdf",              // 文件相对路径
                "score": 0.0325,                     // hybrid RRF 分
                "chunk_index": 34
              }
            ]
          }
        ]
      }
    ]
  }
}
```

`outline` 节点完全符合 [outline/schema.py](../outline/schema.py)（`evidences` 已加到
schema 中作为可选字段），可以直接送给前端渲染或导出 PPT。

---

## 4. 设计要点

### 4.1 Prompt 强约束（[enricher.py](enricher.py) `_build_prompt`）

System：身份+硬性"只输出严格 JSON"。

User 主体三段：
1. **页面上下文**：整体主题 / 章节 / 页标题 / 原 bullets / 原 notes
2. **外部知识片段**：编号 1..N，每条带 `(来源: foo.pdf #chunkX)` 标签
3. **改写要求**：3-6 条 bullets / ≤30 字/条 / ≤200 字 notes / 用 `used_sources` 数组报告引用 / **不要凭空编造数字**

输出契约：`{"bullets":[...], "notes":"...", "used_sources":[1,3,...]}`，复用
[outline/json_extract.py](../outline/json_extract.py) 的兜底解析。

### 4.2 confidence 分桶（[enricher.py](enricher.py) `confidence_from_coverage`）

```
coverage >= 0.65   →  high
coverage >= 0.50   →  medium
else               →  low
```

low 桶时，prompt 会追加一句：
> 注意：本页检索召回质量较弱，外部片段可能与主题相关性不足。若片段不足以支撑改写，
> 请保留原 bullets 的核心，仅在确信无误时引用片段；used_sources 可以为空数组。

实测效果：medium/low 置信度的页 LLM 普遍把 `used_sources` 留空，**不会硬把不相关
的 chunk 当 evidence 报上来**。

### 4.3 schema 扩展（[outline/schema.py](../outline/schema.py)）

旧：`required: [title, bullets, notes]`，`additionalProperties: false`
新：在 `properties` 里加 `evidences`（可选数组），`required` 不变，
`additionalProperties` 仍然 false——意思是"要么不填 evidences；要填就必须符合子结构"。

这样：
- Step 1/2 的旧"无 RAG"路径输出**不带** evidences 时，schema 仍然校验通过
- enrich 输出**带** evidences 时也通过
- 但任何一边出现拼写错误的字段（如 `evidence` 单数）会被 schema 拒掉

### 4.4 解析容错（[enricher.py](enricher.py) `_parse`）

LLM 偶尔会：
- 在 JSON 外面包一层 ```json``` → 用现成的 `extract_first_json_object` 兜底
- `bullets` 长度超 200 字 / 数量超 10 → 硬截到 schema 上限
- `used_sources` 含越界编号或重复 → 过滤越界 + 去重
- `used_sources` 是 `["1", "3"]` 字符串 → `int(x)` 转换，转不成则跳过

---

## 5. 验收记录

测试输入：
- 索引：49 chunks（PPT_Outline_Generation_Strategy_Report.pdf）
- 大纲：5 页（其中 1 页故意主题无关）
- LLM：qwen-plus（temperature=0.3）

| 页面 | coverage | confidence | bullets 数 | evidences 数 | LLM 行为 |
|---|---|---|---|---|---|
| Ch0.P0 Schema On 工程可靠性 | 0.724 | high | 4 | 4 | ✅ 引入具体数字 "GLM 失败率 100%→0%"、"耗时减少 15-25%" |
| Ch0.P1 Schema Off 失败模式 | 0.715 | high | 4 | 0 | ⚠️ 高 coverage 但 LLM 选择不引（可能因为顶级片段是综述性的，不适合做单条 evidence） |
| Ch1.P0 Few-Shot 效率与规范性 | 0.694 | high | 4 | 2 | ✅ 引 §3.1 + §5.1 |
| Ch1.P1 CoT-Silent 优势场景 | 0.696 | high | 4 | 3 | ✅ 引 §3.2 + 推荐配置段 |
| **Ch2.P0 Transformer 注意力（无关页）** | 0.535 | medium | 4 | **0** | ✅ **正确拒绝伪造引用**：bullets 是基于 LLM 通用知识写的 Transformer 内容，notes 里坦诚标注"与实验报告主体非直接重叠" |

总耗时：29.74s（5 页，~6s/页）
Schema 校验：✅ 通过

**关键样例对比**（Ch0.P0 Schema On 工程可靠性）：

| 原 bullets | 浓缩后 bullets |
|---|---|
| Schema 校验对 JSON 解析失败率的影响 | Schema On 让 GLM 的 JSON 解析失败率从 100% 降到 0% |
| DeepSeek 与 Qwen 在 Schema On 下的表现 | DeepSeek + Schema On 被推荐为生产级首选配置 |
| 强制结构化对生成稳定性的提升幅度 | Schema On 使生成耗时减少 15-25% |
| — | 强制 JSON 格式提升了结构严谨度与逻辑深度 |

→ 信息密度从"概念"升级为"可验证的事实+数字+推荐用法"，且每条都能找到对应 chunk。

---

## 6. 已知限制 / 后续阶段

| 限制 | 处理 |
|---|---|
| coverage 信号粗糙 | Step 6 评估时调阈值；或加复合判据（top-3 平均、是否含数字） |
| LLM 偶尔会保留原 bullets 的措辞而不引 evidence（"可用"但"不可审计"） | 评估指标里加"evidence 覆盖率" = 引了证据的 bullet 数 / 总 bullet 数 |
| 没有 Web Search 兜底（语料没有的内容只能靠 LLM 通用知识） | Step 5 可选模块：DeepResearch lite，coverage<low_threshold 时调一次 Tavily/Bing |
| 多页串行调用 LLM，5 页 30s | 后续可加 asyncio.gather 并发，但要注意 provider 的 QPS 限制 |
| evidence 文本只截到 400 字，长表格/长定义可能被截断 | 前端展示时可加"展开原文"按钮（需把 char_start/char_end 送到前端，按需回查源文件） |

---

## 7. 常见问题

**Q：为什么 Ch0.P1 high confidence 但 used_sources=[]？**
A：LLM 看了片段后可能判断"片段太宽泛，不适合做单点引用"，于是没引。这不是 bug——
我们的 prompt 没有强制必须引证据。如果作业评分需要"100% 引用率"，可以在 prompt 里
加一条："至少引用 2 条片段"。

**Q：能否换一个 LLM 做 enrichment？**
A：可以。`--provider deepseek`/`glm`。enrichment 比 query 改写更吃指令遵循 +
长上下文管理；qwen-plus / deepseek-chat 都验证可行；GLM-4 偶尔会偏离严格 JSON 输出，
与你们 §3 实验报告中的观察一致。

**Q：能否单独跑某一页（debug 用）？**
A：当前 CLI 一次跑全大纲。如果想 debug 单页，可以在 Python 里直接调用：
```python
from rag.enricher import enrich_page, snippets_from_research_chunks
r = enrich_page(
    overall_topic="...", chapter_title="...", page_title="...",
    original_bullets=[...], original_notes="...",
    snippets=snippets_from_research_chunks(research_entry["final_chunks"]),
    coverage=0.72,
    client=client, model=model,
)
print(r.bullets, r.evidences)
```

**Q：enriched 输出能否直接给现有前端渲染？**
A：可以。`outline` 节点结构与现有 `/api/outline` 一致，只是页内多了可选 `evidences`
数组。前端不识别该字段时会忽略；要展示溯源就接一个"参考资料"折叠面板。
