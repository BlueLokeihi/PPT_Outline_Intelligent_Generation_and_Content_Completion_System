# 用户使用指南
## 准备你的知识库
### 1. 给知识库起个名字（corpus id）

corpus id 就是个英文短名，比如：

- 如果你要做"机器学习入门"的 PPT → corpus id 可以叫 `ml_intro`
- 如果你要做"产品 2026 Q1 复盘" → corpus id 可以叫 `q1_review`
- 演示用的就叫 `demo`

corpus id 只能用英文字母、数字、下划线。

### 2. 把资料放进对应文件夹

在 `backend/rag/corpus/<corpus id>/` 下放你的资料文件。**支持的格式**：

| 后缀 | 说明 |
|---|---|
| `.pdf` | PDF 文档（自动抽文字，扫描件 OCR 不支持） |
| `.md` | Markdown 笔记 |
| `.txt` | 纯文本 |

可以放任意多个文件，**子目录也会被递归扫描**。例如：

```
backend/rag/corpus/ml_intro/
├── 教材摘录.pdf
├── 课件笔记.md
└── 经典论文/
    ├── lecun_1998.pdf
    └── vaswani_2017.pdf
```

> ⚠️ **不要放敏感/版权受限的资料**，因为构建索引时会把每段文本送到 qwen API 做 embedding。

### 3. 构建索引

```powershell
cd backend
python -m rag.index --corpus ml_intro
```

替换 `ml_intro` 为你自己的 corpus id。命令会：
1. 扫描 `corpus/ml_intro/` 下所有文件
2. 切成大约 500 字一段
3. 调通义 embedding API 把每段变成向量（**会消耗 API 配额**，一篇普通论文约 100-300 段）
4. 写入 `backend/rag/indexes/ml_intro/`

正常输出（中文进度提示）：
```
[1/5] 扫描并切块: corpus/ml_intro/
      共 152 个 chunk（来自 3 个文件）
[2/5] 加载 embedding 配置: provider=qwen
      model=text-embedding-v3, dim=1024, batch=16
[3/5] 调用 embedding API
      embedding batch 1/10 (size=16)
      ...
[4/5] 写入 FAISS 索引
[5/5] 构建 BM25 索引（jieba 分词）
Done.
```

> 💡 **缓存机制**：每段文字的 embedding 结果会缓存到 `backend/rag/cache/`。如果你只是新增了几个文件再 rebuild，已经处理过的段落会跳过 API 调用，**不会重复花钱**。

### 4.（可选）确认建好了

```powershell
python -m rag.search --corpus ml_intro --query "你的关键词" -k 3
```

会返回 3 段最相关的内容。看下结果是不是符合预期；如果完全打偏，可能你的资料和 query 主题不匹配。

> 想了解更多检索模式（vector / bm25 / hybrid），看 [backend/rag/readme_trajectory/readme_step2.md](backend/rag/readme_trajectory/readme_step2.md)。

## 在浏览器里使用

### 1. 顶部工具栏说明

打开页面后，顶部有一排控件：

```
[Provider ▾]  [Strategy ▾]  [Schema ▾]   ☐ RAG增强   [知识库 ▾]   [模式 ▾]
```

| 控件 | 说明 | 推荐值 |
|---|---|---|
| **RAG增强** | 是否接入知识库 | 想要有数据/出处就勾上 |
| **知识库** | 选择哪个 corpus（仅 RAG 开启时显示） | 你刚建的那个 |
| **模式** | 检索方式（仅 RAG 开启时显示） | `hybrid`（混合），`vector`（向量检索），`bm25`（词法检索） |

> 💡 如果 "RAG增强" 切换是灰色的、点不动，说明你还没建过任何索引。回到 §3。

- **不开 RAG**：约 20-40 秒
- **开 RAG**：约 1-3 分钟（每页都要做"改写 query → 检索 → 浓缩"，所以慢一些）

页面上会有一个秒数计时器，正常运行。

### 2. 看结果

生成完成后，**右侧"大纲预览"面板**会显示完整大纲：

