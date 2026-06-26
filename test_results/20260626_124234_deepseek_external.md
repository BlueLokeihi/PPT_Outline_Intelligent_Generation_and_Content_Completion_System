# DeepSeek Acceptance Results (deepseek_external)

- Generated at: 2026-06-26T12:42:34
- Summary: {'PASS': 1, 'FAIL': 5}
- Note: qwen/glm model rows are simulated with actual provider `deepseek`, because only DeepSeek API key is available.

| ID | Requirement | Test | Status | Duration(s) | Notes |
|---|---|---|---|---:|---|
| TC-IP-03 | Input Processing | Dynamic questionnaire with DeepSeek | PASS | 0.018 | {"response": {"ok": true, "needs_questionnaire": false, "questions": [], "error": "error sending request for url (https://api.deepseek.com/chat/completions)"}} |
| TC-WEB-01 | Input Processing | Web search source retrieval | FAIL | 0.554 | ok=false: {'ok': False, 'results': [], 'error': '两个搜索引擎均不可用，请稍后重试', 'jina_error': "HTTPSConnectionPool(host='s.jina.ai', port=443): Max retries exceeded with url: /%E4%BA%BA%E5%B7%A5%E6%99%BA%E8%83%BD%20%E5%8F%91%E5%B1%95%20%E7%AE%80%E5%8F%B2 (Caused by NewConnectionError('<urllib3.connection.HTTPSConnection object at 0x0000016ABD866FB0>: Failed to establish a new connection: [WinError 10013] 以一种访问权限不允许的方式做了一个访问套接字的尝试。'))"} |
| TC-SO-MODEL-QWEN_SIMULATED_BY_DEEPSEEK | Structured Outline | Simulated model run (qwen_simulated_by_deepseek, actual provider=deepseek, strategy=baseline) | FAIL | 0.007 | ok=false: {'ok': False, 'provider': 'deepseek', 'strategy': 'baseline', 'schema': 'on', 'elapsedS': 0.002, 'error': 'error sending request for url (https://api.deepseek.com/chat/completions)'} |
| TC-SO-MODEL-DEEPSEEK | Structured Outline | Simulated model run (deepseek, actual provider=deepseek, strategy=few_shot) | FAIL | 0.005 | ok=false: {'ok': False, 'provider': 'deepseek', 'strategy': 'few_shot', 'schema': 'on', 'elapsedS': 0.002, 'error': 'error sending request for url (https://api.deepseek.com/chat/completions)'} |
| TC-SO-MODEL-GLM_SIMULATED_BY_DEEPSEEK | Structured Outline | Simulated model run (glm_simulated_by_deepseek, actual provider=deepseek, strategy=cot_silent) | FAIL | 0.016 | ok=false: {'ok': False, 'provider': 'deepseek', 'strategy': 'cot_silent', 'schema': 'on', 'elapsedS': 0.0, 'error': 'error sending request for url (https://api.deepseek.com/chat/completions)'} |
| TC-RAG-01 | RAG | DeepSeek outline generation with BM25 RAG | FAIL | 0.012 | ok=false: {'ok': False, 'provider': 'deepseek', 'strategy': 'baseline', 'schema': 'on', 'elapsedS': 0.001, 'error': 'error sending request for url (https://api.deepseek.com/chat/completions)'} |
