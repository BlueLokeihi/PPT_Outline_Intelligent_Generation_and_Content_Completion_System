# 5.2 效率对比实验记录（王相）

## 任务信息

- WBS：5.2 效率对比实验
- 负责人：王相
- 周期：Week 10 - Week 11
- 工时：8h（W10 4h，W11 4h）
- 交付位置：`backend/outline`
- 关联模块：`outline.cli`、`outline.evaluation`、`outline.output`

## 实验目标

本任务用于验证 PPT 大纲生成模块在不同模型、不同 Prompt 策略、Schema 约束开关下的效率和稳定性表现。实验重点不是单次生成结果是否“看起来完整”，而是比较不同组合在可复现条件下的生成耗时、成功率、Schema 合规率、结构质量和稳定性。

## 实验对象

当前系统支持以下对比维度：

| 维度 | 取值 | 说明 |
|---|---|---|
| 模型 provider | `qwen`、`glm`、`deepseek` | 由 `backend/config/models.json` 配置 |
| Prompt 策略 | `baseline`、`few_shot`、`cot_silent` | 由 `backend/outline/prompt_strategies.py` 构造 |
| Schema 约束 | `on`、`off`、`both` | 对比结构化输出约束的影响 |
| 重复次数 | `--runs N` | 用于观察稳定性 |
| 输入样例 | `outline/input/sample_topic.txt` | 默认实验输入 |

## 实验命令

在项目根目录进入后端目录后执行：

```powershell
cd backend
python -m outline.cli --mode compare --input outline/input/sample_topic.txt --providers qwen,glm,deepseek --strategies baseline,few_shot,cot_silent --schema both --runs 3
```

如需快速冒烟验证，可将 `--runs` 调整为 1：

```powershell
cd backend
python -m outline.cli --mode compare --input outline/input/sample_topic.txt --providers qwen,glm,deepseek --strategies baseline,few_shot,cot_silent --schema both --runs 1
```

## 输出文件

实验结果写入 `backend/outline/output`：

| 文件类型 | 命名规则 | 用途 |
|---|---|---|
| 单次结果 | `{timestamp}_{provider}_{strategy}_{schema}_runN.json` | 保存单次请求的元数据、原始响应和质量指标 |
| 汇总结果 | `{timestamp}_summary.json` | 保存全部组合、稳定性和平均质量分 |

仓库中已有历史样例结果：`backend/outline/output/20260413_150702_summary.json`。该结果覆盖 `qwen`、`glm`、`deepseek` 三个 provider，覆盖 `baseline`、`few_shot`、`cot_silent` 三种策略，并同时比较 Schema on/off。

## 评价指标

代码层面的指标来源如下：

| 指标 | 字段 | 来源 | 说明 |
|---|---|---|---|
| 生成耗时 | `elapsed_s` | `outline.generator.generate_once` 调用计时 | 越低表示响应效率越高 |
| 成功率 | `stability.ok_rate` | `outline.evaluation.compute_stability` | 成功生成 outline 的比例 |
| Schema 通过率 | `stability.schema_ok_rate` | `outline.evaluation.compute_stability` | Schema 开启时衡量结构合规 |
| 标题稳定性 | `stability.avg_pairwise_title_similarity_0_1` | `SequenceMatcher` | 多次运行标题相似度 |
| 页数 | `quality.slide_count` | `outline.evaluation.compute_quality` | 是否落在预期页数区间 |
| 章节数 | `quality.chapter_count` | `outline.evaluation.compute_quality` | 是否形成合理层级 |
| 要点粒度 | `quality.avg_bullets_per_slide` | `outline.evaluation.compute_quality` | 每页 bullet 数是否适中 |
| 总质量分 | `quality.overall_score_0_100` | `outline.evaluation.compute_quality` | 结构粒度、层级、连贯性的综合得分 |

## 对比方法

1. 固定输入文件，避免题目变化影响生成耗时和结构质量。
2. 固定模型配置，使用 `backend/config/models.json` 中的 provider 和 model。
3. 对每组 `provider x strategy x schema` 至少运行 3 次。
4. 从 summary 文件中提取每组平均耗时、成功率、Schema 通过率和平均质量分。
5. 按以下原则判断可交付组合：
   - `ok_rate` 应接近或等于 1.0。
   - Schema on 组合应优先保证 `schema_ok_rate`。
   - `overall_score_0_100` 高且 `elapsed_s` 低的组合可作为默认推荐。
   - 若耗时较低但结构质量明显下降，不作为默认方案。

## 验收结论

当前系统已经具备效率对比实验所需的自动化入口和结构化指标输出。`outline.cli` 能一次性批量运行多模型、多策略、Schema 开关组合；`outline.evaluation` 能为生成结果提供质量分和稳定性指标；`outline/output` 能保留每次运行记录和汇总文件，满足课程项目“效率对比实验”的验收要求。

## 后续改进建议

- 增加一个结果汇总脚本，将 summary JSON 自动转换为 CSV 或 Markdown 表格。
- 在实验记录中补充网络环境、运行机器、API 限流情况，降低外部波动对耗时指标的影响。
- 增加更多真实用户主题样本，避免只在 `sample_topic.txt` 上评估。
