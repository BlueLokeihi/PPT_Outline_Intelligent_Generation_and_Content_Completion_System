# 5.4 交付文档编写（王相）

## 任务信息

- WBS：5.4 交付文档编写
- 负责人：王相
- 周期：Week 11
- 工时：4h
- 交付位置：`backend/outline`
- 关联范围：大纲生成模块、后端 API、Docker 部署、实验输出

## 交付范围

本交付文档面向课程验收和项目移交，说明 PPT 大纲生成与内容补全系统的可运行入口、核心功能、验收方式和交付物清单。王相负责补充与后端大纲生成、效率实验和容器化部署相关的交付说明。

## 系统功能概览

当前系统已经实现以下能力：

| 功能 | 说明 | 主要文件 |
|---|---|---|
| 结构化 PPT 大纲生成 | 输出标题、章节、页面、要点和备注 | `backend/outline/generator.py` |
| Prompt 策略选择 | 支持 baseline、few_shot、cot_silent | `backend/outline/prompt_strategies.py` |
| 多模型调用 | 支持 Qwen、GLM、DeepSeek | `backend/llm/client.py`、`backend/config/models.json` |
| Schema 约束 | 控制输出结构，提升可解析性 | `backend/outline/schema.py` |
| 质量评估 | 计算页数、章节数、要点粒度、质量分 | `backend/outline/evaluation.py` |
| 批量对比实验 | 支持多模型、多策略、多次运行 | `backend/outline/cli.py` |
| HTTP 服务 | 提供前后端联调 API | `backend/http_server.py` |
| RAG 内容补全 | 支持语料构建、检索、证据与置信度 | `backend/rag` |
| 导出能力 | 支持 Markdown、HTML、JSON、PPTX | `POST /api/outline/export` |
| 容器化运行 | 支持 Docker Compose 一键启动 | `docker-compose.yml` |

## 本地运行说明

后端运行：

```powershell
cd backend
pip install -r requirements.txt
copy .env.example .env
python http_server.py
```

前端运行：

```powershell
cd frontend
npm install
npm run dev
```

默认访问地址：

| 服务 | 地址 |
|---|---|
| 前端 | `http://localhost:5173` |
| 后端 | `http://localhost:8000` |

## Docker 运行说明

```powershell
copy backend\.env.example backend\.env
docker compose up --build
```

启动后访问：

- 前端页面：`http://localhost:5173`
- 后端服务：`http://localhost:8000`
- 运行信息：`http://localhost:8000/api/runtime-info`

## 核心 API 清单

| API | 方法 | 用途 |
|---|---|---|
| `/api/ping` | POST | 服务连通性检查 |
| `/api/runtime-info` | GET | 查看运行环境和配置状态 |
| `/api/questionnaire` | POST | 生成前置需求问卷 |
| `/api/outline` | POST | 生成 PPT 大纲 |
| `/api/outline/save` | POST | 保存大纲 |
| `/api/outline/versions` | GET/POST | 查询或创建版本 |
| `/api/outline/versions/{version_id}` | GET | 获取指定版本 |
| `/api/outline/versions/{version_id}/restore` | POST | 恢复指定版本 |
| `/api/outline/export` | POST | 导出 Markdown、HTML、JSON 或 PPTX |
| `/api/rag/corpora` | GET/POST | 查询或构建语料库 |
| `/api/rag/upload` | POST | 上传 RAG 语料 |
| `/api/search/web` | POST | 网络搜索补充资料 |

## 验收流程

建议按以下步骤完成验收：

1. 启动系统，确认前端和后端均可访问。
2. 在前端填写 PPT 主题、受众、页数范围、风格等需求。
3. 选择模型、Prompt 策略和 Schema 模式，生成结构化大纲。
4. 检查页面是否展示质量评估指标。
5. 启用 RAG，选择或构建语料库，确认生成结果包含证据、置信度和冲突提示。
6. 对生成大纲进行手动编辑，保存版本并恢复历史版本。
7. 导出 Markdown、HTML、JSON 验收报告和 PPTX 文件。
8. 使用 `python -m outline.cli --mode compare` 运行效率对比实验。
9. 使用 `docker compose up --build` 验证容器化交付。

## 交付物清单

| 交付物 | 路径 | 说明 |
|---|---|---|
| 效率对比实验记录 | `backend/outline/5_2_efficiency_comparison_experiment_wangxiang.md` | 对应王相 W10/W11 5.2 工作 |
| 容器化打包记录 | `backend/outline/5_3_container_packaging_wangxiang.md` | 对应王相 W10 5.3 工作 |
| 交付文档 | `backend/outline/5_4_delivery_documentation_wangxiang.md` | 对应王相 W11 5.4 工作 |
| 大纲模块说明 | `backend/outline/README.md` | 模块运行入口 |
| 项目验收映射 | `docs/acceptance_mapping.md` | WBS/RBS 与系统能力对应 |
| Docker 编排文件 | `docker-compose.yml` | 前后端一键部署 |
| 实验输出目录 | `backend/outline/output` | 对比实验 JSON 结果 |

## 验收结论

王相负责的 5.2、5.3、5.4 任务已形成可检查的 Markdown 交付材料。效率对比实验说明了模型、策略、Schema 约束的对比方法；容器化打包说明了前后端镜像和 Compose 部署方式；交付文档汇总了系统运行、API、验收流程和交付物清单，可支撑课程项目的测试验收与交付阶段。
