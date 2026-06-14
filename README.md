# PPT-Outline-Intelligent-Generation-and-Content-Completion-System-
A PPT Outline Intelligent Generation and Content Completion System for the Software Engineering Management and Economics course.

## Local Run (HTTP Mode)

1. Start backend service:

```powershell
cd backend
pip install -r requirements.txt
copy .env.example .env
# fill QWEN_API_KEY / DEEPSEEK_API_KEY / GLM_API_KEY in .env
python http_server.py
```

2. Start frontend:

```powershell
cd frontend
npm install
npm run dev
```

## Implemented Capabilities

- Structured PPT outline generation with Qwen / GLM / DeepSeek.
- Prompt strategy selection: `baseline`, `few_shot`, `cot_silent`.
- JSON Schema constrained output and backend quality metrics.
- Multi-session frontend workflow with requirement form, PDF text extraction, and multi-turn outline refinement.
- Editable outline panel: edit title/chapter/page/bullets, add/remove/move outline nodes.
- RAG enhancement: indexed local corpus, vector/BM25/hybrid retrieval, query rewriting, page-level evidence, confidence metadata, and conflict flags.
- Version management: generated/edited/restored outline versions can be saved and restored.
- Export: Markdown, HTML, JSON acceptance report, and editable PPTX.

## Useful APIs

- `POST /api/outline`
- `GET /api/rag/corpora`
- `POST /api/rag/corpora/build`
- `POST /api/outline/save`
- `POST /api/outline/versions`
- `GET /api/outline/versions?conversationId=<id>`
- `GET /api/outline/versions/{versionId}`
- `POST /api/outline/versions/{versionId}/restore`
- `POST /api/outline/export`
- `GET /api/monitoring/usage`
- `POST /api/monitoring/reset`

## Docker Run

Create `backend/.env` from `backend/.env.example`, fill API keys, then run:

```powershell
docker compose up --build
```

Frontend: `http://localhost:5173`
Backend: `http://localhost:8000`

Runtime data is mounted back to the host for RAG corpora/indexes/cache, outline output/version/export files, and API monitoring logs.
