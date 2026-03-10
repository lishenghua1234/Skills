"""
存储模块 - 基于 JSON 文件的简单持久化
负责 data/ 目录下三个核心文件的读写：
  - raw_items.json   原始新闻条目
  - events.json      聚类后的事件
  - materials.json   生成的素材包
"""

import json
import os
from pathlib import Path
from typing import Optional
from src.models import RawItem, Event, Material, MaterialsOutput
from rich.console import Console

console = Console()

# 默认数据目录
DATA_DIR = Path("data")


def _ensure_dir():
    """确保 data 目录存在"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


# ===================== 原始条目 (raw_items) =====================

def load_raw_items() -> list[dict]:
    """从 data/raw_items.json 加载所有原始条目"""
    path = DATA_DIR / "raw_items.json"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_raw_items(items: list[dict]):
    """将全量原始条目写入 data/raw_items.json"""
    _ensure_dir()
    path = DATA_DIR / "raw_items.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def append_raw_items(new_items: list[dict]) -> int:
    """
    追加新的原始条目（自动按 id 去重）。
    返回实际新增的条目数量。
    """
    existing = load_raw_items()
    existing_ids = {item["id"] for item in existing}
    added = 0
    for item in new_items:
        if item["id"] not in existing_ids:
            existing.append(item)
            existing_ids.add(item["id"])
            added += 1
    if added > 0:
        save_raw_items(existing)
    return added


# ===================== 事件 (events) =====================

def load_events() -> list[dict]:
    """从 data/events.json 加载所有事件"""
    path = DATA_DIR / "events.json"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_events(events: list[dict]):
    """将全量事件写入 data/events.json"""
    _ensure_dir()
    path = DATA_DIR / "events.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


# ===================== 素材包 (materials) =====================

def load_materials() -> dict:
    """从 data/materials.json 加载素材包"""
    path = DATA_DIR / "materials.json"
    if not path.exists():
        return {"generated_at": "", "total_events": 0, "total_materials": 0, "materials": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_materials(output: dict):
    """将素材包写入 data/materials.json"""
    _ensure_dir()
    path = DATA_DIR / "materials.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)


# ===================== 分发打包 (export) =====================

def export_material_packages(materials: list[dict]):
    """将生成的素材分发到名为 '素材' 的统一文件夹下，以各自的主题命名子目录，并为其中的视觉建议生图/生成占位符"""
    import re
    from src.image_generator import generate_and_save_image

    base_export_dir = Path("素材")
    base_export_dir.mkdir(parents=True, exist_ok=True)
    
    saved_count = 0
    
    for m in materials:
        # 提取标题
        if "xiaohongshu" in m and m["xiaohongshu"].get("titles"):
            title = m["xiaohongshu"]["titles"][0]
        else:
            title = "未命名素材"
            
        # 清洗非法路径字符及各种阻碍终端执行的全半角标点符号（强化版）
        clean_title = re.sub(r'[\\/*?:"<>|“”‘’！!，。：；,\.\[\]【】\s]', "", title).strip()
        short_title = clean_title[:20] if len(clean_title) > 20 else clean_title
        
        # 为了防止重名或者标题提取得太短被覆盖，加上一段随机/事件ID后缀
        event_id = m.get("event_id", "0000")
        suffix = event_id.split("_")[-1][:4] if "_" in event_id else event_id[:4]
        
        dir_name = f"{short_title}_{suffix}"
        target_dir = base_export_dir / dir_name
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. 保存当前独立的一份 JSON
        json_path = target_dir / "material.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=2)
            
        saved_count += 1
        # 构造一个用于给画图模型奠定基调的主题上下文提示
        core_theme = title
            
        enhanced_context = f"Main Theme/Headline: {core_theme}. "
            
        # 2. 为小红书建议生图 (限制最多只画 2 张，使得总图片数不超过 3)
        if "xiaohongshu" in m:
            xhs_sugs = m["xiaohongshu"].get("visual_suggestions", [])[:2]
            for idx, sug in enumerate(xhs_sugs):
                img_path = target_dir / f"小红书配图_{idx+1}.png"
                console.print(f"  [dim]正在为 小红书建议{idx+1} 生成图片...[/dim]")
                
                combined_prompt = f"{enhanced_context} Visual scene description: {sug}"
                success = generate_and_save_image(combined_prompt, str(img_path), aspect_ratio="3:4")
                if not success:
                    placeholder_path = target_dir / f"小红书配图_{idx+1}_建议.txt"
                    with open(placeholder_path, "w", encoding="utf-8") as f:
                        f.write(f"【图片生成失败或账户未支持Imagen功能，请手动配图】\n\n综合生图提示词：\n{combined_prompt}")
                        
    return base_export_dir, saved_count

