"""
命令行入口模块
提供一条命令运行完整流水线：拉取 → 正文抓取 → 存储 → 聚类 → LLM 分析 → 导出素材包

用法:
    uv run python -m src.cli run
    uv run python -m src.cli run --since 12h --max-items 50
    uv run python -m src.cli run --skip-fetch   # 跳过拉取，使用已有数据重跑分析
"""

import argparse
import json
import sys
import os
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# 确保项目根目录在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.rss_fetcher import fetch_all_sources
from src.article_fetcher import enrich_items_with_content
from src.cluster import cluster_items
from src.llm_pipeline import run_llm_pipeline
from src import storage

console = Console()


def _parse_duration(duration_str: str) -> int:
    """解析时间长度字符串，如 '24h', '12h', '48h' → 整数小时"""
    duration_str = duration_str.strip().lower()
    if duration_str.endswith("h"):
        return int(duration_str[:-1])
    elif duration_str.endswith("d"):
        return int(duration_str[:-1]) * 24
    else:
        return int(duration_str)


def cmd_run(args):
    """执行完整流水线"""
    since_hours = _parse_duration(args.since)
    max_items = args.max_items
    skip_fetch = args.skip_fetch
    config_path = args.config

    # 显示运行参数
    console.print(Panel(
        f"📡 数据来源配置: [cyan]{config_path}[/cyan]\n"
        f"⏰ 时间范围: 过去 [cyan]{since_hours}[/cyan] 小时\n"
        f"📊 最大条目数: [cyan]{max_items}[/cyan]\n"
        f"🔄 跳过拉取: [cyan]{'是' if skip_fetch else '否'}[/cyan]\n",
        title="[bold]AI 知识素材引擎[/bold]",
        border_style="blue"
    ))

    start_time = time.time()

    # ======================== 第1步：拉取 RSS ========================
    if skip_fetch:
        console.print("\n[yellow]⏭ 跳过 RSS 拉取，使用已有数据[/yellow]")
        raw_items = storage.load_raw_items()
        if not raw_items:
            console.print("[red]错误：没有找到已有数据，请先不带 --skip-fetch 运行[/red]")
            sys.exit(1)
        console.print(f"[green]加载了 {len(raw_items)} 条已有数据[/green]")
    else:
        raw_items = fetch_all_sources(
            config_path=config_path,
            since_hours=since_hours,
            max_items=max_items
        )
        if not raw_items:
            console.print("[red]❌ 没有获取到任何新闻条目，流程终止[/red]")
            sys.exit(1)

    # ======================== 第2步：抓取正文 ========================
    if not skip_fetch:
        raw_items = enrich_items_with_content(raw_items, max_fetch=min(len(raw_items), 30))

    # ======================== 第3步：保存原始数据 ========================
    added = storage.append_raw_items(raw_items)
    console.print(f"[green]💾 保存原始数据: 新增 {added} 条[/green]")
    # 重新加载最新全量数据
    all_raw_items = storage.load_raw_items()

    # ======================== 第4步：聚类 ========================
    events = cluster_items(raw_items, similarity_threshold=0.78)
    if not events:
        console.print("[red]❌ 聚类后没有事件，流程终止[/red]")
        sys.exit(1)
        
    # 如果用户指定了 max_items 测试，确保最终事件数不超过此限制，以免花费太多时间
    events = events[:max_items]
        
    storage.save_events(events)
    console.print(f"[green]💾 保存事件数据: {len(events)} 个事件[/green]")

    # ======================== 第5步：LLM 分析 ========================
    materials = run_llm_pipeline(
        events=events,
        raw_items=all_raw_items,
        talkability_threshold=5.0
    )

    # ======================== 第6步：导出素材包 ========================
    output = {
        "generated_at": datetime.now().isoformat(),
        "total_events": len(events),
        "total_materials": len(materials),
        "materials": materials
    }
    storage.save_materials(output)

    # ======================== 第7步：执行素材分发打包与图片生成 ========================
    console.print("\n[bold]📦 步骤4/4: 分发素材包与智能生图[/bold]\n")
    export_dir, exported_count = storage.export_material_packages(materials)

    elapsed = time.time() - start_time

    # 显示结果摘要
    console.print("\n")
    console.print(Panel(
        f"⏱ 耗时: [cyan]{elapsed:.1f}[/cyan] 秒\n"
        f"📰 拉取条目: [cyan]{len(raw_items)}[/cyan]\n"
        f"🔗 聚类事件: [cyan]{len(events)}[/cyan]\n"
        f"🎬 生成素材: [cyan]{len(materials)}[/cyan]\n"
        f"📁 独立导出夹: [cyan]{exported_count}[/cyan] 个存入 [yellow]'{export_dir}'[/yellow] 目录\n"
        f"📄 汇总文件: [cyan]data/materials.json[/cyan]",
        title="[bold green]✅ 流水线完成[/bold green]",
        border_style="green"
    ))

    # 显示素材概览表格
    if materials:
        table = Table(title="小红书素材包概览", show_lines=True)
        table.add_column("#", style="dim", width=4)
        table.add_column("核心标题", max_width=60)
        table.add_column("正文摘录", max_width=50)

        for i, m in enumerate(materials):
            xhs = m.get("xiaohongshu", {})
            titles = xhs.get("titles", [])
            title = titles[0] if titles else "—"
            
            content = xhs.get("content", "—")
            cleaned_content = content.replace('\n', ' ')[:45] + "..." if len(content) > 45 else content
            
            row = [str(i + 1), title, cleaned_content]
            table.add_row(*row)

        console.print(table)

    console.print(f"\n[dim]✨ 单独分块打包的精美素材已存于：./{export_dir} 目录 (包含文本与图片)[/dim]\n")
    console.print(f"[dim]📄 汇总完整 JSON 已保存至: data/materials.json[/dim]\n")


def main():
    """命令行主入口"""
    parser = argparse.ArgumentParser(
        description="AI 知识短视频素材引擎 - 从新闻到短视频素材的自动化流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # run 子命令
    run_parser = subparsers.add_parser("run", help="运行完整流水线")
    run_parser.add_argument("--since", default="24h", help="时间范围，如 24h, 12h, 48h (默认: 24h)")
    run_parser.add_argument("--max-items", type=int, default=200, help="最大处理条目数 (默认: 200)")
    run_parser.add_argument("--skip-fetch", action="store_true", help="跳过RSS拉取，使用已有数据")
    run_parser.add_argument("--config", default="sources.yaml", help="数据源配置文件路径 (默认: sources.yaml)")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
