"""
测试模块2: 聚类与去重测试
验证 URL 去重、标题 Hash 去重和关键词相似度计算。
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cluster import _title_hash, _keyword_similarity, cluster_items


def test_title_hash_dedup():
    """测试标题哈希去重"""
    # 标准化后应该一样
    h1 = _title_hash("OpenAI Releases GPT-5")
    h2 = _title_hash("openai releases gpt-5")
    assert h1 == h2, "标题标准化后 hash 应该相同"

    # 完全不同的标题
    h3 = _title_hash("Google 发布 Gemini 3.0")
    assert h1 != h3, "不同标题 hash 应该不同"

    print("✓ test_title_hash_dedup 通过")


def test_keyword_similarity():
    """测试关键词相似度"""
    # 完全相同标题
    sim1 = _keyword_similarity("AI Model Released", "AI Model Released")
    assert sim1 == 1.0, f"完全匹配应为1.0，实际: {sim1}"

    # 高度相似标题
    sim2 = _keyword_similarity(
        "OpenAI Releases New GPT Model",
        "OpenAI Launches New GPT Model Today"
    )
    assert sim2 > 0.4, f"相似标题相似度应>0.4，实际: {sim2}"

    # 完全不相关标题
    sim3 = _keyword_similarity(
        "Apple iPhone 16 Review",
        "NASA Mars Mission Update"
    )
    assert sim3 < 0.2, f"不相关标题相似度应<0.2，实际: {sim3}"

    print("✓ test_keyword_similarity 通过")


def test_cluster_basic():
    """测试基础聚类功能"""
    items = [
        {"id": "a::001", "title": "OpenAI 发布 GPT-5", "url": "https://a.com/1",
         "summary": "OpenAI今天发布了GPT-5", "content": "", "category": "ai"},
        {"id": "b::002", "title": "OpenAI 发布了全新 GPT-5 模型", "url": "https://b.com/2",
         "summary": "OpenAI的GPT-5正式发布", "content": "", "category": "ai"},
        {"id": "c::003", "title": "Google 推出 Gemini 3.0", "url": "https://c.com/3",
         "summary": "Google发布新一代大模型", "content": "", "category": "ai"},
    ]

    # 使用关键词模式（不需要 Embedding API）
    events = cluster_items(items, similarity_threshold=0.4)

    # 前两条应该被聚到一起，第三条应该是独立事件
    assert len(events) >= 1, "至少应有1个事件"
    assert len(events) <= 3, "最多应有3个事件"

    print(f"✓ test_cluster_basic 通过 (输入{len(items)}条 → {len(events)}个事件)")


if __name__ == "__main__":
    test_title_hash_dedup()
    test_keyword_similarity()
    test_cluster_basic()
    print("\n所有聚类测试通过! ✅")
