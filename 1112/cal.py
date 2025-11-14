"""
刑期计算器工具
提供精确的量刑计算功能，避免LLM直接进行数值计算
"""

import json
from typing import Dict, List, Union


class SentencingCalculator:
    """量刑计算器：用于精确计算刑期"""

    # 第一层面情节固定系数表（连乘）
    LAYER1_FACTORS = {
        "未成年人（16-18岁）": {"name": "未成年人（16-18岁）", "ratio": 0.70},
        "未成年人（14-16岁）": {"name": "未成年人（14-16岁）", "ratio": 0.50},
        "从犯（作用较小）": {"name": "从犯（作用较小）", "ratio": 0.60},
        "从犯（一般）": {"name": "从犯（一般）", "ratio": 0.70},
        "胁从犯": {"name": "胁从犯", "ratio": 0.40},
        "犯罪预备": {"name": "犯罪预备", "ratio": 0.40},
        "犯罪中止（自动有效）": {"name": "犯罪中止（自动有效）", "ratio": 0.30},
        "犯罪中止（一般）": {"name": "犯罪中止（一般）", "ratio": 0.40},
        "犯罪未遂（意志以外）": {"name": "犯罪未遂（意志以外）", "ratio": 0.70},
        "犯罪未遂（能力不足）": {"name": "犯罪未遂（能力不足）", "ratio": 0.60},
        "限制刑事责任能力": {"name": "限制刑事责任能力", "ratio": 0.60},
        "又聋又哑/盲人": {"name": "又聋又哑/盲人", "ratio": 0.70},
        "防卫过当": {"name": "防卫过当", "ratio": 0.50},
    }

    # 第二层面情节固定调节表（加减）
    LAYER2_FACTORS = {
        "累犯": {"name": "累犯", "adjustment_pct": 25},
        "自首（主动投案）": {"name": "自首（主动投案）", "adjustment_pct": -35},
        "自首（抓获后）": {"name": "自首（抓获后）", "adjustment_pct": -25},
        "坦白": {"name": "坦白", "adjustment_pct": -15},
        "认罪认罚（具结书）": {"name": "认罪认罚（具结书）", "adjustment_pct": -20},
        "认罪认罚（口头）": {"name": "认罪认罚（口头）", "adjustment_pct": -15},
        "一般立功": {"name": "一般立功", "adjustment_pct": -15},
        "重大立功": {"name": "重大立功", "adjustment_pct": -30},
        "退赃退赔（全部）": {"name": "退赃退赔（全部）", "adjustment_pct": -25},
        "退赃退赔（部分）": {"name": "退赃退赔（部分）", "adjustment_pct": -15},
        "取得谅解": {"name": "取得谅解", "adjustment_pct": -20},
        "刑事和解": {"name": "刑事和解", "adjustment_pct": -35},
        "有前科（同类）": {"name": "有前科（同类）", "adjustment_pct": 20},
        "有前科（其他）": {"name": "有前科（其他）", "adjustment_pct": 15},
        "多次犯罪（3次+）": {"name": "多次犯罪（3次+）", "adjustment_pct": 25},
        "多次犯罪（2次）": {"name": "多次犯罪（2次）", "adjustment_pct": 15},
        "造成严重后果": {"name": "造成严重后果", "adjustment_pct": 35},
    }

    @staticmethod
    def match_layer1_factor(description: str) -> Dict:
        """
        根据描述匹配第一层面情节和系数
        """
        # 简单的关键词匹配逻辑，实际应用中可能需要更复杂的NLP处理
        for key, factor in SentencingCalculator.LAYER1_FACTORS.items():
            if key in description:
                return {
                    "name": factor["name"],
                    "ratio": factor["ratio"],
                    "match_reason": f"匹配到'{key}'"
                }
        
        # 默认返回
        return {
            "name": "一般情节",
            "ratio": 1.0,
            "match_reason": "未匹配到具体情节，使用默认值"
        }

    @staticmethod
    def match_layer2_factor(description: str) -> Dict:
        """
        根据描述匹配第二层面情节和调节值
        """
        # 简单的关键词匹配逻辑，实际应用中可能需要更复杂的NLP处理
        for key, factor in SentencingCalculator.LAYER2_FACTORS.items():
            if key in description:
                return {
                    "name": factor["name"],
                    "adjustment_pct": factor["adjustment_pct"],
                    "match_reason": f"匹配到'{key}'"
                }
        
        # 默认返回
        return {
            "name": "一般情节",
            "adjustment_pct": 0,
            "match_reason": "未匹配到具体情节，使用默认值"
        }

    @staticmethod
    def calculate_base_sentence(crime_type: str, amount: float = None,
                                injury_level: str = None, circumstances: dict = None) -> int:
        """
        计算基准刑（单位：月）

        Args:
            crime_type: 罪名类型
            amount: 犯罪金额（元）
            injury_level: 伤害等级（轻伤/重伤）
            circumstances: 其他犯罪情节

        Returns:
            基准刑月数
        """
        # 使用新的详细计算方法
        if crime_type == "盗窃罪" and amount is not None:
            return SentencingCalculator.calculate_theft_base_sentence(amount, circumstances)
        elif crime_type == "诈骗罪" and amount is not None:
            return SentencingCalculator.calculate_fraud_base_sentence(amount, circumstances)
        elif crime_type == "故意伤害罪" and injury_level:
            return SentencingCalculator.calculate_assault_base_sentence(injury_level, circumstances)
        
        # 默认返回值
        return 12

    def calculate_theft_base_sentence(amount: float, circumstances: dict = None) -> int:
        """
        盗窃罪基准刑计算

        Args:
            amount: 盗窃金额（元）
            circumstances: 其他情节 {
                "multiple_thefts": bool,  # 多次盗窃
                "burglary": bool,  # 入户盗窃
                "pickpocketing": bool,  # 携带凶器盗窃
                "public_places": bool  # 在公共场所扒窃
            }
        """
        circumstances = circumstances or {}

        # 基础金额分档（参考各地司法解释，以江苏为例）
        if amount < 2000:
            return 0  # 不构成犯罪或治安处罚

        elif 2000 <= amount < 5000:  # 数额较大（下限）
            base = 6  # 6个月
            # 多次盗窃等情节可能入罪
            if any(circumstances.values()):
                base = 8

        elif 5000 <= amount < 10000:  # 数额较大（中段）
            base = 12  # 1年

        elif 10000 <= amount < 30000:  # 数额较大（上段）
            base = 18  # 1年6个月

        elif 30000 <= amount < 60000:  # 数额巨大（下限）
            base = 36  # 3年

        elif 60000 <= amount < 100000:  # 数额巨大（中段）
            base = 48  # 4年

        elif 100000 <= amount < 300000:  # 数额巨大（上段）
            base = 72  # 6年

        elif 300000 <= amount < 500000:  # 数额特别巨大（下限）
            base = 96  # 8年

        elif 500000 <= amount < 1000000:  # 数额特别巨大（中段）
            base = 120  # 10年

        elif 1000000 <= amount < 3000000:  # 数额特别巨大（上段）
            base = 144  # 12年

        else:  # 3000000以上
            base = 168  # 14年（接近15年上限）

        # 特殊情节调整
        if circumstances.get("burglary"):  # 入户盗窃
            base = int(base * 1.2)
        if circumstances.get("pickpocketing"):  # 携带凶器盗窃
            base = int(base * 1.15)

        return base

    def calculate_fraud_base_sentence(amount: float, circumstances: dict = None) -> int:
        """
        诈骗罪基准刑计算

        Args:
            amount: 诈骗金额（元）
            circumstances: 其他情节 {
                "telecom_fraud": bool,  # 电信网络诈骗
                "vulnerable_victims": bool,  # 诈骗残疾人/老年人
                "disaster_fraud": bool,  # 诈骗救灾款物
                "medical_fraud": bool  # 医保诈骗
            }
        """
        circumstances = circumstances or {}

        # 诈骗罪起刑点通常高于盗窃罪
        if amount < 3000:
            return 6 # 不构成犯罪

        elif 3000 <= amount < 6000:  # 数额较大（下限）
            base = 6  # 6个月

        elif 6000 <= amount < 10000:  # 数额较大（中下段）
            base = 10  # 10个月

        elif 10000 <= amount < 30000:  # 数额较大（中段）
            base = 18  # 1年6个月

        elif 30000 <= amount < 50000:  # 数额较大（上段）
            base = 24  # 2年

        elif 50000 <= amount < 100000:  # 数额巨大（下限）
            base = 42  # 3年6个月

        elif 100000 <= amount < 300000:  # 数额巨大（中段）
            base = 60  # 5年

        elif 300000 <= amount < 500000:  # 数额巨大（上段）
            base = 84  # 7年

        elif 500000 <= amount < 1000000:  # 数额特别巨大（下限）
            base = 108  # 9年

        elif 1000000 <= amount < 3000000:  # 数额特别巨大（中段）
            base = 132  # 11年

        else:  # 3000000以上
            base = 156  # 13年（接近无期的门槛）

        # 电信网络诈骗从严处罚
        if circumstances.get("telecom_fraud"):
            base = int(base * 1.3)

        # 诈骗弱势群体
        if circumstances.get("vulnerable_victims"):
            base = int(base * 1.2)

        # 诈骗救灾款物
        if circumstances.get("disaster_fraud"):
            base = int(base * 1.4)

        return base

    def calculate_assault_base_sentence(injury_level: str, circumstances: dict = None) -> int:
        """
        故意伤害罪基准刑计算

        Args:
            injury_level: 伤害等级（"轻伤一级"/"轻伤二级"/"重伤一级"/"重伤二级"/"死亡"）
            circumstances: 其他情节 {
                "weapon_used": bool,  # 使用凶器
                "multiple_victims": int,  # 被害人人数
                "disability_caused": str,  # 造成残疾等级（"一级"~"十级"）
                "premeditated": bool  # 预谋
            }
        """
        circumstances = circumstances or {}

        # 按伤情等级分档
        if injury_level == "轻伤二级":
            base = 6  # 6个月-1年

        elif injury_level == "轻伤一级":
            base = 12  # 1年-1年6个月

        elif injury_level == "重伤二级":
            # 重伤二级细分（按伤残等级）
            disability = circumstances.get("disability_caused", "十级")
            if disability in ["十级", "九级"]:
                base = 36  # 3年
            elif disability in ["八级", "七级"]:
                base = 48  # 4年
            elif disability in ["六级", "五级"]:
                base = 60  # 5年
            else:
                base = 72  # 6年

        elif injury_level == "重伤一级":
            # 重伤一级（接近死亡）
            disability = circumstances.get("disability_caused", "四级")
            if disability in ["四级", "三级"]:
                base = 84  # 7年
            elif disability in ["二级"]:
                base = 96  # 8年
            elif disability in ["一级"]:
                base = 108  # 9年（植物人等）
            else:
                base = 72  # 默认6年

        elif injury_level == "死亡":
            # 故意伤害致死（非故意杀人）
            if circumstances.get("premeditated"):
                base = 144  # 12年（接近故意杀人）
            else:
                base = 120  # 10年（一般情况）

        else:
            return 0  # 轻微伤不构成犯罪

        # 使用凶器
        if circumstances.get("weapon_used"):
            base = int(base * 1.2)

        # 多名被害人
        victims = circumstances.get("multiple_victims", 1)
        if victims > 1:
            base = int(base * (1 + 0.15 * (victims - 1)))  # 每增加1人+15%

        return base

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

        # 第二层面：同向相加、逆向相减
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
            steps.append(f"第二层面计算结果: {current_months:.2f} × (1 + ({layer2_adjustment:.2f})) = {final_months:.2f}个月")
        else:
            final_months = current_months

        return {
            "final_months": round(final_months, 2),
            "calculation_steps": steps,
            "formula": f"{base_months} × L1({layer1_multiplier}) × L2(1 + {layer2_adjustment})"
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
    def months_to_range(center_months: float, width: int = 6) -> List[int]:
        """
        将中心月数转换为刑期区间

        Args:
            center_months: 中心月数
            width: 区间宽度（默认6个月）

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
                    },
                    "circumstances": {
                        "type": "object",
                        "description": "犯罪情节，根据不同罪名包含不同字段",
                        "properties": {
                            "multiple_thefts": {
                                "type": "boolean",
                                "description": "多次盗窃（适用于盗窃罪）"
                            },
                            "burglary": {
                                "type": "boolean",
                                "description": "入户盗窃（适用于盗窃罪）"
                            },
                            "pickpocketing": {
                                "type": "boolean",
                                "description": "携带凶器盗窃（适用于盗窃罪）"
                            },
                            "public_places": {
                                "type": "boolean",
                                "description": "在公共场所扒窃（适用于盗窃罪）"
                            },
                            "telecom_fraud": {
                                "type": "boolean",
                                "description": "电信网络诈骗（适用于诈骗罪）"
                            },
                            "vulnerable_victims": {
                                "type": "boolean",
                                "description": "诈骗残疾人/老年人（适用于诈骗罪）"
                            },
                            "disaster_fraud": {
                                "type": "boolean",
                                "description": "诈骗救灾款物（适用于诈骗罪）"
                            },
                            "medical_fraud": {
                                "type": "boolean",
                                "description": "医保诈骗（适用于诈骗罪）"
                            },
                            "weapon_used": {
                                "type": "boolean",
                                "description": "使用凶器（适用于故意伤害罪）"
                            },
                            "multiple_victims": {
                                "type": "integer",
                                "description": "被害人人数（适用于故意伤害罪）"
                            },
                            "disability_caused": {
                                "type": "string",
                                "enum": ["一级", "二级", "三级", "四级", "五级", "六级", "七级", "八级", "九级", "十级"],
                                "description": "造成残疾等级（适用于故意伤害罪）"
                            },
                            "premeditated": {
                                "type": "boolean",
                                "description": "预谋（适用于故意伤害罪）"
                            }
                        }
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
                        "type": "integer",
                        "description": "中心月数"
                    },
                    "width": {
                        "type": "integer",
                        "description": "区间宽度（默认6个月）",
                        "default": 6
                    }
                },
                "required": ["center_months"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "calculate_layered_sentence_deterministic",
            "description": "使用固定系数表进行确定性分层量刑计算，确保相同输入得到相同输出",
            "parameters": {
                "type": "object",
                "properties": {
                    "base_months": {
                        "type": "integer",
                        "description": "基准刑（月数）"
                    },
                    "layer1_descriptions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "第一层面情节描述列表，如['未成年人，已满17周岁', '从犯，作用较小']"
                    },
                    "layer2_descriptions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "第二层面情节描述列表，如['自首，主动投案', '退赃全部']"
                    }
                },
                "required": ["base_months", "layer1_descriptions", "layer2_descriptions"]
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
    """
    calculator = SentencingCalculator()

    try:
        if tool_name == "calculate_base_sentence":
            result = calculator.calculate_base_sentence(**tool_arguments)
            return json.dumps({"base_months": result}, ensure_ascii=False)

        elif tool_name == "calculate_layered_sentence":
            result = calculator.calculate_layered_sentence(**tool_arguments)
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "calculate_layered_sentence_deterministic":
            # ✅ 新增：确定性计算
            base_months = tool_arguments["base_months"]
            layer1_descriptions = tool_arguments.get("layer1_descriptions", [])
            layer2_descriptions = tool_arguments.get("layer2_descriptions", [])

            # 匹配第一层面情节
            layer1_factors = []
            layer1_details = []
            for desc in layer1_descriptions:
                matched = calculator.match_layer1_factor(desc)
                layer1_factors.append({
                    "name": matched["name"],
                    "ratio": matched["ratio"]
                })
                layer1_details.append(f"{matched['name']}(系数{matched['ratio']}, 理由:{matched['match_reason']})")

            # 匹配第二层面情节
            layer2_factors = []
            layer2_details = []
            for desc in layer2_descriptions:
                matched = calculator.match_layer2_factor(desc)
                ratio = 1.0 + (matched["adjustment_pct"] / 100)  # 转换百分比为比例
                layer2_factors.append({
                    "name": matched["name"],
                    "ratio": ratio
                })
                layer2_details.append(
                    f"{matched['name']}(调节{matched['adjustment_pct']:+}%, 理由:{matched['match_reason']})")

            # 调用计算函数
            result = calculator.calculate_layered_sentence(
                base_months=base_months,
                layer1_factors=layer1_factors,
                layer2_factors=layer2_factors
            )

            # 添加匹配详情到结果中
            result["layer1_matching"] = layer1_details
            result["layer2_matching"] = layer2_details

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
        import traceback
        error_detail = traceback.format_exc()
        return json.dumps({"error": str(e), "detail": error_detail}, ensure_ascii=False)


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
    range_result = calc.months_to_range(48, width=6)
    print(f"刑期区间: {range_result}\n")
