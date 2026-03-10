"""
聚类与去重模块
负责将多条报道同一事件的 RawItem 聚合为一个 Event。
策略：
  1. 规则去重：URL 完全相同 或 标题哈希完全相同 → 直接合并
  2. 语义聚类：通过 Gemini Embedding API 计算文本向量余弦相似度
     - 若相似度 > 阈值（默认 0.78）→ 归入同一 Event
     - 否则创建新 Event
  3. 降级策略：若 Embedding 不可用，则仅用标题关键词重叠度做简单聚类
"""

import hashlib
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from rich.console import Console

console = Console()

# ===================== 工具函数 =====================

def _title_hash(title: str) -> str:
    """对标题做标准化后取 MD5"""
    normalized = re.sub(r"[\s\-_:：—|｜\[\]【】()（）]", "", title.lower().strip())
    return hashlib.md5(normalized.encode()).hexdigest()


def _title_keywords(title: str) -> set:
    """提取标题中的关键词集合（简单分词，去掉停用词）"""
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to",
                  "for", "of", "and", "or", "but", "with", "by", "from", "as", "its",
                  "this", "that", "it", "be", "has", "have", "had", "will", "can", "could",
                  "about", "not", "new", "how", "what", "why", "when", "which", "who",
                  "的", "了", "是", "在", "和", "与", "一个", "不", "也", "就", "都",
                  "被", "让", "将", "对", "又", "等", "已", "为"}
    words = re.findall(r"[a-zA-Z]+|[\u4e00-\u9fff]+", title.lower())
    return {w for w in words if w not in stop_words and len(w) > 1}


def _keyword_similarity(title_a: str, title_b: str) -> float:
    """基于关键词重叠度的标题相似度 (Jaccard)"""
    kw_a = _title_keywords(title_a)
    kw_b = _title_keywords(title_b)
    if not kw_a or not kw_b:
        return 0.0
    intersection = kw_a & kw_b
    union = kw_a | kw_b
    return len(intersection) / len(union)


# ===================== Embedding 相关 =====================

def _get_embeddings_via_gemini(texts: list[str]) -> Optional[list[list[float]]]:
    """
    使用 Gemini Embedding API 获取文本向量。
    需要设置 GEMINI_API_KEY 环境变量。
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        # 使用 gemini-embedding-001 模型
        result = client.models.embed_content(
            model="gemini-embedding-001",
            contents=texts,
        )
        return [emb.values for emb in result.embeddings]
    except Exception as e:
        console.print(f"  [yellow]Embedding 调用失败: {e}，将使用关键词匹配降级[/yellow]")
        return None


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """计算两个向量的余弦相似度"""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ===================== 主聚类逻辑 =====================

def cluster_items(raw_items: list[dict], similarity_threshold: float = 0.78) -> list[dict]:
    """
    对 raw_items 进行去重与聚类，生成 Event 列表。
    
    流程：
    1. URL 去重
    2. 标题 Hash 去重
    3. 尝试 Embedding 语义聚类（失败则用关键词聚类降级）
    
    参数:
        raw_items: 标准化的原始条目列表
        similarity_threshold: 聚类相似度阈值
    返回:
        事件列表 (list[dict])
    """
    if not raw_items:
        return []

    console.print(f"\n[bold]🔗 开始聚类 (共 {len(raw_items)} 条)[/bold]\n")

    # 第一步：URL 去重
    seen_urls = {}
    unique_items = []
    for item in raw_items:
        url = item.get("url", "")
        if url not in seen_urls:
            seen_urls[url] = item
            unique_items.append(item)
    
    dup_count = len(raw_items) - len(unique_items)
    if dup_count > 0:
        console.print(f"  [dim]URL 去重移除 {dup_count} 条[/dim]")

    # 第二步：标题 Hash 去重
    seen_titles = {}
    deduped_items = []
    for item in unique_items:
        th = _title_hash(item.get("title", ""))
        if th not in seen_titles:
            seen_titles[th] = item
            deduped_items.append(item)
        else:
            # 标题几乎相同的条目，只保留第一条但可以关联
            pass
    
    dup_count2 = len(unique_items) - len(deduped_items)
    if dup_count2 > 0:
        console.print(f"  [dim]标题去重移除 {dup_count2} 条[/dim]")

    # 第三步：语义聚类
    events = []
    use_embedding = True

    # 尝试获取 embedding
    titles = [item.get("title", "") for item in deduped_items]
    embeddings = _get_embeddings_via_gemini(titles)

    if embeddings is None:
        use_embedding = False
        console.print("  [yellow]⚠ 使用关键词匹配模式进行聚类[/yellow]")

    # 逐条分配到 Event
    assigned = [False] * len(deduped_items)

    for i, item in enumerate(deduped_items):
        if assigned[i]:
            continue

        # 创建新事件
        event_id = f"evt_{uuid.uuid4().hex[:8]}"
        event = {
            "id": event_id,
            "title": item.get("title", ""),
            "summary": item.get("summary", "") or item.get("content", "")[:500],
            "article_ids": [item["id"]],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "talkability_score": 0.0,
            "category": item.get("category", ""),
        }
        assigned[i] = True

        # 寻找可合并的条目
        for j in range(i + 1, len(deduped_items)):
            if assigned[j]:
                continue

            if use_embedding and embeddings:
                sim = _cosine_similarity(embeddings[i], embeddings[j])
            else:
                sim = _keyword_similarity(item.get("title", ""), deduped_items[j].get("title", ""))

            if sim >= similarity_threshold:
                event["article_ids"].append(deduped_items[j]["id"])
                assigned[j] = True

        events.append(event)

    console.print(f"\n[bold green]✅ 聚类完成: {len(deduped_items)} 条 → {len(events)} 个事件[/bold green]\n")
    return events
