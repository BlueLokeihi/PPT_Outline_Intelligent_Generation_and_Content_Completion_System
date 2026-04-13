# outline（大纲生成）

本目录包含“结构化 PPT 骨架（章节—页—要点—备注）”的生成与对比评测。

- 输入从：`outline/input/` 读取
- 输出写到：`outline/output/`

运行前约定：在终端先进入 backend 目录。

```powershell
cd backend
```

## 对比运行（多模型 × 多策略 × Schema on/off）

```powershell
python -m outline.cli --mode compare --input outline/input/sample_topic.txt --runs 3 --schema both
```

参数说明（控制组合维度）：
- 多模型：`--providers qwen,glm,deepseek`
- 多策略：`--strategies <strategy1>,<strategy2>,...`
- Schema 开关：`--schema on|off|both`
- 稳定性重复次数：`--runs N`

输出：
- 单次运行：`outline/output/{timestamp}_{provider}_{strategy}_{schema}_runN.json`
- 汇总：`outline/output/{timestamp}_summary.json`

## 单次运行（单 provider × 单策略）

```powershell
python -m outline.cli --mode single --input outline/input/sample_topic.txt --provider qwen --strategy baseline --schema on
```

## 配置文件
- 默认读取：`config/models.json`
- 如需指定：加 `--config config/models.json`
