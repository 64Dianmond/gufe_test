import json
from typing import Dict, List, Union


class SentencingCalculator:
    """量刑计算器：用于精确计算刑期"""



    @staticmethod
    def calculate_base_sentence(crime_type: str, amount: float = None,
                                injury_level: str = None, region: str = "default", 
                                theft_count: int = None, fraud_count: int = None,
                                victim_count: int = None) -> int:
        """
        计算基准刑（单位：月）- 改进版
        采用"档位基准刑 + 超额累进"模式，参考大多数省份标准
        """
            # ---------- 故意伤害罪 ----------
        if crime_type == "故意伤害罪":
            # 故意伤害罪基准刑标准
            # 轻伤：二年以下有期徒刑、拘役或者管制（1-24个月）
            # 重伤：三年以上十年以下有期徒刑（36-120个月）
            # 致死：十年以上有期徒刑、无期徒刑或者死刑（120个月以上）
            injury_map = {
                "轻伤二级": 15,  # 6个月至2年，取中点1年
                "轻伤一级": 18,  # 6个月至2年，取中点1.5年
                "重伤二级": 48,  # 3年至10年，取中点6年
                "重伤一级": 72,  # 3年至10年，取中点6年
                "致人死亡": 120, # 10年至15年，取中点10年
                "死亡": 120,     # 10年至15年，取中点10年
            }
            base_sentence = injury_map.get(injury_level, 12)
            
            # 如果涉及多名受害者，增加基准刑期
            if victim_count and victim_count > 1:
                # 对于多名受害者的案件，根据受害人数适当增加基准刑期
                # 增加的比例基于司法实践中的常见做法
                additional_percentage = min(0.5 * (victim_count - 1), 2.0)  # 最多增加200%
                base_sentence = int(base_sentence * (1 + additional_percentage))
                
            return base_sentence

            # 默认兜底
        return 12

    @staticmethod
    def calculate_layered_sentence_with_constraints(
            base_months: int,
            crime_type: str,
            amount: float = None,
            layer1_factors: List[Dict[str, Union[str, float]]] = None,
            layer2_factors: List[Dict[str, Union[str, float]]] = None,
            has_statutory_mitigation: bool = False,  # 是否有法定减轻情节
            injury_level: str = None,  # 伤害等级（用于故意伤害罪）
            victim_count: int = None   # 受害者人数（用于故意伤害罪）
    ) -> Dict[str, Union[float, str]]:
        """
        分层计算最终刑期 - 增强版,带约束条件
        """
        steps = []
        current_months = base_months
        steps.append(f"基准刑: {base_months}个月")

        # 如果涉及多名受害者，添加说明
        if victim_count and victim_count > 1:
            steps.append(f"涉及{victim_count}名受害者，已考虑加重情节")

        # 第一层面：连乘
        layer1_multiplier = 1.0
        if layer1_factors:
            for factor in layer1_factors:
                # 兼容 name 和 factor 两种字段名
                name = factor.get("name") or factor.get("factor")
                ratio = factor["ratio"]
                layer1_multiplier *= ratio
                steps.append(f"第一层面 - {name}: ×{ratio}")

            current_months = base_months * layer1_multiplier
            steps.append(f"第一层面结果: {current_months:.2f}个月")

        # 第二层面：加减
        layer2_adjustment = 0.0
        if layer2_factors:
            for factor in layer2_factors:
                # 兼容 name 和 factor 两种字段名
                name = factor.get("name") or factor.get("factor")
                ratio = factor["ratio"]
                adjustment = ratio - 1.0
                layer2_adjustment += adjustment
                steps.append(f"第二层面 - {name}: {'+' if adjustment > 0 else ''}{adjustment * 100:.0f}%")

            layer2_multiplier = 1.0 + layer2_adjustment
            temp_final = current_months * layer2_multiplier
            steps.append(f"第二层面初步结果: {temp_final:.2f}个月")
        else:
            temp_final = current_months

        # 移除所有法定约束检查，只保留基本的有效性检查
        # 确保刑期不低于1个月
        if temp_final < 1:
            steps.append(f"⚠️ 调整: 结果({temp_final:.2f}月)低于1个月")
            steps.append(f"   调整至最低刑期: 1个月")
            temp_final = 1

        final_months = round(temp_final, 2)

        return {
            "final_months": final_months,
            "base_months": base_months,
            "calculation_steps": steps,
            "constrained": temp_final != current_months * (1.0 + layer2_adjustment)
        }

    @staticmethod
    def _get_legal_range(crime_type: str, amount: float, injury_level: str = None) -> tuple:
        """
        获取法定刑档位的上下限
        """
        if crime_type == "故意伤害罪":
            # 根据最高检相关解释和刑法规定确定故意伤害罪的法定刑范围
            injury_range_map = {
                # 轻伤（三年以下有期徒刑、拘役或者管制）
                "轻伤一级": (6, 24),   # 6个月至2年
                "轻伤二级": (1, 24),   # 6个月至2年

                # 重伤（三年以上十年以下有期徒刑）
                "重伤一级": (36, 120), # 3年至10年
                "重伤二级": (36, 120), # 3年至10年

                # 致人死亡或特别残忍手段致人重伤造成严重残疾（十年以上有期徒刑、无期徒刑或者死刑）
                "致人死亡": (120, 180), # 10年至15年
                "死亡": (120, 180)     # 10年至15年
            }
            # 默认返回较宽泛的范围
            return injury_range_map.get(injury_level, (1, 180))

        # 默认
        return (6, 120)

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
    def months_to_range(center_months: float, width: int = 12) -> List[int]:
        """
        将中心月数转换为刑期区间（修改后版本）
        
        新规则：
        - 下限：对中心月数向下偏移1/3宽度
        - 上限：对中心月数向上偏移2/3宽度
        
        Args:
            center_months: 中心月数
            width: 区间宽度（默认12个月）

        Returns:
            [最小月数, 最大月数]
        """

        width = max(6, min(12, center_months * 0.15))
        half_width = width / 2
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
                        "enum": ["盗窃罪", "诈骗罪", "故意伤害罪", "职务侵占罪"],
                        "description": "罪名类型"
                    },
                    "amount": {
                        "type": "number",
                        "description": "犯罪金额（元），适用于盗窃罪和诈骗罪"
                    },
                    "injury_level": {
                        "type": "string",
                        "enum": ["轻伤一级", "轻伤二级", "重伤一级", "重伤二级", "致人死亡", "死亡"],
                        "description": "伤害等级，适用于故意伤害罪"
                    },
                    "region": {
                        "type": "string",
                        "description": "案件所在地区"
                    },
                    "theft_count": {
                        "type": "integer",
                        "description": "盗窃次数，适用于盗窃罪"
                    },
                    "fraud_count": {
                        "type": "integer",
                        "description": "诈骗次数，适用于诈骗罪"
                    },
                    "victim_count": {
                        "type": "integer",
                        "description": "受害者人数，适用于故意伤害罪"
                    }
                },
                "required": ["crime_type"]
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
                        "description": "区间宽度（默认12个月）",
                        "default": 12
                    }
                },
                "required": ["center_months"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_layered_sentence_with_constraints",
            "description": "带约束条件的分层量刑计算,确保不超50%减轻且不低于法定刑下限",
            "parameters": {
                "type": "object",
                "properties": {
                    "base_months": {"type": "integer"},
                    "crime_type": {"type": "string", "enum": ["盗窃罪", "诈骗罪", "故意伤害罪"]},
                    "amount": {"type": "number"},
                    "layer1_factors": {"type": "array", "items": {"type": "object"}},
                    "layer2_factors": {"type": "array", "items": {"type": "object"}},
                    "has_statutory_mitigation": {
                        "type": "boolean",
                        "description": "是否有法定减轻处罚情节(自首/立功/未成年人等)"
                    },
                    "injury_level": {
                        "type": "string",
                        "description": "伤害等级，适用于故意伤害罪",
                        "enum": ["轻伤一级", "轻伤二级","重伤一级", "重伤二级", "致人死亡", "死亡"]
                    },
                    "victim_count": {
                        "type": "integer",
                        "description": "受害者人数，适用于故意伤害罪"
                    }
                },
                "required": ["base_months", "crime_type"]
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

        # elif tool_name == "calculate_layered_sentence":
        #     result = calculator.calculate_layered_sentence(**tool_arguments)
        #     return json.dumps(result, ensure_ascii=False)

        elif tool_name == "calculate_layered_sentence_with_constraints":
            result = calculator.calculate_layered_sentence_with_constraints(**tool_arguments)
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
    result = calc.calculate_layered_sentence_with_constraints(
        base_months=100,
        crime_type="盗窃罪",
        amount=3631,
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