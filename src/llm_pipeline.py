"""
LLM 流水线模块
使用 Gemini API 完成四步分析：
  1. 事件价值判断 → 可讲性评分 + AI 相关性过滤
  2. 三层解释生成 → 普通人 / 泛技术人 / 专业人
  3. 短视频素材包生成 → 标题、Hook、要点、误区、视觉建议等
使用 google-genai SDK 调用 Gemini 模型，确保返回严格 JSON。
"""

import json
import os
import re
import time
from typing import Optional

from rich.console import Console

console = Console()

# ===================== Gemini 客户端调用与容灾 =====================
from src.api_router import keys_manager

def _call_gemini_with_key(prompt: str, api_key: str) -> str:
    """
    具体的 Gemini 模型调用执行体。
    被包裹在 KeysManager 容灾外壳中运行。
    """
    from google import genai
    client = genai.Client(api_key=api_key)
    
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-preview",
        contents=prompt,
    )
    return response.text

def _call_gemini(prompt: str, max_retries: int = 3) -> str:
    """
    暴露在外的调用入口，自带容错池查询及熔断机制。
    """
    # 借助 api_router 提供的轮转执行来完成调用
    try:
        return keys_manager.execute_with_fallback(
            provider="gemini",
            max_retries_per_key=max_retries,
            task_func=_call_gemini_with_key,
            prompt=prompt
        )
    except Exception as e:
        console.print(f"  [red]!!! LLM 彻底调用失败 (所有密钥已耗尽): {e} !!![/red]")
        return ""


