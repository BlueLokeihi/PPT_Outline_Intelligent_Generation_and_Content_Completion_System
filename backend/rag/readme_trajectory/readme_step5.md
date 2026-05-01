# RAG 模块 · Step 5：HTTP 接口 + 前端集成

把 [Step 1-4](readme_step4.md) 跑通的"建索引 → 研究 → 浓缩"流水线接到前端，让普通
用户在浏览器里勾一下"RAG 增强"+ 选一个知识库，就能拿到带溯源的大纲。

---

## 1. 设计目标

| 目标 | 怎么做 |
|---|---|
| 旧的"无 RAG"流程零回归 | RAG 字段（`useRag`、`corpusId`）默认关闭；schema 上 `evidences` 是可选 |
| 接入点最小化 | 不新建生成端点，扩展原有 `POST /api/outline` |
| 索引管理保持 CLI 化 | 暂不在 UI 里上传/构建索引（CLI 已稳定）；UI 只负责"用"已有索引 |
| 进度可观测 | 每页 `enrichment` 状态、`coverage`、`confidence`、`used_source_ids` 在响应 `rag.page_meta` 里全暴露 |
| 前端展示溯源 | 每页底部加可折叠的"📚 N 条来源"小面板，列出每条 evidence 的来源 + 摘录 + score |

---

## 2. 接口契约

### 2.1 `GET /api/rag/corpora`（新增）

列出已建好的索引（来自 `backend/rag/indexes/<id>/manifest.json`）。

```json
{
  "ok": true,
  "corpora": [
    {
      "id": "demo",
      "size": 49,
      "dim": 1024,
      "embedding_model": "text-embedding-v3",
      "built_at": "2026-04-30 14:23:52",
      "has_bm25": true
    }
  ]
}
```

### 2.2 `POST /api/outline`（扩展）

**请求新增字段**（全部可选，默认关闭）：

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `useRag` | bool | false | 总开关；为 false 时走原有流程 |
| `corpusId` | string | "" | 知识库 id（必须在 `/api/rag/corpora` 返回的列表里） |
| `ragMode` | `"vector"\|"bm25"\|"hybrid"` | `"hybrid"` | 检索模式 |
| `ragRewriteThreshold` | float | 0.45 | 多轮改写触发阈值 |
| `ragMaxRounds` | int | 2 | 最大检索轮数 |
| `ragMaxSnippets` | int | 8 | 喂给 enrichment LLM 的最大片段数 |
| `ragSkipLowConfidence` | bool | false | 低置信度页跳过 LLM 调用，保留原 bullets |
| `ragLowThreshold` | float | 0.4 | skip 触发阈值 |

**响应新增字段**：

```jsonc
{
  "ok": true,
  "outline": { /* 与旧版同 schema，但每页可能多出 evidences 数组 */ },
  "elapsedS": 148.093,        // 包含 outline + RAG 总耗时
  "rag": {
    "used": true,
    "corpus": "demo",
    "mode": "hybrid",
    "embedding_model": "text-embedding-v3",
    "index_size": 49,
    "rewrite_threshold": 0.45,
    "max_rounds": 2,
    "page_meta": [
      {
        "chapter_idx": 0, "page_idx": 0,
        "page_title": "...",
        "enrichment": "ok",
        "coverage": 0.6966, "confidence": "high",
        "used_source_ids": [1,3,4,5,6],
        "n_evidences": 5
      }
    ],
    "elapsed_s": 119.802
  }
}
```

`rag.elapsed_s` 是 RAG 阶段独占耗时；`elapsedS` 是 outline 生成 + RAG 总耗时。

---

## 3. 文件改动

```
backend/
└── http_server.py          (改动) 加 /api/rag/corpora；POST /api/outline 接 _run_rag_pipeline

frontend/src/
├── types.ts                (改动) Evidence/RagMode/RagPageMeta/RagResultMeta/RagCorpusInfo + 扩展 RunOutline*
├── services/bridge.ts      (改动) 加 getCorpora()
├── stores/chat.ts          (改动) useRag/corpusId/ragMode 三个 ref + payload 传递
├── App.vue                 (改动) 顶部加 RAG 切换 + 知识库下拉 + 模式下拉，挂载时拉取 /api/rag/corpora
├── components/OutlinePanel.vue (改动) 标题栏加"🔗 N 条引证"徽章；每页底部加可折叠的"📚 N 条来源"
└── styles.css              (改动) toolbar 上 .rag-toggle / .rag-corpus / .rag-mode 样式
```

后端 RAG 流水线本身（research → enrich）一行没改，只在 [http_server.py](../http_server.py)
里新增了一个 `_run_rag_pipeline()` 函数，接到原有 `run_outline()` 末尾。

---

## 4. 前端 UI 行为

### 4.1 启动与挂载

`onMounted` 时并发拉三个：`/api/ping`、`/api/runtime-info`、`/api/rag/corpora`。
- 没有任何已建索引时：RAG 切换会显示但 disabled；hover 提示"尚无"
- 有索引时：自动选第一个 corpus 作为默认值（用户可改）

### 4.2 顶部 toolbar（已加 3 个新控件）

```
[Provider] [Strategy] [Schema]   ☐ RAG增强   [知识库 ▾]   [模式 ▾]
```

