# 5.3 容器化打包记录（王相）

## 任务信息

- WBS：5.3 容器化打包
- 负责人：王相
- 周期：Week 10
- 工时：6h
- 交付位置：`backend/outline`
- 关联文件：`backend/Dockerfile`、`frontend/Dockerfile`、`docker-compose.yml`

## 打包目标

本任务负责将 PPT 大纲生成系统打包为可复现的容器化部署形态，降低不同同学本地 Python、Node.js、依赖版本不一致带来的运行风险。容器化交付需覆盖后端 API 服务、前端页面服务、环境变量配置、数据目录挂载和端口暴露。

## 当前容器结构

| 服务 | 镜像构建文件 | 运行端口 | 主要职责 |
|---|---|---|---|
| backend | `backend/Dockerfile` | `8000:8000` | 启动 `http_server.py`，提供 outline、RAG、导出、版本管理等 API |
| frontend | `frontend/Dockerfile` | `5173:80` | 构建 Vue 前端并通过 Nginx 提供页面 |

## 后端镜像说明

后端镜像基于 `python:3.12-slim`：

1. 工作目录设置为 `/app/backend`。
2. 复制 `backend/requirements.txt` 并安装 Python 依赖。
3. 复制完整后端代码到容器。
4. 暴露 8000 端口。
5. 使用 `python http_server.py` 启动服务。

该方案将模型调用、结构化大纲生成、RAG 检索、文件导出和版本保存统一封装在同一个后端容器中。

## 前端镜像说明

前端镜像采用两阶段构建：

1. 使用 `node:20-alpine` 安装依赖并执行 `npm run build`。
2. 使用 `nginx:1.27-alpine` 托管构建后的静态文件。
3. 将 `frontend/nginx.conf` 写入 Nginx 配置。
4. 对外暴露容器内 80 端口，并由 Compose 映射为宿主机 5173 端口。

## Compose 编排说明

`docker-compose.yml` 同时定义 backend 和 frontend 两个服务：

| 配置项 | 说明 |
|---|---|
| `env_file: backend/.env` | 后端读取 Qwen、DeepSeek、GLM 等 API Key |
| `ports: 8000:8000` | 后端 API 对外暴露 |
| `ports: 5173:80` | 前端页面对外暴露 |
| `depends_on: backend` | 前端服务依赖后端服务先启动 |
| `./backend/rag/corpus` | 语料库目录持久化 |
| `./backend/rag/indexes` | RAG 索引目录持久化 |
| `./backend/outline/output` | 大纲生成实验结果持久化 |
| `./backend/outline/versions` | 大纲版本记录持久化 |
| `./backend/outline/exports` | 导出文件持久化 |

## 打包与运行步骤

首次运行前在 `backend/.env` 中配置模型 API Key：

```powershell
copy backend\.env.example backend\.env
```

填写后执行：

```powershell
docker compose up --build
```

运行成功后访问：

| 服务 | 地址 |
|---|---|
| 前端页面 | `http://localhost:5173` |
| 后端 API | `http://localhost:8000` |
| 后端运行信息 | `http://localhost:8000/api/runtime-info` |

## 验收检查项

| 检查项 | 验收标准 | 结果记录 |
|---|---|---|
| 后端镜像构建 | `backend` 服务可以完成依赖安装和代码复制 | 待执行 `docker compose up --build` 确认 |
| 前端镜像构建 | `frontend` 服务可以完成 `npm ci` 和 `npm run build` | 待执行 `docker compose up --build` 确认 |
| API 启动 | `http://localhost:8000/api/runtime-info` 可访问 | 待联调确认 |
| 页面启动 | `http://localhost:5173` 可访问 | 待联调确认 |
| 数据持久化 | output、versions、exports、RAG indexes 等目录映射到宿主机 | Compose 已配置 |
| 环境隔离 | 不依赖宿主机 Python/Node 运行时 | Dockerfile 已配置 |

## 交付结论

当前仓库已经具备前后端容器化打包能力。后端通过 Python 镜像运行 API 服务，前端通过 Node 构建并交由 Nginx 托管，Compose 文件负责端口、环境变量和数据目录挂载。该交付满足课程项目中“容器化打包”的基本验收要求。

## 风险与补充说明

- `backend/.env` 不应提交真实 API Key，只在部署机器本地配置。
- 大模型 API 依赖外部网络，容器启动成功不等于模型调用一定成功。
- 首次构建需要拉取基础镜像和安装依赖，耗时取决于网络环境。
- 如需离线演示，应提前构建镜像并缓存 Python、Node 依赖。

## 复查与补充记录（2026-06-14）

本次复查发现并补充了以下容器化交付细节：

1. 后端容器监听地址已由 `127.0.0.1` 调整为 `0.0.0.0`，确保容器内 FastAPI 服务可以通过宿主机端口映射访问。
2. `docker-compose.yml` 已补充挂载 `backend/logs`，用于持久化 API 使用监控统计文件 `api_usage_metrics.json`。
3. `docker-compose.yml` 已补充挂载 `backend/rag/cache`，避免 Embedding 缓存随容器重建丢失。
4. 新增 `.dockerignore`，排除 `.env`、`node_modules`、`dist`、RAG 语料/索引、输出文件、日志和缓存，降低镜像体积并避免把本地密钥和运行数据复制进镜像。
5. `.gitignore` 已补充 `backend/.env` 和 `backend/logs/`，防止后续误提交本地密钥和运行日志。

复查后，容器化打包不再只是基础启动配置，也覆盖了运行数据持久化、构建上下文控制和容器网络可访问性。
