from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Literal, Tuple

StrategyName = Literal["baseline", "few_shot", "cot_silent"]


@dataclass(frozen=True)
class PromptOptions:
    strategy: StrategyName
    enforce_schema: bool
    min_slides: int = 10
    max_slides: int = 18


def build_messages(topic_text: str, opts: PromptOptions) -> List[dict[str, str]]:
    system = (
        "你是一个PPT大纲生成器。你会收到一段主题资料（可能较长）。"
        "请在内部进行分析与规划，但不要输出任何推理过程。"
        "最终只输出严格JSON（不要Markdown代码块、不要解释文字）。"
    )

    schema_block = _schema_instructions() if opts.enforce_schema else _loose_instructions()
    quality_block = (
        "分页粒度要求：总页数尽量在"
        f"{opts.min_slides}-{opts.max_slides}页。每页3-6条要点。"
        "章节数量建议3-8个，每章包含若干页。备注用于讲解提示/例子/过渡语。"
    )

    if opts.strategy == "baseline":
        user = (
            "根据下面的主题资料生成PPT骨架，结构必须是：章节 — 页 — 要点 — 备注。\n"
            + quality_block
            + "\n"
            + schema_block
            + "\n主题资料：\n"
            + topic_text
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    if opts.strategy == "cot_silent":
        user = (
            "任务：从主题资料生成结构化PPT骨架（章节—页—要点—备注）。\n"
            "请先在心里完成：信息抽取→章节划分→分页规划→每页要点与备注。"
            "不要输出你的思考过程，只输出最终JSON。\n"
            + quality_block
            + "\n"
            + schema_block
            + "\n主题资料：\n"
            + topic_text
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    if opts.strategy == "few_shot":
        example_user, example_assistant = _few_shot_example(opts)
        user = (
            "现在请对新的主题资料完成同样任务。\n"
            + quality_block
            + "\n"
            + schema_block
            + "\n主题资料：\n"
            + topic_text
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": example_user},
            {"role": "assistant", "content": example_assistant},
            {"role": "user", "content": user},
        ]

    raise ValueError(f"Unknown strategy: {opts.strategy}")


def _loose_instructions() -> str:
    return (
        "输出格式要求：输出一个JSON object，字段至少包含 title 与 chapters。"
        "chapters 是数组，每个元素包含 title 与 pages；pages 是数组，每个元素包含 title、bullets、notes。"
        "请确保是可被 json.loads 解析的严格JSON。"
    )


def _schema_instructions() -> str:
    # 保持可读性，避免把完整 JSON Schema 贴太长；但明确 required 字段与 additionalProperties。
    return (
        "严格结构要求（必须满足）：\n"
        "- 根对象：{title: string, chapters: Chapter[]}，可选 assumptions: string[]\n"
        "- Chapter：{title: string, pages: Page[]}\n"
        "- Page：{title: string, bullets: string[], notes: string}\n"
        "- 不允许出现额外字段（additionalProperties=false），不要输出 null。\n"
        "- bullets 每页1-10条，建议3-6条。\n"
        "- 只输出JSON本体，不要附带任何解释。"
    )


def _few_shot_example(opts: PromptOptions) -> Tuple[str, str]:
    example_topic = (
        "主题：软件项目进度管理入门\n"
        "要点：甘特图/里程碑/风险与缓冲/沟通机制\n"
        "受众：本科生\n"
        "期望：约10-12页\n"
    )

    example_user = (
        "根据下面的主题资料生成PPT骨架，结构必须是：章节 — 页 — 要点 — 备注。\n"
        f"分页粒度要求：总页数尽量在{opts.min_slides}-{opts.max_slides}页。每页3-6条要点。\n"
        + (_schema_instructions() if opts.enforce_schema else _loose_instructions())
        + "\n主题资料：\n"
        + example_topic
    )

    # 示例保持短小，但覆盖章节/页/要点/备注。
    example_outline = {
        "title": "软件项目进度管理入门",
        "chapters": [
            {
                "title": "为什么要做进度管理",
                "pages": [
                    {
                        "title": "课程目标与产出",
                        "bullets": [
                            "明确进度概念与常见误区",
                            "了解计划-执行-跟踪闭环",
                            "会读懂基本计划图",
                        ],
                        "notes": "先用一个延期案例引入",
                    },
                    {
                        "title": "进度失控的典型原因",
                        "bullets": ["需求频繁变化", "资源不可用或切换成本", "估算偏差与沟通不足"],
                        "notes": "强调：问题通常是系统性的",
                    },
                ],
            },
            {
                "title": "常用工具与方法",
                "pages": [
                    {
                        "title": "甘特图与关键路径",
                        "bullets": ["任务分解到可交付", "标注依赖关系", "识别关键路径"],
                        "notes": "可现场演示一个小例子",
                    },
                    {
                        "title": "里程碑与验收",
                        "bullets": ["里程碑代表阶段完成", "定义可验收标准", "与团队同步节奏"],
                        "notes": "备注可给出里程碑模板",
                    },
                ],
            },
            {
                "title": "风险、缓冲与沟通",
                "pages": [
                    {
                        "title": "风险与缓冲设置",
                        "bullets": ["识别高不确定性任务", "设置时间缓冲与优先级", "定期复盘并调整"],
                        "notes": "提示：缓冲不是浪费",
                    },
                    {
                        "title": "沟通与跟踪机制",
                        "bullets": ["每日站会/周报节奏", "看板与阻塞项升级", "版本节奏与发布计划"],
                        "notes": "给出一套可执行的会议节奏",
                    },
                ],
            },
        ],
    }

    example_assistant = json.dumps(example_outline, ensure_ascii=False, separators=(",", ":"))
    return example_user, example_assistant
