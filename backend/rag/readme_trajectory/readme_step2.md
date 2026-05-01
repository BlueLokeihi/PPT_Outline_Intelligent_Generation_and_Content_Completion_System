# RAG 模块 · Step 2：BM25 + RRF 混合检索

本阶段在 [Step 1](readme_step1.md) 的纯向量检索基础上，加入**词法检索 (BM25)** 与
**RRF (Reciprocal Rank Fusion)** 融合，形成一个统一的可切换检索器。

---

## 1. 为什么要做混合检索

向量检索擅长"语义近似"，但有几类 query 它表现差：

| 场景 | 向量 | BM25 |
|---|---|---|
| "few-shot 提示策略效果" | ✅ 跨语言语义匹配 | 一般 |
| "55.245"（具体数字） | ❌ 完全打偏 | ✅ 直接命中 |
| 专有名词、API 名、错误码 | 易飘 | ✅ 精确 |

实际验证（同一索引、同一 query `55.245`）：

```
Vector mode:  Top1 是关于章节结构的段落，Top3 都不含 55.245
BM25   mode:  Top1 命中含 "55.245" 的实验数据行
Hybrid mode:  含数字段被 RRF 提到 Top1（V#11 + B#2 → 融合后第1）
```

混合检索通过 RRF 让两路投票，**任一路把文档排得高，融合后都会受益**，而无需把
余弦相似度和 BM25 分数硬归一化到同一量纲（这是 RRF 相对线性加权的核心优势）。

---

## 2. 新增 / 改动文件

```
backend/rag/
├── bm25.py            (新增) BM25 索引：jieba 分词 + rank_bm25
├── retriever.py       (新增) 统一检索器：vector / bm25 / hybrid 三模式
├── index.py           (改动) 建索引时同时产出 tokens.jsonl
└── search.py          (改动) 加 --mode / --recall-k / --rrf-k 参数
```

依赖增量（[backend/requirements.txt](../requirements.txt)）：
- `rank-bm25>=0.2.2`（纯 Python，约 10 KB）
- `jieba>=0.42.1`（中文分词，纯 Python，含 dict 约 19 MB）

每个 corpus 的 `indexes/<corpusId>/` 目录下多出一个 `tokens.jsonl`，每行是该 chunk 的
分词结果（list[str]），重启时从 JSONL 重建 `BM25Okapi`，加载快、可读、可 diff。

---

## 3. 用法

### 3.1 重建索引（旧索引没有 BM25）

```powershell
cd backend
python -m rag.index --corpus demo
```

输出多了一步：
```
[5/5] 构建 BM25 索引（jieba 分词）
      已写入: ...indexes/demo/tokens.jsonl
```

参数：
- `--no-bm25`：跳过 BM25 构建，仅向量（debug 用）

### 3.2 检索三模式

```powershell
# 默认 hybrid
python -m rag.search --corpus demo --query "Schema On Few-Shot" -k 5

# 仅向量
python -m rag.search --corpus demo --query "..." --mode vector

# 仅 BM25
python -m rag.search --corpus demo --query "..." --mode bm25
```

hybrid 调参：
- `--recall-k 20`：每路（向量、BM25）各召多少候选送入 RRF（默认 20，再大收益递减）
- `--rrf-k 60`：RRF 平滑常数，**越小越激进、越大越温和**。60 是论文里常用值

### 3.3 输出阅读

每条命中除了最终 `score`，还会显示两路命中信息：

```
[1] score=0.0302  V#11(0.407) B#2(4.490)  source=...  chunk=5
    4.09 5 CoT Silent On 55.245 7 13 4.62 (highest) ...
```

- `score=0.0302`：RRF 分（hybrid 模式才有）
- `V#11(0.407)`：在向量召回中排第 11，余弦相似度 0.407
- `B#2(4.490)`：在 BM25 召回中排第 2，BM25 原始分 4.490
- 没有 `V#…` 表示该文档**没进**向量召回前 `recall_k`，只靠 BM25 撑起来；反之亦然

---

## 4. 设计要点

### 4.1 中文分词（[bm25.py](bm25.py) `tokenize`）

- 中文：`jieba.cut_for_search`（搜索引擎模式，召回比精确模式更全）
- 英文/数字：先用正则把英数串单独抽出，避免 jieba 把 `text-embedding-v3` 切碎
- 中文段落里的英数子串单独按 `.`、`-`、`_` 切分（如 "DeepSeek-V3" → `deepseek` + `v3`）
- 全部小写化

