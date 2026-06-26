# DeepSeek Acceptance Results (deepseek_external_network)

- Generated at: 2026-06-26T12:44:02
- Summary: {'PASS': 6}
- Note: qwen/glm model rows are simulated with actual provider `deepseek`, because only DeepSeek API key is available.

| ID | Requirement | Test | Status | Duration(s) | Notes |
|---|---|---|---|---:|---|
| TC-IP-03 | Input Processing | Dynamic questionnaire with DeepSeek | PASS | 2.412 | {"response": {"ok": true, "needs_questionnaire": true, "questions": [{"id": "q1", "question": "核心叙事侧重？", "options": [{"id": "a", "label": "技术突破为主线"}, {"id": "b", "label": "人物与公司故事"}, {"id": "c", "label": "社会影响与伦理"}], "al |
| TC-WEB-01 | Input Processing | Web search source retrieval | PASS | 24.232 | {"response": {"ok": true, "results": [{"title": "人工智能发展简史_中央网络安全和信息化委员会办公室", "url": "https://www.cac.gov.cn/2017-01/23/c_1120366748.htm", "snippet": "1981年，日本经济产业省拨款8.5亿美元用以研发第五代计算机项目，在当时被叫做人工智能计算机。随后，英国、美国纷纷响应，开始向信息技术领域 |
| TC-SO-MODEL-QWEN_SIMULATED_BY_DEEPSEEK | Structured Outline | Simulated model run (qwen_simulated_by_deepseek, actual provider=deepseek, strategy=baseline) | PASS | 5.82 | {"title": "人工智能发展简史", "chapter_count": 4, "page_count": 4, "quality": {"slide_count": 4, "chapter_count": 4, "avg_bullets_per_slide": 4.0, "unique_slide_title_ratio": 1.0, "granularity_score_0_100": 66.67, "hierarchy_sco |
| TC-SO-MODEL-DEEPSEEK | Structured Outline | Simulated model run (deepseek, actual provider=deepseek, strategy=few_shot) | PASS | 4.343 | {"title": "人工智能发展简史", "chapter_count": 3, "page_count": 6, "quality": {"slide_count": 6, "chapter_count": 3, "avg_bullets_per_slide": 3.0, "unique_slide_title_ratio": 1.0, "granularity_score_0_100": 100.0, "hierarchy_sco |
| TC-SO-MODEL-GLM_SIMULATED_BY_DEEPSEEK | Structured Outline | Simulated model run (glm_simulated_by_deepseek, actual provider=deepseek, strategy=cot_silent) | PASS | 7.998 | {"title": "人工智能发展简史", "chapter_count": 4, "page_count": 8, "quality": {"slide_count": 8, "chapter_count": 4, "avg_bullets_per_slide": 4.0, "unique_slide_title_ratio": 1.0, "granularity_score_0_100": 100.0, "hierarchy_sco |
| TC-RAG-01 | RAG | DeepSeek outline generation with BM25 RAG | PASS | 30.465 | {"title": "人工智能发展简史", "chapter_count": 6, "page_count": 6, "quality": {"slide_count": 6, "chapter_count": 6, "avg_bullets_per_slide": 4.0, "unique_slide_title_ratio": 1.0, "granularity_score_0_100": 100.0, "hierarchy_sco |
