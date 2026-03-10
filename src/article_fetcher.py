"""
正文抓取模块
根据 raw_item 中的 URL 抓取文章正文。
策略：使用 requests + BeautifulSoup 提取 <article> 或 <main> 内的文本。
若抓取失败则平滑降级，保留 RSS summary 继续后续流程。
"""

import requests
from bs4 import BeautifulSoup
from rich.console import Console

console = Console()

# 请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def fetch_article_content(url: str, timeout: int = 10) -> str:
    """
    从给定 URL 抓取正文内容。
    抓取策略：
    1. 优先提取 <article> 标签内容
    2. 其次提取 <main> 标签内容  
    3. 再次提取 <div class="content/post/entry"> 类似容器
    4. 最后回退到 <body> 并取前 3000 字符
    
    参数:
        url: 文章链接
        timeout: 请求超时（秒）
    返回:
        提取到的纯文本，失败返回空字符串
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        # 尝试自动检测编码
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        # 移除无关标签
        for tag in soup.find_all(["script", "style", "nav", "header", "footer", "aside", "iframe"]):
            tag.decompose()

        # 策略1：<article> 标签
        article = soup.find("article")
        if article:
            text = article.get_text(separator="\n", strip=True)
            if len(text) > 100:
                return text[:5000]

        # 策略2：<main> 标签
        main = soup.find("main")
        if main:
            text = main.get_text(separator="\n", strip=True)
            if len(text) > 100:
                return text[:5000]

        # 策略3：常见正文容器的 class 名
        for class_name in ["content", "post-content", "entry-content", "article-body", "post-body"]:
            container = soup.find("div", class_=class_name)
            if container:
                text = container.get_text(separator="\n", strip=True)
                if len(text) > 100:
                    return text[:5000]

        # 策略4：整个 body 的前 3000 字符（兜底）
        body = soup.find("body")
        if body:
            text = body.get_text(separator="\n", strip=True)
            return text[:3000]

        return ""

    except Exception as e:
        # 抓取失败不影响流程
        return ""


def enrich_items_with_content(raw_items: list[dict], max_fetch: int = 50) -> list[dict]:
    """
    为 raw_items 列表中的条目补充正文内容。
    如果 raw_item 的 content 字段已有内容则跳过。
    
    参数:
        raw_items: 原始条目列表
        max_fetch: 最多抓取正文的条目数（避免大量请求）
    返回:
        更新后的 raw_items（原地修改并返回）
    """
    fetched_count = 0
    success_count = 0

    console.print(f"\n[bold]📄 开始抓取正文 (最多 {max_fetch} 篇)[/bold]\n")

    for item in raw_items:
        if fetched_count >= max_fetch:
            break
        # 如果已有正文内容，跳过
        if item.get("content", "").strip():
            continue

        url = item.get("url", "")
        if not url:
            continue

        content = fetch_article_content(url)
        if content:
            item["content"] = content
            success_count += 1
            console.print(f"  [green]✓[/green] {item['title'][:50]}...")
        else:
            # 降级：使用 summary 作为内容
            item["content"] = item.get("summary", "")
            console.print(f"  [yellow]↓[/yellow] {item['title'][:50]}... (使用摘要降级)")

        fetched_count += 1

    console.print(f"\n[bold green]✅ 正文抓取完成: {success_count}/{fetched_count} 成功[/bold green]\n")
    return raw_items