```
[大纲标题徽章]  3 章 · 10 页    🔗 28 条引证   ← RAG 才会出现
─────────────────────────────────────────
▾ 第1章 章节标题                10p  ›
   • 页标题
     - 要点 1
     - 要点 2
     - 要点 3
     📚 5 条来源 ›                ← 点开看具体引用
```

**点击"📚 N 条来源"**可以展开该页所引用的资料片段，每条会显示：
- 来源文件名（哪个 PDF / md）
- chunk 编号（方便你在原文件里翻找）
- score（相关度分数）
- 200 字以内的原文摘录

### 3. 多轮迭代

提交完大纲后，下方会出现一个聊天输入框。你可以用自然语言继续调整：

- "把第 2 章拆成两章"
- "第 5 页加一个具体案例"
- "总页数压到 8 页"

每条修改请求都会**重新跑一遍**生成 + RAG 流水线（保留多轮上下文），输出新的大纲版本。

---

## 怎么解读"📚 N 条来源"

每条来源对应一段你知识库里的原文。看到输出 bullets 里的关键数字/概念时，可以：

1. **核对一下原文**：点开来源面板，看 score 最高的那条摘录，确认数字没被 LLM 写错
2. **回查源文件**：照着 `来源.pdf #chunk34` 去原 PDF 里搜对应段落（chunk 编号是顺序的，前面的 chunk 在文档前部）
3. **如果某页"📚 0 条来源"**：说明这一页 LLM 没有从你的资料里找到合适证据。可能原因：
   - 这一页主题确实不在你的资料范围内（系统会保留 LLM 通用知识写的内容，**不会乱编引用**）
   - 你的资料表述与 LLM 改写出的 query 词汇相差太远（可以试试切到 `bm25` 或 `vector` 模式重新跑）

---

## 常见问题

### Q：勾"RAG增强"切换不动（灰色）？

你还没有任何已建好的索引。建立一个，然后**刷新浏览器页面**。

### Q：建索引时报"未找到 qwen 的 API key"？

`backend/.env` 没配 `QWEN_API_KEY`，或者 conda 环境没激活就跑了命令。

### Q：建索引时网络超时 / 连接失败？

通义 API 有 QPS 限制和服务器抖动。等 1 分钟再 rerun 即可——已建好的部分会从缓存读取，不会重头来。

### Q：生成时一直转圈、超过 5 分钟没结果？

后端可能卡在某个调用上。**回到后端终端**，按 Ctrl+C 停止，重新运行 `python http_server.py`，然后在浏览器里重新提交。

### Q：能换一个大模型做 RAG 浓缩吗？

当前 UI 上 RAG 阶段会沿用顶部 Provider 设置。如果想分开（比如生成用 deepseek、RAG 用 qwen），需要改代码，详见 [backend/rag/readme_trajectory/readme_step5.md](backend/rag/readme_trajectory/readme_step5.md)。

### Q：知识库里加了新文件，需要重建吗？

需要，再跑一次 `python -m rag.index --corpus 你的corpusId`。已处理过的旧文件命中缓存，不会重花钱。

### Q：能否在 UI 里直接上传文件建索引？

当前不支持，需要在命令行操作。这是有意为之——避免普通用户无意中把私密文件扔进数据流。


---

## 想深入了解？

| 想了解 | 看哪个文件 |
|---|---|
| 整体设计与作业要求对应 | [backend/rag/readme_trajectory/readme_step1.md](backend/rag/readme_trajectory/readme_step1.md) |
| 检索是怎么工作的（向量 / BM25 / 混合） | [backend/rag/readme_trajectory/readme_step2.md](backend/rag/readme_trajectory/readme_step2.md) |
| query 怎么被改写、多轮检索逻辑 | [backend/rag/readme_trajectory/readme_step3.md](backend/rag/readme_trajectory/readme_step3.md) |
| 检索结果怎么被压成 bullets，evidence 怎么挂上 | [backend/rag/readme_trajectory/readme_step4.md](backend/rag/readme_trajectory/readme_step4.md) |
| HTTP 接口契约、前端集成方式 | [backend/rag/readme_trajectory/readme_step5.md](backend/rag/readme_trajectory/readme_step5.md) |

---

