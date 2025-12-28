"""
刑期计算器工具
提供精确的量刑计算功能，避免 LLM 直接进行数值计算
"""

import json
from typing import Dict, List, Union


class SentencingCalculator:
    """量刑计算器：用于精确计算刑期"""

    # 各地区盗窃罪、诈骗罪数额标准（单位：元）
    REGIONAL_STANDARDS = {
        "default": {
            "theft": {"large": 1000, "huge": 30000, "especially_huge": 300000},
            "fraud": {"large": 3000, "huge": 30000, "especially_huge": 500000}
        },
        # 北京
        "北京": {
            "theft": {"large": 2000, "huge": 60000, "especially_huge": 400000},
            "fraud": {"large": 5000, "huge": 100000, "especially_huge": 500000}
        },
        # 上海
        "上海": {
            "theft": {"large": 6000, "huge": 100000, "especially_huge": 500000},
            "fraud": {"large": 6000, "huge": 100000, "especially_huge": 500000}
        },

        # 广东（一类地区）
        "广东": {
            "theft": {"large": 3000, "huge": 100000, "especially_huge": 500000},
            "fraud": {"large": 6000, "huge": 100000, "especially_huge": 500000}
        },
        # 广东二类地区示例
        "惠州": {
            "theft": {"large": 2000, "huge": 60000, "especially_huge": 400000},
            "fraud": {"large": 4000, "huge": 60000, "especially_huge": 500000}
        },
        "江门": {
            "theft": {"large": 2000, "huge": 60000, "especially_huge": 400000},
            "fraud": {"large": 4000, "huge": 60000, "especially_huge": 500000}
        },
        "汕头": {
            "theft": {"large": 2000, "huge": 60000, "especially_huge": 400000},
            "fraud": {"large": 4000, "huge": 60000, "especially_huge": 500000}
        },
        # 江苏
        "江苏": {
            "theft": {"large": 2000, "huge": 50000, "especially_huge": 400000},
            "fraud": {"large": 6000, "huge": 100000, "especially_huge": 500000}
        },
        # 浙江
        "浙江": {
            "theft": {"large": 3000, "huge": 80000, "especially_huge": 400000},
            "fraud": {"large": 6000, "huge": 100000, "especially_huge": 500000}
        },
        # 山东
        "山东": {
            "theft": {"large": 2000, "huge": 60000, "especially_huge": 400000},
            "fraud": {"large": 6000, "huge": 80000, "especially_huge": 500000}
        },
        # 其他省份
        "天津": {
            "theft": {"large": 1000, "huge": 30000, "especially_huge": 300000},
            "fraud": {"large": 5000, "huge": 50000, "especially_huge": 500000}
        },
        "重庆": {
            "theft": {"large": 2000, "huge": 60000, "especially_huge": 400000},
            "fraud": {"large": 5000, "huge": 70000, "especially_huge": 500000}
        },
        "贵州": {
            "theft": {"large": 1000, "huge": 30000, "especially_huge": 300000},
            "fraud": {"large": 3000, "huge": 50000, "especially_huge": 500000}
        },
        "河南": {
            "theft": {"large": 2000, "huge": 50000, "especially_huge": 400000},
            "fraud": {"large": 5000, "huge": 50000, "especially_huge": 500000}
        },
        "河北": {
            "theft": {"large": 2000, "huge": 60000, "especially_huge": 400000},
            "fraud": {"large": 5000, "huge": 60000, "especially_huge": 500000}
        },
        "辽宁": {
            "theft": {"large": 2000, "huge": 70000, "especially_huge": 400000},
            "fraud": {"large": 6000, "huge": 60000, "especially_huge": 500000}
        },
        "四川": {
            "theft": {"large": 1600, "huge": 50000, "especially_huge": 300000},
            "fraud": {"large": 5000, "huge": 50000, "especially_huge": 500000}
        },
        "安徽": {
            "theft": {"large": 2000, "huge": 50000, "especially_huge": 400000},
            "fraud": {"large": 5000, "huge": 50000, "especially_huge": 500000}
        },
        "陕西": {
            "theft": {"large": 1000, "huge": 30000, "especially_huge": 300000},
            "fraud": {"large": 5000, "huge": 50000, "especially_huge": 500000}
        },
        "山西": {
            "theft": {"large": 1000, "huge": 30000, "especially_huge": 300000},
            "fraud": {"large": 5000, "huge": 80000, "especially_huge": 500000}
        },
        "湖南": {
            "theft": {"large": 2000, "huge": 50000, "especially_huge": 400000},
            "fraud": {"large": 5000, "huge": 50000, "especially_huge": 500000}
        },
        "湖北": {
            "theft": {"large": 2000, "huge": 50000, "especially_huge": 500000},
            "fraud": {"large": 5000, "huge": 50000, "especially_huge": 500000}
        },
        "福建": {
            "theft": {"large": 3000, "huge": 60000, "especially_huge": 300000},
            "fraud": {"large": 5000, "huge": 100000, "especially_huge": 500000}
        },
        "云南": {
            "theft": {"large": 1500, "huge": 40000, "especially_huge": 350000},
            "fraud": {"large": 5000, "huge": 50000, "especially_huge": 500000}
        },
        "广西": {
            "theft": {"large": 1500, "huge": 40000, "especially_huge": 400000},
            "fraud": {"large": 5000, "huge": 50000, "especially_huge": 500000}
        },
        "江西": {
            "theft": {"large": 1500, "huge": 50000, "especially_huge": 400000},
            "fraud": {"large": 5000, "huge": 50000, "especially_huge": 500000}
        },
        "吉林": {
            "theft": {"large": 2000, "huge": 30000, "especially_huge": 300000},
            "fraud": {"large": 5000, "huge": 50000, "especially_huge": 500000}
        },
        "黑龙江": {
            "theft": {"large": 1500, "huge": 50000, "especially_huge": 350000},
            "fraud": {"large": 5000, "huge": 50000, "especially_huge": 500000}
        },
        "海南": {
            "theft": {
                "large": 1500,
                "huge": 15000,
                "especially_huge": 70000
            },
            "fraud": {
                "large": 5000,
                "huge": 50000,
                "especially_huge": 500000
            }
        },
        "甘肃": {
            "theft": {
                "large": 2000,
                "huge": 60000,
                "especially_huge": 400000
            },
            "fraud": {
                "large": 3000,
                "huge": 30000,
                "especially_huge": 300000
            }
        },
        "青海": {
            "theft": {
                "large": 2000,
                "huge": 30000,
                "especially_huge": 300000
            },
            "fraud": {
                "large": 3000,
                "huge": 30000,
                "especially_huge": 500000
            }
        },
        "内蒙古": {
            "theft": {
                "large": 1600,
                "huge": 30000,
                "especially_huge": 300000
            },
            "fraud": {
                "large": 5000,
                "huge": 50000,
                "especially_huge": 500000
            }
        },
        "宁夏": {
            "theft": {
                "large": 1500,
                "huge": 30000,
                "especially_huge": 300000
            },
            "fraud": {
                "large": 3000,
                "huge": 30000,
                "especially_huge": 500000
            }
        },
        "西藏": {
            "theft": {
                "large": 2000,
                "huge": 50000,
                "especially_huge": 400000
            },
            "fraud": {
                "large": 6000,
                "huge": 50000,
                "especially_huge": 500000
            }
        },
        "新疆": {
            "theft": {
                "large": 1000,
                "huge": 30000,
                "especially_huge": 300000
            },
            "fraud": {
                "large": 3000,
                "huge": 50000,
                "especially_huge": 500000
            }
        },

        # 城市到省份的映射
        "cities_to_provinces": {
            "江门": "广东",
            "深圳": "广东",
            "广州": "广东",
            "珠海": "广东",
            "佛山": "广东",
            "东莞": "广东",
            "中山": "广东",
            "杭州": "浙江",
            "宁波": "浙江",
            "温州": "浙江",
            "嘉兴": "浙江",
            "绍兴": "浙江",
            "台州": "浙江",
            "义乌": "浙江",
            "南京": "江苏",
            "苏州": "江苏",
            "无锡": "江苏",
            "常州": "江苏",
            "徐州": "江苏",
            "济南": "山东",
            "青岛": "山东",
            "烟台": "山东",
            "潍坊": "山东",
            "大连": "辽宁",
            "沈阳": "辽宁",
            "哈尔滨": "黑龙江",
            "长春": "吉林",
            "成都": "四川",
            "西安": "陕西",
            "武汉": "湖北",
            "长沙": "湖南",
            "福州": "福建",
            "厦门": "福建",
            "贵阳": "贵州",
            "昆明": "云南",
            "南宁": "广西",
            "石家庄": "河北",
            "太原": "山西",
            "南昌": "江西",
            "合肥": "安徽",
            "郑州": "河南",
            "海口": "海南",
            "乌鲁木齐": "新疆",
            "呼和浩特": "内蒙古",
            "银川": "宁夏",
            "西宁": "青海",
            "拉萨": "西藏",
            "兰州": "甘肃"
        }
    }

    @staticmethod
    def _get_standards_by_region(region: str) -> Dict:
        """
        根据 region 获取对应的标准字典（含 theft / fraud），带城市到省份映射。
        """
        all_std = SentencingCalculator.REGIONAL_STANDARDS
        if region in all_std:
            return all_std[region]
        cities_map = all_std.get("cities_to_provinces", {})
        if region in cities_map:
            province = cities_map[region]
            return all_std.get(province, all_std["default"])
        return all_std["default"]

    @staticmethod
    def _calculate_base_sentence_fraud(amount: float, region: str = "default") -> int:
        """
        诈骗罪基准刑（单位：月）——线性插值版，重点调整“特别巨大”档位：
        - 数额较大：6~36 个月
        - 数额巨大：36~120 个月
        - 数额特别巨大：120~160 个月（而不是 120~180，避免普遍打到极高刑期）
        """
        standards = SentencingCalculator._get_standards_by_region(region)
        fraud_std = standards["fraud"]

        A = amount or 0.0
        L = fraud_std["large"]
        H = fraud_std["huge"]
        EH = fraud_std["especially_huge"]

        # 低于立案标准：给一个低值
        if A < L:
            return 6

        # 数额较大：在 [L, H) 之间线性插值到 6~36 月
        if A < H:
            ratio = (A - L) / float(H - L) if H > L else 0.0
            base = 6 + ratio * (36 - 6)
            return int(round(base))

        # 数额巨大：在 [H, EH) 之间线性插值到 36~120 月
        if A < EH:
            ratio = (A - H) / float(EH - H) if EH > H else 0.0
            base = 36 + ratio * (120 - 36)
            return int(round(base))

        # 数额特别巨大：120~160 月，随超额金额缓慢上浮
        # extra_ratio = 0 时，对应刚刚超过特别巨大起点 → 120 月
        # extra_ratio = 1 时，对应金额明显高于起点 → 160 月
        extra_ratio = min(1.0, (A - EH) / float(EH)) if EH > 0 else 1.0
        base = 120 + extra_ratio * 40  # 120→160
        return int(round(base))

    @staticmethod
    def calculate_base_sentence(
        crime_type: str,
        amount: float = None,
        injury_level: str = None,
        region: str = "default",
        theft_count: int = None,
        fraud_count: int = None
    ) -> int:
        """
        计算基准刑（单位：月）
        - 目前重点优化诈骗罪；
        - 其他罪名使用简单默认值，可按需扩展。
        """
        # 诈骗罪：使用线性插值版本
        if crime_type == "诈骗罪":
            return SentencingCalculator._calculate_base_sentence_fraud(amount or 0.0, region)

        # 其他罪名可以在此按需添加更精细的逻辑
        # 盗窃罪、故意伤害罪、职务侵占罪等目前返回一个中性基准值
        return 12

    @staticmethod
    def calculate_layered_sentence_with_constraints(
            base_months: int,
            crime_type: str,
            amount: float,
            layer1_factors: List[Dict[str, Union[str, float]]],
            layer2_factors: List[Dict[str, Union[str, float]]],
            has_statutory_mitigation: bool = False,
            injury_level: str = None
    ) -> Dict[str, Union[float, str]]:
        """
        分层计算最终刑期——打印完整计算过程。
        """
        steps = []
        current_months = float(base_months)

        print("====== [Calc] 分层量刑计算开始 ======")
        print(f"[Calc] 罪名: {crime_type}, 金额: {amount}, 基准刑: {base_months} 月")
        print(f"[Calc] 第一层情节: {layer1_factors}")
        print(f"[Calc] 第二层情节: {layer2_factors}")
        print(f"[Calc] 是否存在法定减轻情节: {has_statutory_mitigation}")

        steps.append(f"基准刑: {base_months}个月")

        # 第一层面：连乘
        layer1_multiplier = 1.0
        for factor in layer1_factors or []:
            name = factor.get("name") or factor.get("factor")
            ratio = factor["ratio"]
            layer1_multiplier *= ratio
            steps.append(f"第一层面 - {name}: ×{ratio}")
            print(f"[Calc] 第一层情节: {name}, 比例: {ratio}, 累计乘数: {layer1_multiplier:.4f}")

        if layer1_factors:
            current_months = base_months * layer1_multiplier
            steps.append(f"第一层面结果: {current_months:.2f}个月")
            print(f"[Calc] 第一层结果: {current_months:.2f} 月")
        else:
            print("[Calc] 无第一层情节，当前刑期保持为基准刑。")

        # 第二层面：按比例叠加
        layer2_adjustment = 0.0
        for factor in layer2_factors or []:
            name = factor.get("name") or factor.get("factor")
            ratio = factor["ratio"]
            adjustment = ratio - 1.0
            layer2_adjustment += adjustment
            steps.append(f"第二层面 - {name}: {'+' if adjustment > 0 else ''}{adjustment * 100:.0f}%")
            print(f"[Calc] 第二层情节: {name}, 比例: {ratio}, "
                  f"本项增减: {adjustment * 100:.1f}%, 累计增减: {layer2_adjustment * 100:.1f}%")

        if layer2_factors:
            layer2_multiplier = 1.0 + layer2_adjustment
            temp_final = current_months * layer2_multiplier
            steps.append(f"第二层面初步结果: {temp_final:.2f}个月")
            print(f"[Calc] 第二层乘数: {layer2_multiplier:.4f}, 第二层结果: {temp_final:.2f} 月")
        else:
            temp_final = current_months
            print("[Calc] 无第二层情节，当前刑期保持第一层结果。")

        # 基本有效性检查：不得低于 1 个月
        if temp_final < 1:
            steps.append(f"⚠️ 调整: 结果({temp_final:.2f}月)低于1个月，调整至1个月")
            print(f"[Calc] 结果 {temp_final:.2f} 月 < 1 月，调整为 1 月。")
            temp_final = 1.0

        final_months = round(temp_final, 2)
        print(f"[Calc] 最终刑期: {final_months} 月")
        print("====== [Calc] 分层量刑计算结束 ======\n")

        return {
            "final_months": final_months,
            "base_months": base_months,
            "calculation_steps": steps,
            "constrained": False
        }

    @staticmethod
    def _get_legal_range(crime_type: str, amount: float, injury_level: str = None) -> tuple:
        """
        获取法定刑档位的上下限（可根据需要使用）
        """
        if crime_type == "诈骗罪":
            if amount < 30000:
                return (6, 36)
            elif amount < 500000:
                return (36, 120)
            else:
                return (120, 180)
        return (6, 120)

    @staticmethod
    def apply_factor(base_months: int, factor_name: str, factor_ratio: float) -> float:
        """
        应用单个情节调节因子
        """
        result = base_months * factor_ratio
        return round(result, 2)

    @staticmethod
    def calculate_simple_adjustment(base_months: int, adjustment_percent: float) -> int:
        """
        简单百分比调节计算
        """
        multiplier = 1.0 + (adjustment_percent / 100.0)
        result = base_months * multiplier
        return round(result)

    @staticmethod
    def months_to_range(center_months: float, width: int = None) -> List[int]:
        """
        将中心月数转换为刑期区间，并打印区间生成过程。
        """
        if width is None:
            width = max(6, min(12, center_months * 0.15))

        half_width = width / 2.0
        min_months = max(1, round(center_months - half_width))
        max_months = max(1, round(center_months + half_width))

        print("------ [Range] 刑期区间计算 ------")
        print(f"[Range] 中心刑期: {center_months} 月, 预设宽度: {width} 月")
        print(f"[Range] 计算得到区间: [{int(min_months)}, {int(max_months)}]")
        print("------ [Range] 计算结束 ------\n")

        return [int(min_months), int(max_months)]

    @staticmethod
    def validate_legal_range(months: int, min_legal: int, max_legal: int) -> int:
        """
        验证并调整刑期是否在法定范围内
        """
        if months < min_legal:
            return min_legal
        if months > max_legal:
            return max_legal
        return months


# 工具函数定义（OpenAI Function Calling 格式）
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
            "description": "根据分层量刑规则精确计算最终刑期（保留以兼容旧逻辑，当前主用 with_constraints 版本）",
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
                        "description": "区间宽度（若省略则按经验公式自动计算）"
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
            "description": "带约束条件的分层量刑计算（当前主用版本）",
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
                        "enum": ["轻伤一级", "轻伤二级", "重伤一级", "重伤二级", "致人死亡", "死亡"]
                    }
                },
                "required": ["base_months", "crime_type", "amount", "layer1_factors", "layer2_factors"]
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
    执行工具调用（为兼容保留；当前 Task2 已不依赖 LLM 工具调用，但你可在调试时继续使用）。
    """
    calculator = SentencingCalculator()

    try:
        if tool_name == "calculate_base_sentence":
            result = calculator.calculate_base_sentence(**tool_arguments)
            return json.dumps({"base_months": result}, ensure_ascii=False)

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
