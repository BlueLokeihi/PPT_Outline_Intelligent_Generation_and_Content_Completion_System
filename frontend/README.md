# Frontend 

本目录已实现：

- Vue3 + Vite + TypeScript + Pinia 前端骨架
- 多轮对话（会话列表、消息历史、继续提修改意见）
- PDF 文件接收与前端文本提取（pdfjs）
- 通过 HTTP 接口调用本地 Python 后端服务

## 目录说明

- `src/`：Vue 前端代码

说明：`python_host/` 为旧桌面桥接方案，当前默认不再使用。

## 运行前准备

1. 安装 Node.js（建议 18+）
2. 安装 Python 3.10+
3. 在 `backend` 下安装后端依赖

```powershell
cd backend
pip install -r requirements.txt
```

4. 配置模型 API Key（参考 `backend/README.md`）

## 启动本地后端 HTTP 服务

```powershell
cd backend
python http_server.py
```

默认监听 `http://127.0.0.1:8000`。

## 构建前端

```powershell
cd frontend
npm install
npm run dev
```

开发模式下，前端默认通过 `/api` 代理访问后端本地服务。

```powershell
cd frontend
npm run build
npm run preview
```

如需显式指定后端地址，可配置环境变量：`VITE_API_BASE_URL`（例如 `http://127.0.0.1:8000/api`）。

## 已实现 HTTP 接口

- `POST /api/ping`：服务可用性检测
- `GET /api/runtime-info`：读取 provider 列表与策略列表
- `POST /api/outline`：触发后端单次生成并返回结构化结果

`POST /api/outline` 请求关键字段：

- `messages`：多轮对话消息数组（user/assistant）
- `pdfText`：PDF提取文本
- `provider`：`qwen | glm | deepseek`
- `strategy`：`baseline | few_shot | cot_silent`
- `schema`：`on | off`
- `minSlides` / `maxSlides`：页数范围

## 验收建议

1. 新建会话并发送需求，观察是否返回初版大纲
2. 上传 PDF，确认文本进入上下文
3. 在同一会话追加修改意见，验证多轮生成
4. 切换会话，确认历史互不污染