"""
刑期计算器工具
提供精确的量刑计算功能，避免LLM直接进行数值计算
"""

import json
from typing import Dict, List, Union


class SentencingCalculator:
    """量刑计算器：用于精确计算刑期"""

    @staticmethod
    def calculate_base_sentence(crime_type: str, amount: float = None,
                                injury_level: str = None) -> int:
        """
        计算基准刑（单位：月）

        Args:
            crime_type: 罪名类型
            amount: 犯罪金额（元）
            injury_level: 伤害等级（轻伤/重伤）

        Returns:
            基准刑月数
        """
        if crime_type == "盗窃罪":
            if amount and amount < 3000:
                return 6  # 6个月以下或者拘役
            elif amount and amount < 30000:
                return 12  # 3年以下
            elif amount and amount < 300000:
                return 48  # 3-10年
            else:
                return 120  # 10年以上

        elif crime_type == "诈骗罪":
            if amount and amount < 3000:
                return 0  # 不构成犯罪
            elif amount and amount < 30000:
                return 12  # 3年以下
            elif amount and amount < 500000:
                return 48  # 3-10年
            else:
                return 120  # 10年以上

        elif crime_type == "故意伤害罪":
            if injury_level == "轻微伤":
                return 0  # 不构成犯罪
            elif injury_level == "轻伤":
                return 12  # 3年以下
            elif injury_level == "重伤":
                return 48  # 3-10年
            elif injury_level == "致人死亡":
                return 120  # 10年以上
            else:
                return 12

        return 12  # 默认值

    @staticmethod
    def apply_factor(base_months: int, factor_name: str, factor_ratio: float) -> float:
        """
        应用单个情节调节因子

        Args:
            base_months: 基准月数
            factor_name: 情节名称
            factor_ratio: 调节比例（如0.5表示减少50%，1.3表示增加30%）

        Returns:
            调节后的月数
        """
        result = base_months * factor_ratio
        return round(result, 2)

    @staticmethod
    def calculate_layered_sentence(
            base_months: int,
            layer1_factors: List[Dict[str, Union[str, float]]],
            layer2_factors: List[Dict[str, Union[str, float]]]
    ) -> Dict[str, Union[float, str]]:
        """
        分层计算最终刑期

        Args:
            base_months: 基准刑（月）
            layer1_factors: 第一层面情节列表 [{"name": "未成年人", "ratio": 0.5}, ...]
            layer2_factors: 第二层面情节列表 [{"name": "累犯", "ratio": 0.3}, ...]

        Returns:
            计算结果字典，包含最终月数和计算步骤
        """
        steps = []
        current_months = base_months
        steps.append(f"基准刑: {base_months}个月")

        # 第一层面：连乘
        layer1_multiplier = 1.0
        for factor in layer1_factors:
            name = factor["name"]
            ratio = factor["ratio"]
            layer1_multiplier *= ratio
            steps.append(f"第一层面 - {name}: ×{ratio}")

        if layer1_factors:
            current_months = base_months * layer1_multiplier
            steps.append(f"第一层面计算结果: {base_months} × {layer1_multiplier} = {current_months:.2f}个月")

        # 第二层面：加减
        layer2_adjustment = 0.0
        for factor in layer2_factors:
            name = factor["name"]
            ratio = factor["ratio"]
            # ratio为正数表示从重（如1.3表示+30%），为负数表示从轻（如0.9表示-10%）
            adjustment = ratio - 1.0  # 转换为调节比例
            layer2_adjustment += adjustment
            steps.append(f"第二层面 - {name}: {'+' if adjustment > 0 else ''}{adjustment * 100:.0f}%")

        if layer2_factors:
            layer2_multiplier = 1.0 + layer2_adjustment
            final_months = current_months * layer2_multiplier
            steps.append(f"第二层面计算结果: {current_months:.2f} × {layer2_multiplier} = {final_months:.2f}个月")
        else:
            final_months = current_months

        return {
            "final_months": round(final_months, 2),
            "calculation_steps": steps,
            "formula": f"{base_months} × L1({layer1_multiplier}) × L2({1.0 + layer2_adjustment})"
        }

    @staticmethod
    def calculate_simple_adjustment(base_months: int, adjustment_percent: float) -> int:
        """
        简单的百分比调节计算

        Args:
            base_months: 基准月数
            adjustment_percent: 调节百分比（如30表示增加30%，-10表示减少10%）

        Returns:
            调节后的月数（整数）
        """
        multiplier = 1.0 + (adjustment_percent / 100.0)
        result = base_months * multiplier
        return round(result)

    @staticmethod
    def months_to_range(center_months: float, width: int = 4) -> List[int]:
        """
        将中心月数转换为刑期区间

        Args:
            center_months: 中心月数
            width: 区间宽度（默认4个月）

        Returns:
            [最小月数, 最大月数]
        """
        half_width = width // 2
        # 确保不低于1个月，同时正确处理浮点数
        min_months = max(1, round(center_months - half_width))
        max_months = max(1, round(center_months + half_width))
        return [min_months, max_months]

    @staticmethod
    def validate_legal_range(months: int, min_legal: int, max_legal: int) -> int:
        """
        验证并调整刑期是否在法定范围内

        Args:
            months: 计算出的月数
            min_legal: 法定最低月数
            max_legal: 法定最高月数

        Returns:
            调整后的合法月数
        """
        if months < min_legal:
            return min_legal
        elif months > max_legal:
            return max_legal
        return months


