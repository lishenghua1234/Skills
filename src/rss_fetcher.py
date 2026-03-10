"""
RSS 抓取模块
负责：
1. 读取 sources.yaml 配置
2. 遍历已启用的 RSS 来源拉取最新条目
3. 将条目标准化为 RawItem 格式
"""

import hashlib
import time
import yaml
import feedparser
import requests
from datetime import datetime, timedelta, timezone
from dateutil import parser as dateparser
from pathlib import Path
from typing import Optional
from rich.console import Console

console = Console()

# 默认请求头，模拟浏览器访问
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def load_sources(config_path: str = "sources.yaml") -> dict:
    """
    加载数据源配置文件。
    返回完整配置字典，包含 sources（列表）和 settings（全局设置）。
    """
    path = Path(config_path)
    if not path.exists():
        console.print(f"[red]错误：找不到配置文件 {config_path}[/red]")
        return {"sources": [], "settings": {}}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _make_id(source_id: str, url: str) -> str:
    """根据来源ID和URL生成唯一的条目ID"""
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    return f"{source_id}::{url_hash}"


def _parse_date(date_str: str) -> Optional[str]:
    """解析各种格式的日期字符串，转为 ISO 格式"""
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    try:
        dt = dateparser.parse(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def _is_within_hours(date_iso: str, hours: int) -> bool:
    """检查给定日期是否在过去 N 小时之内"""
    try:
        dt = dateparser.parse(date_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return dt >= cutoff
    except Exception:
        # 解析失败时保留条目（宽容策略）
        return True


def fetch_single_source(source: dict, since_hours: int = 24) -> list[dict]:
    """
    拉取单个 RSS 来源的最新条目。
    参数:
        source: 来源配置字典
        since_hours: 只保留过去N小时的条目
    返回:
        标准化的 raw_item 字典列表
    """
    source_id = source["id"]
    url = source["url"]
    category = source.get("category", "")
    rate_limit = source.get("rate_limit", 3)

    console.print(f"  [cyan]拉取[/cyan] {source_id}: {url}")

    try:
        # 使用 requests 获取内容，更可控的超时与 User-Agent
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
    except Exception as e:
        console.print(f"  [red]✗ {source_id} 拉取失败: {e}[/red]")
        return []

    items = []
    for entry in feed.entries:
        # 提取基本字段
        link = getattr(entry, "link", "")
        if not link:
            continue

        title = getattr(entry, "title", "无标题")
        # 摘要优先取 summary，其次 description
        summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
        # 发布时间
        pub_date = getattr(entry, "published", "") or getattr(entry, "updated", "")
        pub_iso = _parse_date(pub_date)

        # 时间过滤
        if not _is_within_hours(pub_iso, since_hours):
            continue

        item_id = _make_id(source_id, link)
        raw_item = {
            "id": item_id,
            "source_id": source_id,
            "title": title.strip(),
            "url": link.strip(),
            "summary": summary.strip()[:2000],  # 限制摘要长度
            "content": "",  # 后续由 article_fetcher 填充
            "published": pub_iso,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "category": category,
        }
        items.append(raw_item)

    console.print(f"  [green]✓ {source_id}: 获取 {len(items)} 条[/green]")

    # 简单速率限制
    if rate_limit > 0:
        time.sleep(rate_limit)

    return items


def fetch_all_sources(config_path: str = "sources.yaml", since_hours: int = 24, max_items: int = 200) -> list[dict]:
    """
    拉取所有已启用来源的 RSS 条目。
    参数:
        config_path: 配置文件路径
        since_hours: 只保留过去N小时的条目
        max_items: 最大返回条数
    返回:
        标准化的 raw_item 字典列表
    """
    config = load_sources(config_path)
    sources = config.get("sources", [])
    settings = config.get("settings", {})

    # 使用配置文件中的默认值（如果命令行未指定）
    if since_hours is None:
        since_hours = settings.get("default_hours", 24)
    if max_items is None:
        max_items = settings.get("max_items", 200)

    # 按权重降序排列来源
    enabled_sources = [s for s in sources if s.get("enabled", True)]
    enabled_sources.sort(key=lambda s: s.get("weight", 5), reverse=True)

    console.print(f"\n[bold]📡 开始拉取 {len(enabled_sources)} 个来源 (过去 {since_hours} 小时)[/bold]\n")

    all_items = []
    for source in enabled_sources:
        items = fetch_single_source(source, since_hours)
        all_items.extend(items)
        if len(all_items) >= max_items:
            all_items = all_items[:max_items]
            console.print(f"[yellow]已达最大条数限制 ({max_items})，停止拉取[/yellow]")
            break

    console.print(f"\n[bold green]✅ 共获取 {len(all_items)} 条原始条目[/bold green]\n")
    return all_items
