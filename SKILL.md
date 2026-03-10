---
name: SearchNews XHS Material Generator
description: 一键从全球 AI RSS 源获取新闻并自动将其转化为包含标题、文案和图片的完美小红书图文轮播素材包。
version: 1.0.0
---

# SearchNews XHS Material Generator 技能指南

这是一个专为全自动抓取、分析并生成小红书专属科技领域素材包而构建的技能体系。它可以与小红书自动发布引擎（如 OpenClaw）无缝衔接，实现从“灵感获取”到“内容生成”乃至“自动分发”的无人执守闭环。

## ⚙️ 技能功能
1. 监听 `sources.yaml` 中配置的多个顶尖 AI 科技源。
2. 抓取文章并通过强大的大模型链路和容错轮换池（Gemini / Minimax 等）进行去重和“小红书专有化”改造（提炼网感、添加 Emoji，编写引人入胜的标题与互动段落）。
3. 调用智能图片接口为每次生成的素材生成 1~2 张尺寸适配（3:4）的配图。
4. 将事件及素材结构化落盘输出为独立的资产文件夹，供其他发布工具（OpenClaw）提取并使用。

## 🚀 外部调用方式

本技能的唯一入口为项目的 `src/cli.py`：

```bash
# 进入项目目录
cd D:\WorFlow\AntiGravity\SearchNews

# 运行技能获取过去 12 小时的最新事件并最多生成 5 个新闻素材包装
uv run python -m src.cli run --since 12h --max-items 5
```

## 📦 产物说明与发布对接 (与 OpenClaw 集成)

当命令行执行完毕后，所有提取并成功生成的素材都会被统一存放在 `D:\WorFlow\AntiGravity\SearchNews\素材\` 目录下。
每一个子文件夹（如 `实时看战争？AI已经_9cc4`）代表一篇可以随时在小红书被发布的内容。

**文件层级结构及对接方式**：
```text
/素材/[简短主标题]_[事件ID后缀]/
├── material.json        # 核心数据文件。OpenClaw 应该读取此文件进行发布
├── 小红书配图_1.png     # （首图）OpenClaw 需将其设为小红书笔记的主视觉封面
├── 小红书配图_2.png     # （内页图）轮播图的第二张
```

### ➡️ 给 OpenClaw 开发者的接入建议协议：
当 OpenClaw 获取到发布指令时，可以按照以下流处理：
1. 监控或遍历 `/素材/*` 目录。
2. 进入某事件目录，读取 `material.json`。
3. 提取 `json` 中的 `xiaohongshu.content` 字段作为发布的正文；提取 `xiaohongshu.titles` 的第一项作为小红书的标题。
4. 提取该文件夹下所有的 `*.png`，按照文件名自然序提取数组（必须先推入 `小红书配图_1.png`）。
5. 传至 OpenClaw 完成发帖。
6. 打上标记（可以将该目录重命名，或存入数据库）以避免重复发布！

## 🔧 原料配置要求
运行本技能前，须确保项目的 `sources.yaml` 文件中已经为容灾密钥池 `api_keys.gemini` 分配了有效的阵列值。

> Note: 如果大模型能力欠费将自动切换下一把，若全部耗尽流水线会强行终止但保留部分已生成的有效包。