def _extract_json(text: str) -> Optional[dict]:
    """
    从 LLM 返回的文本中提取 JSON。
    支持处理 markdown 代码块包裹、多余文字等情况。
    """
    if not text:
        return None
    
    # 策略1：尝试直接找 ```json ... ``` 代码块
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except json.JSONDecodeError:
            pass
    
    # 策略2：尝试取花括号区域
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    # 策略3：找方括号区域（数组情况）
    bracket_match = re.search(r"\[.*\]", text, re.DOTALL)
    if bracket_match:
        try:
            return json.loads(bracket_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


# ===================== Prompt 模板 =====================

PROMPT_VALUE_JUDGE = """你是一位资深科技内容策划师。请分析以下新闻事件，判断它是否适合做成AI科技类短视频。

## 事件信息
标题: {title}
摘要: {summary}
正文片段: {content_snippet}

## 输出要求
请返回严格 JSON 格式，不要包含任何其他文字：
{{
  "is_ai_related": true/false,
  "talkability_score": 0-10的数字,
  "score_reason": "评分理由，一句话",
  "core_topic": "事件核心主题，10字以内"
}}

## 评分标准
- 10分：重大突破/发布（如新模型发布、重大政策）
- 7-9分：行业有影响力的动态（融资、产品更新、有趣应用）
- 4-6分：值得一提但不太突出的消息
- 1-3分：太小众/太旧/太无聊
- 0分：与 AI 完全无关

请只返回 JSON，不要有任何其他文字。"""



PROMPT_XHS = """你是一位小红书爆款图文创作者，擅长把严肃的AI科技新闻写得极具"网感"、分享欲和干货价值。

## 事件信息
标题: {title}
核心主题: {core_topic}
内容: {content}

## 输出要求
请返回严格 JSON 格式，不要包含任何其他文字：
{{
  "titles": ["网感标题1", "网感标题2", "网感标题3"],
  "content": "多段落的小红书正文，必须包含大量 Emoji，格式分明，带有勾人的开头、干货主体和互动引导结尾",
  "visual_suggestions": ["封面图文字建议", "内页1图像建议", "内页2图像建议"],
  "tags": ["#AI", "#标签2", "#标签3"]
}}

## 创作指导
- **标题**：夸张、反差、引发焦虑或极强的好奇心（如"打工人必看！..." "快跑！..." "藏不住了..."）。**字数必须严格小于等于 20 个字（满足小红书系统限制）**。
- **正文**：
  - 首段直接抛出痛点或极大的价值。
  - 主体采用列表结构，排版留白，熟练使用 💡、🔥、👉 等表情符号。
  - 术语一定要“人话”解释。
  - 结尾抛出问题引导评论区讨论（如："各位怎么看？评论区聊聊！"）。
- **图片建议**：小红书是视觉平台，需要脑补如果做成图文轮播，每一页放什么画面和文案，给出具体指示。
- **标签**：3-6个，不要带空格，全网热门的话题。

请只返回 JSON，不要有任何其他文字。"""


# ===================== 流水线步骤 =====================

def step_value_judge(event: dict, raw_items_map: dict) -> dict:
    """
    步骤1：事件价值判断
    评估事件是否与 AI 相关、可讲性评分。
    """
    title = event.get("title", "")
    summary = event.get("summary", "")
    
    # 拼接关联文章的内容作为上下文
    content_parts = []
    for aid in event.get("article_ids", []):
        item = raw_items_map.get(aid, {})
        c = item.get("content", "") or item.get("summary", "")
        if c:
            content_parts.append(c[:500])
    content_snippet = "\n".join(content_parts)[:1500]
    
    if not content_snippet:
        content_snippet = summary

    prompt = PROMPT_VALUE_JUDGE.format(
        title=title,
        summary=summary,
        content_snippet=content_snippet
    )

    result_text = _call_gemini(prompt)
    result = _extract_json(result_text)

    if result:
        event["talkability_score"] = result.get("talkability_score", 0)
        event["is_ai_related"] = result.get("is_ai_related", False)
        event["core_topic"] = result.get("core_topic", "")
        event["score_reason"] = result.get("score_reason", "")
    else:
        # JSON 解析失败时设默认值
        event["talkability_score"] = 5.0
        event["is_ai_related"] = True
        event["core_topic"] = title[:20]
        event["score_reason"] = "LLM返回解析失败，使用默认值"

    return event



def step_xiaohongshu(event: dict, raw_items_map: dict) -> Optional[dict]:
    """
    步骤4：生成小红书图文素材
    """
    title = event.get("title", "")
    core_topic = event.get("core_topic", title[:20])

    # 拼接内容
    content_parts = []
    for aid in event.get("article_ids", []):
        item = raw_items_map.get(aid, {})
        c = item.get("content", "") or item.get("summary", "")
        if c:
            content_parts.append(c[:600])
    content = "\n".join(content_parts)[:1500] or event.get("summary", "")

    prompt = PROMPT_XHS.format(
        title=title,
        core_topic=core_topic,
        content=content
    )

    result_text = _call_gemini(prompt)
    result = _extract_json(result_text)

    if result:
        return {
            "titles": result.get("titles", [title]),
            "content": result.get("content", ""),
            "visual_suggestions": result.get("visual_suggestions", []),
            "tags": result.get("tags", [])
        }
    else:
        console.print(f"  [red]✗ 小红书素材生成失败: {title[:40]}[/red]")
        return None


# ===================== 完整流水线 =====================

def run_llm_pipeline(events: list[dict], raw_items: list[dict],
                     talkability_threshold: float = 5.0) -> list[dict]:
    """
    运行精简后的小红书专属 LLM 分析流水线。
    
    流程：
    1. 对每个 Event 做价值判断
    2. 过滤掉不相关 / 低可讲性的事件
    3. 针对所有留存事件调用成组装配 (全量执行 step_xiaohongshu)
    
    参数:
        events: 聚类后的事件列表
        raw_items: 原始条目列表
        talkability_threshold: 可讲性评分阈值
    返回:
        生成的小红书图文素材包列表
    """
    if not events:
        console.print("[yellow]没有事件可以处理[/yellow]")
        return []

    raw_items_map = {item["id"]: item for item in raw_items}

    # === 步骤1：价值判断 ===
    console.print(f"\n[bold]🧠 步骤1/2: 事件价值判断 (共 {len(events)} 个事件)[/bold]\n")

    for i, event in enumerate(events):
        console.print(f"  [{i + 1}/{len(events)}] 评估: {event['title'][:50]}...")
        event = step_value_judge(event, raw_items_map)
        score = event.get("talkability_score", 0)
        ai_related = event.get("is_ai_related", False)
        console.print(f"    → 可讲性: {score}/10 | AI相关: {'是' if ai_related else '否'}")
        
    qualified = [
        e for e in events
        if e.get("is_ai_related", False) and e.get("talkability_score", 0) >= talkability_threshold
    ]
    console.print(f"\n  [cyan]过滤后: {len(qualified)}/{len(events)} 个事件符合条件 (阈值≥{talkability_threshold})[/cyan]\n")

    if not qualified:
        console.print("[yellow]⚠ 没有事件通过过滤，无法生成素材[/yellow]")
        return []

    # === 步骤2：小红书素材直出生成 ===
    console.print(f"\n[bold]🎬 步骤2/2: 生成小红书网感图文 (共 {len(qualified)} 个事件)[/bold]\n")

    materials = []
    for i, event in enumerate(qualified):
        material = {
            "event_id": event["id"],
            "generated_at": __import__("datetime").datetime.now().isoformat()
        }
        
        console.print(f"  [{i + 1}/{len(qualified)}] 创作图文中: {event['title'][:50]}...")
        xhs_m = step_xiaohongshu(event, raw_items_map)
        if xhs_m:
            material["xiaohongshu"] = xhs_m
            materials.append(material)
            console.print(f"    → ✓ 小红书内容抽取成功！")
        else:
            console.print(f"    → [red]✗ 本次事件素材大模型抽提失败[/red]")
        
        time.sleep(1)

    console.print(f"\n[bold green]✅ LLM 流水线完成: 共创作 {len(materials)} 篇小红书爆款图文[/bold green]\n")
    return materials
