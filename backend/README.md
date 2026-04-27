# 后端（backend）

本目录包含：
- 结构化 PPT 骨架生成（章节—页—要点—备注）
- Prompt 策略 / Schema 约束 / 多模型稳定性对比脚本

运行约定：Python 执行前请先进入本目录。

## 环境基线（可复现）

- Python：3.12.7
- 依赖：见 requirements.txt（精确锁定版本，便于同学复现）

推荐在新机器按以下方式创建环境并安装：

```powershell
conda create -n pptoutline python=3.12.7 -y
conda activate pptoutline
cd backend
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 目录结构
- config/models.json：模型配置（base_url/model/api_key_env 等）
- llm/：大模型调用封装（集中在一个文件：llm/client.py）
- outline/：大纲生成与对比（内部包含 input/ 与 output/）
- rag/：RAG 功能预留（空目录）
- run_outline.py：兼容入口（建议使用 python -m outline.compare）

## 安装依赖

在项目根目录创建/激活好 Python 环境后，进入 backend 安装：

```powershell
cd backend
pip install -r requirements.txt
```

## 配置 API Key

```powershell
cd backend
$env:QWEN_API_KEY = "sk-99cda0ecf3c844e79ebc66145cf09151"
$env:DEEPSEEK_API_KEY = "sk-26c711ce77cd4162912a783a3ad6355c"
$env:GLM_API_KEY = "ec48f7ca8edb45e083f9022e7ad641fb.ZvwxcUe4Za5Y28xl"
```

## 支持的模型

当前支持以下大模型调用，配置详见 `config/models.json`：

- **Qwen**
  - Base URL: `https://dashscope.aliyuncs.com/compatible-mode/v1`
  - Model: `qwen-plus`
  - API Key 环境变量: `QWEN_API_KEY`
- **DeepSeek**
  - Base URL: `https://api.deepseek.com`
  - Model: `deepseek-chat`
  - API Key 环境变量: `DEEPSEEK_API_KEY`
- **GLM**
  - Base URL: `https://open.bigmodel.cn/api/paas/v4`
  - Model: `glm-4`
  - API Key 环境变量: `GLM_API_KEY`

## 运行对比脚本

### 基本对比（多模型 × 多策略 × Schema on/off）

```powershell
cd backend
python -m outline.cli --mode compare --input outline/input/sample_topic.txt --runs 1 --schema both
```


## 单次运行（单 provider × 单策略）

```powershell
cd backend
python -m outline.cli --mode single --input outline/input/sample_topic.txt --provider qwen --strategy baseline --schema on
```

说明（哪个参数控制哪个组合维度）：
- 多模型：`--providers qwen,glm,deepseek`
- 多策略：`--strategies baseline,few_shot,cot_silent`
- Schema 开关：`--schema on|off`
- 稳定性重复次数：`--runs N`（每个 provider×strategy×schema 组合重复 N 次）

输入/输出：
- 输入从 outline/input/ 读取（`--input` 指向具体文件）
- 输出写入 outline/output/：
	- 单次运行：outline/output/{timestamp}_{provider}_{strategy}_{schema}_runN.json
	- 汇总文件：outline/output/{timestamp}_summary.json



