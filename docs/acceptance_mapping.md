# WBS/RBS Acceptance Mapping

This document maps the current implementation to the course project management artifacts.

| Capability | WBS ID | RBS ID | Evidence in system |
|---|---|---|---|
| Requirement-guided interaction | WBS 3.1-3.4 | RBS Req1 | Requirement form, multi-turn chat, PDF context |
| Outline generation engine | WBS 4.1-4.5 | RBS Req2 | Prompt strategies, Schema mode, multi-model provider selection |
| RAG information completion | WBS 5.1-5.8 | RBS Req3 | Corpus index, query rewriting, hybrid retrieval, evidence and confidence |
| Content integration and output | WBS 6.1-6.4 | RBS Req4 | Edited outline, Markdown/HTML/JSON/PPTX export |
| Quality evaluation | WBS 7.1-7.3 | RBS Req5 | Backend quality metrics, frontend score display, acceptance report |
| Integration, packaging, delivery | WBS 7.4-8.6 | RBS Req6 | FastAPI service, Vite frontend, Docker Compose, user-facing exports |

## Acceptance Scenarios

1. Generate a normal outline without RAG and verify quality metrics appear.
2. Generate with RAG enabled and verify evidence, confidence, and conflict flags appear.
3. Edit the outline manually, save a version, and restore it.
4. Export the final outline as Markdown, HTML, JSON report, and PPTX.
5. Build and run the system with Docker Compose using `backend/.env`.
