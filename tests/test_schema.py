"""
测试模块3: JSON Schema 校验测试
验证输出的 materials.json 是否符合预定义的 Pydantic Schema。
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import Material, MaterialExplanation, MaterialsOutput


def test_material_schema():
    """测试单个素材包的 Schema 合法性"""
    # 模拟一个合法的素材包
    material_data = {
        "event_id": "evt_abc12345",
        "title_candidates": ["AI 又要革命了？", "GPT-5 来了，你准备好了吗"],
        "hook_3s": "你知道吗？OpenAI 刚发布的新模型，能力相当于一个实习生了",
        "key_points": ["GPT-5 推理能力大幅提升", "支持多模态", "价格下降50%"],
        "explanations": {
            "general": "就像手机从按键升级到触屏一样，AI也迎来了一次大升级",
            "tech_enthusiast": "新模型在 MMLU 上达到了 95%，推理任务的表现显著提升",
            "professional": "GPT-5 采用了 MoE 架构，70B 活跃参数，推理 FLOPS 降低40%"
        },
        "common_misconceptions": ["AI 要取代所有工作", "这和之前的版本没区别"],
        "visual_suggestions": ["展示性能对比柱状图", "录屏演示新功能"],
        "recommended_duration": 60,
        "script_outline": "开头抛出悬念 → 展示核心能力 → 解读影响 → 号召关注"
    }

    # Pydantic 校验应该通过
    material = Material(**material_data)
    assert material.event_id == "evt_abc12345"
    assert len(material.title_candidates) == 2
    assert material.recommended_duration == 60
    assert isinstance(material.explanations, MaterialExplanation)

    print("✓ test_material_schema 通过")


def test_materials_output_schema():
    """测试完整输出结构的 Schema 合法性"""
    output_data = {
        "generated_at": "2026-03-07T00:30:00",
        "total_events": 3,
        "total_materials": 2,
        "materials": [
            {
                "event_id": "evt_001",
                "title_candidates": ["标题A"],
                "hook_3s": "hook内容",
                "key_points": ["要点1"],
                "explanations": {
                    "general": "普通解释",
                    "tech_enthusiast": "技术解释",
                    "professional": "专业解释"
                },
                "common_misconceptions": [],
                "visual_suggestions": [],
                "recommended_duration": 30,
                "script_outline": "大纲"
            }
        ]
    }

    output = MaterialsOutput(**output_data)
    assert output.total_events == 3
    assert output.total_materials == 2
    assert len(output.materials) == 1

    print("✓ test_materials_output_schema 通过")


def test_invalid_material_rejected():
    """测试不合法的素材数据是否被拒绝"""
    # 缺少必填字段
    incomplete_data = {
        "event_id": "evt_001",
        # 缺少 title_candidates, hook_3s 等
    }

    try:
        Material(**incomplete_data)
        assert False, "应该抛出校验异常"
    except Exception:
        pass  # 预期行为

    print("✓ test_invalid_material_rejected 通过")


if __name__ == "__main__":
    test_material_schema()
    test_materials_output_schema()
    test_invalid_material_rejected()
    print("\n所有 Schema 校验测试通过! ✅")
