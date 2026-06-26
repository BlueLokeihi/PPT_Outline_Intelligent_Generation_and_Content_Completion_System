# DeepSeek Acceptance Results (docker_deepseek_smoke)

- Generated at: 2026-06-26T13:11:19
- Summary: {'PASS': 6}
- Note: qwen/glm model rows are simulated with actual provider `deepseek`, because only DeepSeek API key is available.

| ID | Requirement | Test | Status | Duration(s) | Notes |
|---|---|---|---|---:|---|
| TC-IP-03 | Input Processing | Dynamic questionnaire with DeepSeek | PASS | 3.073 | {"response": {"ok": true, "needs_questionnaire": true, "questions": [{"id": "q1", "question": "核心叙事侧重？", "options": [{"id": "a", "label": "技术突破驱动史"}, {"id": "b", "label": "社会影响与伦理"}, {"id": "c", "label": "算法演进为主线"}], "al |
| TC-WEB-01 | Input Processing | Web search source retrieval | PASS | 17.054 | {"response": {"ok": true, "results": [{"title": "人工智能发展简史_中央网络安全和信息化委员会办公室", "url": "https://www.cac.gov.cn/2017-01/23/c_1120366748.htm", "snippet": "## 人工智能发展简史\n\n2017年01月23日 11:10 来源： 网络传播杂志\n\n“人工智能之父” 艾伦·图灵。\n\n**1、 |
| TC-SO-MODEL-QWEN_SIMULATED_BY_DEEPSEEK | Structured Outline | Simulated model run (qwen_simulated_by_deepseek, actual provider=deepseek, strategy=baseline) | PASS | 9.031 | {"title": "人工智能发展简史", "chapter_count": 5, "page_count": 6, "quality": {"slide_count": 6, "chapter_count": 5, "avg_bullets_per_slide": 4.0, "unique_slide_title_ratio": 1.0, "granularity_score_0_100": 100.0, "hierarchy_sco |
| TC-SO-MODEL-DEEPSEEK | Structured Outline | Simulated model run (deepseek, actual provider=deepseek, strategy=few_shot) | PASS | 8.03 | {"title": "人工智能发展简史", "chapter_count": 4, "page_count": 8, "quality": {"slide_count": 8, "chapter_count": 4, "avg_bullets_per_slide": 3.0, "unique_slide_title_ratio": 1.0, "granularity_score_0_100": 100.0, "hierarchy_sco |
| TC-SO-MODEL-GLM_SIMULATED_BY_DEEPSEEK | Structured Outline | Simulated model run (glm_simulated_by_deepseek, actual provider=deepseek, strategy=cot_silent) | PASS | 8.84 | {"title": "人工智能发展简史", "chapter_count": 4, "page_count": 8, "quality": {"slide_count": 8, "chapter_count": 4, "avg_bullets_per_slide": 3.0, "unique_slide_title_ratio": 1.0, "granularity_score_0_100": 100.0, "hierarchy_sco |
| TC-RAG-01 | RAG | DeepSeek outline generation with BM25 RAG | PASS | 31.643 | {"title": "人工智能发展简史", "chapter_count": 5, "page_count": 5, "quality": {"slide_count": 5, "chapter_count": 5, "avg_bullets_per_slide": 4.0, "unique_slide_title_ratio": 1.0, "granularity_score_0_100": 83.33, "hierarchy_sco |
