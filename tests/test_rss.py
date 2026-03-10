"""
测试模块1: RSS 解析测试
验证 RSS 解析逻辑是否能正确标准化条目。
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.rss_fetcher import _make_id, _parse_date, _is_within_hours


def test_make_id():
    """测试条目 ID 生成"""
    id1 = _make_id("source_a", "https://example.com/article1")
    id2 = _make_id("source_a", "https://example.com/article2")
    id3 = _make_id("source_b", "https://example.com/article1")

    # 同源同URL应该生成一样的ID
    assert id1 == _make_id("source_a", "https://example.com/article1")
    # 不同URL应该不同
    assert id1 != id2
    # 不同来源也应该不同
    assert id1 != id3
    print("✓ test_make_id 通过")


def test_parse_date():
    """测试日期解析"""
    # 标准 RFC 822 格式 (RSS 常见)
    result = _parse_date("Wed, 05 Mar 2026 12:00:00 GMT")
    assert result is not None
    assert "2026" in result

    # ISO 格式
    result2 = _parse_date("2026-03-05T12:00:00Z")
    assert result2 is not None

    # 空字符串应返回当前时间
    result3 = _parse_date("")
    assert result3 is not None

    print("✓ test_parse_date 通过")


def test_is_within_hours():
    """测试时间窗口检查"""
    from datetime import datetime, timezone, timedelta

    # 刚刚的时间应该在24小时内
    now = datetime.now(timezone.utc)
    assert _is_within_hours(now.isoformat(), 24) is True

    # 2天前应该在48小时窗口内
    two_days_ago = now - timedelta(hours=47)
    assert _is_within_hours(two_days_ago.isoformat(), 48) is True

    # 3天前不应在24小时窗口内
    three_days_ago = now - timedelta(hours=73)
    assert _is_within_hours(three_days_ago.isoformat(), 24) is False

    print("✓ test_is_within_hours 通过")


if __name__ == "__main__":
    test_make_id()
    test_parse_date()
    test_is_within_hours()
    print("\n所有 RSS 解析测试通过! ✅")