# 工具函数定义（OpenAI Function Calling格式）
SENTENCING_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calculate_base_sentence",
            "description": "根据罪名和犯罪事实计算基准刑",
            "parameters": {
                "type": "object",
                "properties": {
                    "crime_type": {
                        "type": "string",
                        "enum": ["盗窃罪", "诈骗罪", "故意伤害罪"],
                        "description": "罪名类型"
                    },
                    "amount": {
                        "type": "number",
                        "description": "犯罪金额（元），适用于盗窃罪和诈骗罪"
                    },
                    "injury_level": {
                        "type": "string",
                        "enum": ["轻伤", "重伤", "死亡"],
                        "description": "伤害等级，适用于故意伤害罪"
                    }
                },
                "required": ["crime_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_layered_sentence",
            "description": "根据分层量刑规则精确计算最终刑期。第一层面情节（未成年人、从犯等）使用连乘，第二层面情节（累犯、自首等）使用加减",
            "parameters": {
                "type": "object",
                "properties": {
                    "base_months": {
                        "type": "integer",
                        "description": "基准刑月数"
                    },
                    "layer1_factors": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "情节名称，如'未成年人'、'从犯'"
                                },
                                "ratio": {
                                    "type": "number",
                                    "description": "调节比例（乘数），如0.5表示减半，0.8表示减少20%"
                                }
                            },
                            "required": ["name", "ratio"]
                        },
                        "description": "第一层面情节列表（连乘因子）"
                    },
                    "layer2_factors": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "情节名称，如'累犯'、'自首'、'坦白'"
                                },
                                "ratio": {
                                    "type": "number",
                                    "description": "调节比例（乘数），如1.3表示增加30%，0.9表示减少10%"
                                }
                            },
                            "required": ["name", "ratio"]
                        },
                        "description": "第二层面情节列表（加减因子）"
                    }
                },
                "required": ["base_months", "layer1_factors", "layer2_factors"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "months_to_range",
            "description": "将中心月数转换为刑期区间",
            "parameters": {
                "type": "object",
                "properties": {
                    "center_months": {
                        "type": "number",
                        "description": "中心月数"
                    },
                    "width": {
                        "type": "integer",
                        "description": "区间宽度（默认4个月）",
                        "default": 4
                    }
                },
                "required": ["center_months"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "validate_legal_range",
            "description": "验证并调整刑期是否在法定范围内",
            "parameters": {
                "type": "object",
                "properties": {
                    "months": {
                        "type": "integer",
                        "description": "计算出的月数"
                    },
                    "min_legal": {
                        "type": "integer",
                        "description": "法定最低月数"
                    },
                    "max_legal": {
                        "type": "integer",
                        "description": "法定最高月数"
                    }
                },
                "required": ["months", "min_legal", "max_legal"]
            }
        }
    }
]


def execute_tool_call(tool_name: str, tool_arguments: dict) -> str:
    """
    执行工具调用

    Args:
        tool_name: 工具名称
        tool_arguments: 工具参数

    Returns:
        执行结果的JSON字符串
    """
    calculator = SentencingCalculator()

    try:
        if tool_name == "calculate_base_sentence":
            result = calculator.calculate_base_sentence(**tool_arguments)
            return json.dumps({"base_months": result}, ensure_ascii=False)

        elif tool_name == "calculate_layered_sentence":
            result = calculator.calculate_layered_sentence(**tool_arguments)
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "months_to_range":
            result = calculator.months_to_range(**tool_arguments)
            return json.dumps({"range": result}, ensure_ascii=False)

        elif tool_name == "validate_legal_range":
            result = calculator.validate_legal_range(**tool_arguments)
            return json.dumps({"validated_months": result}, ensure_ascii=False)

        else:
            return json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


if __name__ == "__main__":
    # 测试示例
    calc = SentencingCalculator()

    # 示例1：计算基准刑
    print("=== 示例1：计算基准刑 ===")
    base = calc.calculate_base_sentence("盗窃罪", amount=3631)
    print(f"基准刑: {base}个月\n")

    # 示例2：分层计算
    print("=== 示例2：分层计算 ===")
    result = calc.calculate_layered_sentence(
        base_months=100,
        layer1_factors=[
            {"name": "未成年人", "ratio": 0.5},
            {"name": "从犯", "ratio": 0.8}
        ],
        layer2_factors=[
            {"name": "累犯", "ratio": 1.3},
            {"name": "自首", "ratio": 0.9}
        ]
    )
    print(f"最终刑期: {result['final_months']}个月")
    print("计算步骤:")
    for step in result['calculation_steps']:
        print(f"  {step}")
    print()

    # 示例3：转换为区间
    print("=== 示例3：转换为区间 ===")
    range_result = calc.months_to_range(48, width=4)
    print(f"刑期区间: {range_result}\n")