- "RAG增强"是高亮的青色徽章式 checkbox（开了之后视觉上很醒目）
- 知识库 / 模式两个下拉只在 RAG 开启时出现
- 模式选项：hybrid（默认）/ vector / bm25

### 4.3 OutlinePanel 大纲预览面板

- 标题栏：原有"X 章 · Y 页"右边加 `🔗 N 条引证`（仅当响应里 evidences 总数 > 0 才出现）
- 每页底部：原有 bullets 下面，如果 `page.evidences` 非空，加一个折叠面板：
  ```
  📚 N 条来源 ›
  ```
  点开后是顺序编号的 evidence 列表，每条显示：
  - 来源文件名（粗体）
  - `#chunkXX` + `score 0.123`（小字 monospace）
  - 200 字以内的摘录原文（淡灰背景，左侧蓝色竖条）

---

## 5. 端到端验收

### 5.1 后端冒烟（CLI）

```powershell
# 1. 列索引
curl http://127.0.0.1:8000/api/rag/corpora
# → {"ok":true,"corpora":[{"id":"demo","size":49,"dim":1024,...}]}

# 2. 跑带 RAG 的 outline（payload 见 backend/rag/test_outlines/_smoke_request.json）
curl -X POST http://127.0.0.1:8000/api/outline \
    -H "Content-Type: application/json" \
    --data-binary @backend/rag/test_outlines/_smoke_request.json
```

实测结果（4 章 7 页大纲，主题：Schema/Few-Shot/CoT-Silent 对比汇报）：

| 阶段 | 耗时 |
|---|---|
| 大纲生成（baseline + Schema On）| ~28s |
| RAG 流水线（7 页 × research+enrich）| ~120s |
| **总计** | **~148s** |

7 页全部 `enrichment="ok"`，coverage 区间 0.635-0.698，每页 1-5 条 evidences。
样例（Ch0.P0 "汇报目标与核心问题"）：
- "Schema约束使生成时间降低15–25%（所有策略一致）"
- "Few-Shot+Schema On生成最快（43.4s），且格式稳定性最优"
- "CoT-Silent+Schema On准确率最高（55.2%），但内容深度较薄"

→ 直接从 [PPT_Outline_Generation_Strategy_Report.pdf](corpus/demo/) 抓出原始数字。

### 5.2 前端冒烟（浏览器）

操作步骤：

```powershell
# 终端 1：启动后端
cd backend
python http_server.py

# 终端 2：启动前端
cd frontend
npm run dev
# → http://localhost:5173/
```

在浏览器里：
1. 顶部应看到"RAG增强"切换；勾上后右侧出现"知识库"下拉，已选 `demo · 49块`
2. 在主面板里输入主题（例如"对比 Schema On/Off 与 Few-Shot 的实验结论"）→ 提交
3. 等待大约 2-3 分钟（RAG 全流水线耗时大头）
4. 大纲预览面板顶部出现"🔗 N 条引证"徽章
5. 展开任意一页，底部点 "📚 X 条来源 ›" 可看到具体引用片段

---

## 6. 已知限制 / 后续阶段

| 限制 | 处理方向 |
|---|---|
| RAG 全流水线 1-3 分钟，前端只有计时器没有阶段进度 | 后续可改 SSE / WebSocket 推送阶段事件（research/enrich/done） |
| 不能在 UI 里上传文件并构建索引 | Step 6+：加 `POST /api/rag/index`（multipart upload）；当前 CLI 已经够 demo |
| 知识库列表不会自动刷新（rebuild 后需要重启或刷新页面） | 后续可加一个"刷新"按钮调用 `getCorpora()` |
| OutlinePanel 没渲染 page-level confidence / coverage | 视需要在每页标题旁加一个 `high/medium/low` 小标签（`message.metadata.rag.page_meta` 已有数据） |
| `useRag` 但 `corpusId` 为空时，前端逻辑直接传 `useRag=false`（store 里加了保护），后端也有兜底 | 已 OK，但缺少 UI 提示——用户勾了切换却没建过索引时不知道为啥没生效 |

---

## 7. 常见问题

**Q：浏览器打开 5173 后顶部"RAG增强"切换是灰的？**
A：说明 `/api/rag/corpora` 返回空数组。先在 `backend/` 下跑 `python -m rag.index --corpus demo` 建出至少一个索引，然后刷新前端。

**Q：勾了 RAG 但生成的大纲没有任何 evidences？**
A：可能原因：
1. 知识库与主题不相关（所有页 coverage 都低）→ 看响应 `rag.page_meta` 各页 confidence 是不是都是 medium/low
2. 后端 `_run_rag_pipeline` 抛了异常 → 看 `rag.error` 字段
3. 用了 `--skip-low-confidence` 等参数（当前 UI 暂未暴露这些选项）

**Q：能否在生成完成后单独"补"RAG 而不是重跑整个 outline？**
A：当前没有。要做的话需要新增一个 `POST /api/outline/enrich` 端点，吃已有 outline JSON 做 enrichment。CLI 那边 `rag.enrich` 模块已经独立可用。

**Q：CORS 报错？**
A：`http_server.py` 里 `CORSMiddleware` 已开放 `localhost:5173`/`127.0.0.1:5173`。如果前端 dev server 改了端口要记得同步加进 `allow_origin_regex`。
