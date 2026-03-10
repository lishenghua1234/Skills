"""
数据模型定义模块
定义整个流水线中使用的所有数据结构，使用 Pydantic 做校验。
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class RawItem(BaseModel):
    """原始新闻条目 —— 从 RSS 拉取并标准化后的单条记录"""
    id: str = Field(..., description="唯一标识，格式: {source_id}::{url_hash}")
    source_id: str = Field(..., description="来源ID，对应 sources.yaml 中的 id")
    title: str = Field(..., description="新闻标题")
    url: str = Field(..., description="原文链接")
    summary: str = Field(default="", description="RSS 提供的摘要")
    content: str = Field(default="", description="抓取到的正文内容，若失败则为空")
    published: str = Field(default="", description="发布时间 ISO 格式字符串")
    fetched_at: str = Field(default_factory=lambda: datetime.now().isoformat(), description="抓取时间")
    category: str = Field(default="", description="来源分类")


class Event(BaseModel):
    """聚类后的事件 —— 由一条或多条报道合并而成"""
    id: str = Field(..., description="事件唯一ID")
    title: str = Field(..., description="事件核心标题")
    summary: str = Field(default="", description="事件综合摘要")
    article_ids: list[str] = Field(default_factory=list, description="关联的 RawItem ID 列表")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    talkability_score: float = Field(default=0.0, description="可讲性评分 0-10")
    category: str = Field(default="", description="事件分类")


class XiaohongshuMaterial(BaseModel):
    """小红书图文素材包"""
    titles: list[str] = Field(..., description="3-5 个具有网感、吸引眼球的标题候选")
    content: str = Field(..., description="多段落、带Emoji、包含干货感和分享欲的正文")
    visual_suggestions: list[str] = Field(default_factory=list, description="多张图片/图文轮播的画面文案设计建议")
    tags: list[str] = Field(default_factory=list, description="相关话题标签，如 #AI #人工智能 等")


class Material(BaseModel):
    """素材包 —— 围绕小红书平台封装的数据"""
    event_id: str = Field(..., description="关联的事件ID")
    xiaohongshu: XiaohongshuMaterial = Field(..., description="小红书图文素材")
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class MaterialsOutput(BaseModel):
    """最终输出的素材包集合"""
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    total_events: int = Field(default=0)
    total_materials: int = Field(default=0)
    materials: list[Material] = Field(default_factory=list)