不引入停用词表（语料是技术文档，停用词收益小且增加配置复杂度）。

### 4.2 BM25 持久化策略（[bm25.py](bm25.py)）

- **不**直接 pickle `BM25Okapi` 对象（可移植性差、跨版本易坏）
- 只保存分词结果 `tokens.jsonl`，加载时几毫秒重建 `BM25Okapi`
- 单文件、可读、可 diff，方便 debug 看分词质量

### 4.3 RRF 融合（[retriever.py](retriever.py) `search`）

公式：
```
rrf_score(d) = Σ_paths  1 / (rrf_k + rank_in_path(d))
```

实现要点：
- 两路各召 `recall_k=20` 个候选（不是 `k`），扩大候选池
- 取并集；某路缺席的项就只贡献一路 1/(rrf_k+rank)
- 排序后取 `top-k`

为什么 RRF 优于线性加权 `α·cosine + (1-α)·bm25`：
- 余弦在 [0,1]，BM25 在 [0, +∞)，**量纲不可比**，归一化既人为又不稳定
- RRF 只看"排名"，对绝对分数不敏感
- 实测：调 `α` 调到怀疑人生 vs. RRF 几乎参数无关地工作

### 4.4 检索器架构

`HybridRetriever` 共享同一个 corpus 目录的两个索引：
- 向量路：`store.VectorStore`（FAISS）
- 词法路：`bm25.Bm25Index`
- 元数据 `meta.jsonl`：两路共用，`doc_id` 在两个索引里都对齐到同一行

返回 `RetrievedChunk`：携带每路的 rank/score 信息，方便上层做溯源、归因、调参。

---

## 5. 验收记录

测试索引：49 chunks（来自 PPT_Outline_Generation_Strategy_Report.pdf）

| Query | Vector Top1 | BM25 Top1 | Hybrid Top1 | 备注 |
|---|---|---|---|---|
| `schema 校验失败` | chunk 25, 0.673 | — | chunk 25 | 语义类，向量主导 |
| `few-shot 提示策略效果` | chunk 7, 0.705 | — | chunk 7 | 跨语言语义匹配 |
| `Schema On Few-Shot DeepSeek` | chunk 47, 0.689 | chunk 47, 6.473 | chunk 47 | 两路共识 |
| `55.245` | ❌ chunk 38（无 55.245） | ✅ chunk 5 | ✅ chunk 5 | **关键案例**：vector 完全打偏，hybrid 通过 BM25 救回 |

---

## 6. 已知限制 / 后续阶段

| 限制 | 后续阶段 |
|---|---|
| 一次只能问一个 query；page-level 还要靠人工写 query | Step 3：基于大纲节点的查询改写（LLM 生成 2-3 条 query） |
| 检索片段还没"压"成 PPT bullets | Step 4：内容浓缩 + 大纲补全（enricher） |
| `rrf_k=60` 是经验值，没在你们语料上调过 | 评估阶段（Step 6）可以拉一组标注做网格搜索 |
| 长文档单 chunk 可能跨越多个主题；BM25 召回的"上下文行"和向量召回的"语义行"会竞争 | 可考虑 Step 4 浓缩时主动把同一来源的相邻 chunks 合并喂给 LLM |
| 中文分词没有自定义词典 | 如果发现专业术语被切碎（如 `RAG`、`大纲生成器`），后续可加 `jieba.load_userdict` |

---

## 7. 常见问题

**Q：旧的索引报 `缺少 BM25 索引: ...tokens.jsonl`？**
A：旧索引没有 BM25。重新跑 `python -m rag.index --corpus <id>`。embedding 已缓存，不会重花钱。

**Q：换了文档但 BM25 结果没变？**
A：BM25 与向量索引共用 `meta.jsonl`，重建会一起更新。如果你只想刷新 BM25（比如改了切块参数），目前只能整体 rebuild。

**Q：hybrid 模式比 vector 慢吗？**
A：BM25 是 numpy 向量化打分，对几万 chunks 量级毫秒级。整体延迟主要来自 query 的 embedding 调用（约 100-300ms），**hybrid 与 vector 几乎等延迟**。

**Q：能不能让某些 query 只走 BM25（省 embedding 钱）？**
A：可以。`--mode bm25` 时不会调用 embedding API。Step 4 的 enricher 会自动判断（短查询 / 含数字 / 含专有名词 → 偏 BM25 路）。
