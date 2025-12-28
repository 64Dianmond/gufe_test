import json
import os
import re
from openai import OpenAI
from dotenv import load_dotenv
from cal_zp import SENTENCING_TOOLS, execute_tool_call, SentencingCalculator

# 加载环境变量
load_dotenv()


class SentencingPredictor:
    """
    一个基于大型语言模型的法律量刑预测器。
    Task1 使用 LLM 做情节抽取（带强约束提示词）；
    Task2 改为纯规则 + 计算器的确定性计算，避免 LLM 在数值与权重上自由发挥。
    """

    def __init__(self):
        """
        初始化客户端和模型配置。
        """
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL")
        )
        self.model_name = os.getenv("OPENAI_MODEL", "qwen-max")
        self.temperature_task1 = 0.1  # Task1 使用稍低温度，保证稳定 + 轻微多样性
        self.temperature_task2 = 0.1  # Task2 已改为规则化，这个参数基本不会再用
        self.max_tokens = 32768

    # ===== 基础信息抽取工具 =====

    def identify_crime_type(self, defendant_info, case_description):
        """
        增强版的罪名识别函数。
        优先从指控中识别,其次通过关键词匹配。
        """
        text = (defendant_info or "") + (case_description or "")
        text = text.replace(" ", "").replace("\n", "")

        # 1. 优先匹配指控罪名
        charge_match = re.search(r'(因涉嫌|指控犯)(.*?)罪', text)
        if charge_match:
            crime = charge_match.group(2)
            if "盗窃" in crime:
                return "盗窃罪"
            if "故意伤害" in crime:
                return "故意伤害罪"
            if "诈骗" in crime:
                return "诈骗罪"
            if "职务侵占" in crime:
                return "职务侵占罪"

        # 2. 关键词备用
        theft_keywords = ["盗窃", "窃取", "扒窃", "盗走"]
        injury_keywords = ["故意伤害", "殴打", "打伤", "轻伤", "重伤"]
        fraud_keywords = ["诈骗", "骗取", "虚构事实"]
        embezzlement_keywords = ["职务侵占", "挪用资金", "非法占有"]

        if any(k in text for k in theft_keywords):
            return "盗窃罪"
        if any(k in text for k in injury_keywords):
            return "故意伤害罪"
        if any(k in text for k in fraud_keywords):
            return "诈骗罪"
        if any(k in text for k in embezzlement_keywords):
            return "职务侵占罪"

        # 3. 默认回退
        return "盗窃罪"

    def extract_region(self, defendant_info, case_description):
        """
        从案件信息中提取地区信息
        """
        text = (defendant_info or "") + (case_description or "")

        regions = [
            "北京", "上海", "天津", "重庆", "河北", "山西", "辽宁", "吉林",
            "黑龙江", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南",
            "湖北", "湖南", "广东", "海南", "四川", "贵州", "云南", "陕西",
            "甘肃", "青海", "台湾", "内蒙古", "广西", "西藏", "宁夏", "新疆",
            "香港", "澳门"
        ]

        cities = [
            "江门", "深圳", "广州", "珠海", "佛山", "东莞", "中山", "杭州",
            "宁波", "温州", "嘉兴", "绍兴", "台州", "义乌", "南京", "苏州",
            "无锡", "常州", "徐州", "济南", "青岛", "烟台", "潍坊", "大连",
            "沈阳", "哈尔滨", "长春", "成都", "西安", "武汉", "长沙", "福州",
            "厦门", "贵阳", "昆明", "南宁", "石家庄", "太原", "南昌", "合肥",
            "郑州", "海口", "乌鲁木齐", "呼和浩特", "银川", "西宁", "拉萨", "兰州"
        ]

        for region in regions:
            if region in text:
                return region

        for city in cities:
            if city in text:
                return city

        return "default"

    # ===== Prompt 构造（Task1） =====

    def _get_amount_standards_for_prompt(self, crime_type, region):
        """
        根据罪名和地区的数额标准生成提示信息
        """
        standards_all = SentencingCalculator.REGIONAL_STANDARDS

        if region in standards_all:
            standards = standards_all[region]
        elif region in standards_all.get("cities_to_provinces", {}):
            province = standards_all["cities_to_provinces"][region]
            standards = standards_all[province]
        else:
            standards = standards_all["default"]

        if crime_type == "盗窃罪" and "theft" in standards:
            theft_standards = standards["theft"]
            return f"""**{region}盗窃罪数额标准:**
- **数额较大**: {theft_standards['large']}元以上不满{theft_standards['huge']}元
- **数额巨大**: {theft_standards['huge']}元以上不满{theft_standards['especially_huge']}元
- **数额特别巨大**: {theft_standards['especially_huge']}元以上"""

        elif crime_type == "诈骗罪" and "fraud" in standards:
            fraud_standards = standards["fraud"]
            return f"""**{region}诈骗罪数额标准:**
- **数额较大**: {fraud_standards['large']}元以上不满{fraud_standards['huge']}元
- **数额巨大**: {fraud_standards['huge']}元以上不满{fraud_standards['especially_huge']}元
- **数额特别巨大**: {fraud_standards['especially_huge']}元以上"""

        elif crime_type == "职务侵占罪":
            # 使用河南标准作为默认
            return """**河南职务侵占罪数额标准:**
- **数额较大**: 6万元以上不满100万元
- **数额巨大**: 100万元以上不满1500万元
- **数额特别巨大**: 1500万元以上"""

        else:
            return """**全国通用数额标准参考:**
- **盗窃罪**:
  - 数额较大: 1000元以上不满30000元
  - 数额巨大: 30000元以上不满300000元
  - 数额特别巨大: 300000元以上
- **诈骗罪**:
  - 数额较大: 3000元以上不满30000元
  - 数额巨大: 30000元以上不满500000元
  - 数额特别巨大: 500000元以上"""

    def build_prompt_task1_authoritative(self, defendant_info, case_description):
        """
        Task1 提示词：锁死诈骗罪标签空间。
        若你之后希望扩展到其他罪名，可以在此增加分支。
        """
        crime_type = "诈骗罪"  # 当前专门优化诈骗罪子任务
        region = self.extract_region(defendant_info, case_description)
        amount_standards = self._get_amount_standards_for_prompt(crime_type, region)

        prompt = f"""
你是一名中国刑事法官，专门办理诈骗罪案件。请从下面的案情事实中，提取**与量刑直接相关**的情节，且只能使用下面给定的标签形式。

【标签种类和固定写法（只能用这些）】

1. 金额类（必选其一，如能确定）：
   - "诈骗金额既遂XXXX元"
   - "诈骗金额未遂XXXX元"
   其中 XXXX 必须是案情中明确写出的总金额，或可以由多笔金额简单相加得到的总金额。

2. 数额档次（最多输出一个）：
   - "诈骗数额较大"
   - "诈骗数额巨大"
   - "诈骗数额特别巨大"
   判断标准请严格根据本地区数额标准：
{amount_standards}

3. 次数类（二选一，不能同时出现）：
   - "诈骗次数X次"   —— 能够从案情中精确统计次数时使用
   - "多次诈骗"       —— 只能确认“多次”，但无法精确统计次数时使用

4. 犯罪手段：
   - "电信网络诈骗"   —— 仅在案情中出现电话、短信、微信、QQ、网络平台、APP 等典型电信网络手段时使用

5. 法定/酌定量刑情节：
   - "自首"
   - "坦白"
   - "认罪认罚"
   - "当庭自愿认罪"
   - "退赔XXXX元"
   - "退赃XXXX元"
   - "退赔全部损失"
   - "退赔部分损失"
   - "取得谅解"
   - "前科"
   - "累犯"

【严格规则】

- 只能在案情中有明确事实依据时输出标签，宁少勿多；
- 金额、次数必须与案情文字一致，不要自己估算；
- 若案情写明“退赔全部损失”，优先使用 "退赔全部损失" 标签，不再额外写具体金额；
- 若同时出现“累犯”和“前科”事实，只输出“累犯”，不要重复评价；
- 已经用来确定“诈骗金额”“数额档次”“次数”的事实，在后续量刑情节中不要重复发明新标签描述。

【输出格式】

- 只输出一个 JSON 数组，不要输出任何解释和多余文字；
- 例如：
  ["诈骗金额既遂50000元","诈骗数额较大","诈骗次数2次","电信网络诈骗","自首","认罪认罚","退赔全部损失"]

【案情事实】
{case_description}
"""
        return prompt

    # ===== Task1: 调用 + 轻量后处理 =====

    def _postprocess_fraud_factors(self, raw_factors):
        """
        对诈骗罪的 Task1 输出做轻量后处理：
        - 去除明显无关或重复标签；
        - 统一金额小数位；
        - 避免同时出现“诈骗次数X次”和“多次诈骗”。
        """
        if not isinstance(raw_factors, list):
            return raw_factors

        cleaned = []
        has_count = False
        has_multi = False

        for f in raw_factors:
            if not isinstance(f, str):
                continue
            f = f.strip()

            # 1. 过滤明显不在字典中的“自造标签”
            allowed_exact = {
                "诈骗数额较大", "诈骗数额巨大", "诈骗数额特别巨大",
                "电信网络诈骗",
                "自首", "坦白", "认罪认罚", "当庭自愿认罪",
                "退赔全部损失", "退赔部分损失",
                "取得谅解",
                "前科", "累犯"
            }
            # 前缀类标签另行处理
            if f in allowed_exact:
                cleaned.append(f)
                continue

            # 2. 次数类（优先保留“诈骗次数X次”，避免和“多次诈骗”重复）
            if f.startswith("诈骗次数"):
                if not has_count:
                    cleaned.append(f)
                    has_count = True
                continue

            if f == "多次诈骗":
                # 只有在没有精确次数的情况下才保留
                if not has_count and not has_multi:
                    cleaned.append(f)
                    has_multi = True
                continue

            # 3. 金额类：保留，但规范小数位
            if f.startswith("诈骗金额既遂") or f.startswith("诈骗金额未遂"):
                # 统一为最多两位小数
                m_yuan = re.search(r"(诈骗金额[既未]遂)([\d\.]+)元", f)
                m_wan = re.search(r"(诈骗金额[既未]遂)([\d\.]+)万元", f)
                prefix = None
                amount_val = None
                unit = "元"

                if m_wan:
                    prefix = m_wan.group(1)
                    try:
                        amount_val = float(m_wan.group(2)) * 10000.0
                    except Exception:
                        amount_val = None
                elif m_yuan:
                    prefix = m_yuan.group(1)
                    try:
                        amount_val = float(m_yuan.group(2))
                    except Exception:
                        amount_val = None

                if prefix is not None and amount_val is not None:
                    # 这里采用“元”为单位，保留两位小数；如你发现标注统一用整数，可以改成 :.0f
                    normalized = f"{prefix}{amount_val:.2f}元"
                    cleaned.append(normalized)
                else:
                    cleaned.append(f)
                continue

            # 4. 退赔/退赃金额类：直接保留
            if f.startswith("退赔") or f.startswith("退赃"):
                cleaned.append(f)
                continue

            # 其他未知标签，先保留（如果你确认标注集没有，可以在这里丢弃）
            cleaned.append(f)

        # 5. 若同时存在“累犯”和“前科”，去掉“前科”
        if "累犯" in cleaned and "前科" in cleaned:
            cleaned = [x for x in cleaned if x != "前科"]

        return cleaned

    def predict_task1_authoritative(self, defendant_info, case_description):
        """
        执行 Task1: 提取量刑情节（诈骗罪专用）。
        """
        prompt = self.build_prompt_task1_authoritative(defendant_info, case_description)
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位经验丰富的刑事法官,精通中国刑法量刑情节认定,对细节极其敏感。"
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature_task1,
                max_tokens=self.max_tokens
            )
            result_text = response.choices[0].message.content.strip()

            json_match = re.search(r'\[.*?\]', result_text, re.DOTALL)
            if json_match:
                raw_factors = json.loads(json_match.group(0))
                # 当前聚焦诈骗罪，直接按诈骗罪规则后处理
                processed = self._postprocess_fraud_factors(raw_factors)
                return processed
            else:
                print(f"警告 (Task 1): 未能在输出中找到JSON数组。返回: {result_text}")
                return ["诈骗数额较大"]
        except Exception as e:
            print(f"错误 (Task 1): API调用或JSON解析失败: {e}")
            return ["诈骗数额较大"]

    # ===== Task2：完全规则化的量刑计算 =====

    def _extract_amount_from_factors(self, factors):
        """
        从 Task1 输出的标签中提取金额（元）。
        支持：
        - 诈骗金额既遂XXXX元 / 万元
        - 诈骗金额未遂XXXX元 / 万元
        """
        if not factors:
            return None

        for f in factors:
            if not isinstance(f, str):
                continue
            if "金额既遂" in f or "金额未遂" in f:
                m_wan = re.search(r"金额[既未]遂([\d\.]+)万元", f)
                m_yuan = re.search(r"金额[既未]遂([\d\.]+)元", f)

                if m_wan:
                    try:
                        return float(m_wan.group(1)) * 10000.0
                    except Exception:
                        continue
                if m_yuan:
                    try:
                        return float(m_yuan.group(1))
                    except Exception:
                        continue
        return None

    def _extract_fraud_count(self, factors):
        """
        从标签中解析“诈骗次数X次”的次数。
        """
        if not factors:
            return None
        for f in factors:
            if not isinstance(f, str):
                continue
            m = re.search(r"诈骗次数(\d+)次", f)
            if m:
                try:
                    return int(m.group(1))
                except Exception:
                    continue
        return None

    def _map_factors_from_answer1(self, crime_type, factors):
        """
        将 Task1 的标签映射为分层量刑情节（完全在 Python 中确定，不再交给 LLM）。

        返回：
        - layer1_factors: [{'name': str, 'ratio': float}, ...]
        - layer2_factors: [{'name': str, 'ratio': float}, ...]
        - has_statutory_mitigation: bool
        """
        layer1 = []
        layer2 = []

        # 可根据需要继续扩展
        has_statutory = False
        tags = set(factors or [])

        # ===== 第一层：法定减轻/从轻情节（连乘） =====
        # 若你之后为其他罪名加入“未成年人”“从犯”等，可在此补充
        # 示例：未成年人、犯罪未遂等
        for f in factors or []:
            if "未成年人" in f:
                layer1.append({"name": "未成年人", "ratio": 0.7})
                has_statutory = True
            if "犯罪预备" in f:
                layer1.append({"name": "犯罪预备", "ratio": 0.5})
                has_statutory = True
            if "犯罪中止" in f:
                layer1.append({"name": "犯罪中止", "ratio": 0.5})
                has_statutory = True
            # 利用“金额未遂”标签推断犯罪未遂
            if "金额未遂" in f or "犯罪未遂" in f:
                layer1.append({"name": "犯罪未遂", "ratio": 0.5})
                has_statutory = True

        # ===== 第二层：从重情节 =====
        if "累犯" in tags:
            layer2.append({"name": "累犯", "ratio": 1.30})
        if "前科" in tags and "累犯" not in tags:
            layer2.append({"name": "前科", "ratio": 1.10})

        # “多次诈骗”：作为酌定从重
        if "多次诈骗" in tags:
            layer2.append({"name": "多次诈骗", "ratio": 1.10})

        # 电信网络诈骗：酌定从重 + 基准刑处已通过“就高”处理一部分
        if "电信网络诈骗" in tags:
            layer2.append({"name": "电信网络诈骗", "ratio": 1.15})

        # ===== 第二层：从轻情节 =====
        if "自首" in tags:
            layer2.append({"name": "自首", "ratio": 0.80})
            has_statutory = True  # 自首也可视作法定减轻基础（此处记为有法定减轻）

        if "坦白" in tags:
            layer2.append({"name": "坦白", "ratio": 0.80})

        if "认罪认罚" in tags or "当庭自愿认罪" in tags:
            # 可视情况调到 0.9 或 0.95
            layer2.append({"name": "认罪认罚", "ratio": 0.95})

        # 退赔/退赃：视作酌定从轻
        if any(f.startswith("退赔") or f.startswith("退赃") for f in factors or []):
            layer2.append({"name": "退赃/退赔", "ratio": 0.85})

        if "退赔全部损失" in tags:
            # 全额退赔 + 一般退赔叠加可能过度，这里可以微调逻辑：
            # 要么单独给“退赔全部损失”0.8，把通用退赔略去；
            # 为简化，这里不额外叠加。
            pass

        if "取得谅解" in tags:
            layer2.append({"name": "取得谅解", "ratio": 0.95})

        return layer1, layer2, has_statutory

    def _choose_width_for_fraud(self, amount, region):
        """
        根据金额档次选择默认区间宽度（可根据验证集微调）。
        - 数额较大：宽度 8
        - 数额巨大：宽度 10
        - 数额特别巨大：宽度 12
        """
        standards_all = SentencingCalculator.REGIONAL_STANDARDS

        if region in standards_all:
            standards = standards_all[region]
        elif region in standards_all.get("cities_to_provinces", {}):
            province = standards_all["cities_to_provinces"][region]
            standards = standards_all[province]
        else:
            standards = standards_all["default"]

        fraud_std = standards["fraud"]
        L, H, EH = fraud_std["large"], fraud_std["huge"], fraud_std["especially_huge"]

        if amount is None:
            return 10  # 中档宽度

        if amount < H:
            return 8   # 数额较大
        elif amount < EH:
            return 10  # 数额巨大
        else:
            return 12  # 数额特别巨大

    def predict_task2_with_tools(self, defendant_info, case_description, sentencing_factors):
        """
        执行 Task2：使用规则 + 计算器进行刑期预测，并在控制台打印完整计算过程。

        返回：[min_months, max_months]
        """
        if not sentencing_factors:
            sentencing_factors = ["犯罪情节较轻"]

        crime_type = self.identify_crime_type(defendant_info, case_description)
        region = self.extract_region(defendant_info, case_description)
        amount = self._extract_amount_from_factors(sentencing_factors)
        fraud_count = self._extract_fraud_count(sentencing_factors)

        print("\n******** [Task2] 刑期计算流程 ********")
        print(f"[Task2] 罪名: {crime_type}")
        print(f"[Task2] 地区: {region}")
        print(f"[Task2] 识别出的金额: {amount} 元")
        print(f"[Task2] 识别出的诈骗次数: {fraud_count}")
        print(f"[Task2] 量刑情节标签: {sentencing_factors}")

        # 1. 基准刑
        base_months = SentencingCalculator.calculate_base_sentence(
            crime_type=crime_type,
            amount=amount,
            region=region
        )
        print(f"[Task2] 计算得到基准刑: {base_months} 月")

        # 2. 映射分层情节
        layer1_factors, layer2_factors, has_statutory = self._map_factors_from_answer1(
            crime_type, sentencing_factors
        )
        print(f"[Task2] 第一层情节映射结果: {layer1_factors}")
        print(f"[Task2] 第二层情节映射结果: {layer2_factors}")
        print(f"[Task2] 是否存在法定减轻情节: {has_statutory}")

        # 3. 通过分层量刑计算最终刑期月数
        calc_result = SentencingCalculator.calculate_layered_sentence_with_constraints(
            base_months=base_months,
            crime_type=crime_type,
            amount=amount or 0.0,
            layer1_factors=layer1_factors,
            layer2_factors=layer2_factors,
            has_statutory_mitigation=has_statutory,
            injury_level=None
        )

        final_months = calc_result["final_months"]
        print(f"[Task2] 分层计算后最终刑期: {final_months} 月")

        # 4. 根据金额档次选择区间宽度，并生成区间
        if crime_type == "诈骗罪":
            width = self._choose_width_for_fraud(amount, region)
        else:
            width = 10

        print(f"[Task2] 选定区间宽度: {width} 月")
        final_range = SentencingCalculator.months_to_range(
            center_months=final_months,
            width=width
        )
        print(f"[Task2] 最终刑期区间: {final_range}")
        print("******** [Task2] 刑期计算流程结束 ********\n")

        return final_range

    # ===== 数据处理入口 =====

    def process_all_data(self, preprocessed_data, output_file):
        """
        主处理流程: 遍历所有数据, 执行两阶段预测, 并保存结果。
        """
        results = []

        for idx, item in enumerate(preprocessed_data):
            print(f"\n{'=' * 60}")
            print(f"处理第 {idx + 1}/{len(preprocessed_data)} 条数据 (ID: {item['id']})")
            print(f"{'=' * 60}")

            answer1, answer2 = [], []
            try:
                print("\n【步骤1: 提取量刑情节】")
                answer1 = self.predict_task1_authoritative(
                    item.get('defendant_info', ""),
                    item.get('case_description', "")
                )
                print(f"✓ 提取到的情节: {answer1}")

                print("\n【步骤2: 规则计算刑期】")
                answer2 = self.predict_task2_with_tools(
                    item.get('defendant_info', ""),
                    item.get('case_description', ""),
                    answer1,
                )
                print(f"✓ 预测刑期区间: {answer2}")

            except Exception as e:
                print(f"!!! 处理ID {item['id']} 时发生未知严重错误: {e}")
                answer1 = answer1 if answer1 else ["诈骗数额较大"]
                answer2 = answer2 if answer2 else [6, 12]

            result = {
                "id": item['id'],
                "answer1": answer1,
                "answer2": answer2
            }
            results.append(result)

            print(f"\n【最终结果】")
            print(f"  答案1 (情节提取): {answer1}")
            print(f"  答案2 (刑期预测): {answer2}")

            # 可以改为每处理 N 条保存一次
            if (idx + 1) % 1 == 0:
                print(f"\n--- 进度保存:已处理 {idx + 1} 条数据 ---")
                self._save_results(results, output_file)

        self._save_results(results, output_file)
        print(f"\n所有数据处理完成,结果已保存至: {output_file}")
        return results

    def process_fact_data(self, fact_data, output_file):
        """
        处理 fact 格式的数据（新格式，仅有 fact 字段）。
        """
        results = []

        for idx, item in enumerate(fact_data):
            print(f"\n{'=' * 60}")
            print(f"处理第 {idx + 1}/{len(fact_data)} 条数据 (ID: {item['id']})")
            print(f"{'=' * 60}")

            answer1, answer2 = [], []
            try:
                print("\n【步骤1: 提取量刑情节】")
                answer1 = self.predict_task1_authoritative(
                    "",          # 被告人信息为空
                    item['fact'] # 使用 fact 作为案情描述
                )
                print(f"✓ 提取到的情节: {answer1}")

                print("\n【步骤2: 规则计算刑期】")
                answer2 = self.predict_task2_with_tools(
                    "",          # 被告人信息为空
                    item['fact'],
                    answer1,
                )
                print(f"✓ 预测刑期区间: {answer2}")

            except Exception as e:
                print(f"!!! 处理ID {item['id']} 时发生未知严重错误: {e}")
                answer1 = answer1 if answer1 else ["诈骗数额较大"]
                answer2 = answer2 if answer2 else [6, 12]

            result = {
                "id": item['id'],
                "answer1": answer1,
                "answer2": answer2
            }
            results.append(result)

            print(f"\n【最终结果】")
            print(f"  答案1 (情节提取): {answer1}")
            print(f"  答案2 (刑期预测): {answer2}")

            if (idx + 1) % 1 == 0:
                print(f"\n--- 进度保存:已处理 {idx + 1} 条数据 ---")
                self._save_results(results, output_file)

        self._save_results(results, output_file)
        print(f"\n所有数据处理完成,结果已保存至: {output_file}")
        return results

    def _save_results(self, results, output_file):
        """
        将结果以 jsonl 格式保存到文件。
        """
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                for result in results:
                    f.write(json.dumps(result, ensure_ascii=False) + '\n')
        except IOError as e:
            print(f"错误:无法写入文件 {output_file}。请检查权限或路径。错误信息: {e}")


def load_preprocessed_data(preprocessed_file):
    """
    加载并验证预处理后的数据文件。
    """
    if not os.path.exists(preprocessed_file):
        raise FileNotFoundError(f"错误:预处理文件不存在: {preprocessed_file}\n请确保文件路径正确。")

    print(f"正在加载预处理数据: {preprocessed_file}")
    with open(preprocessed_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"✓ 成功加载 {len(data)} 条预处理数据")
    return data


def load_fact_data(fact_file):
    """
    加载 fact 格式的数据文件。
    """
    if not os.path.exists(fact_file):
        raise FileNotFoundError(f"错误:数据文件不存在: {fact_file}\n请确保文件路径正确。")

    print(f"正在加载 fact 数据: {fact_file}")
    data = []
    with open(fact_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line.strip()))
    print(f"✓ 成功加载 {len(data)} 条 fact 数据")
    return data


def main():
    """
    主函数: 初始化并运行整个预测流程。
    """
    preprocessed_file = "extracted_info_fusai1.json"
    fact_file = "data/zp.jsonl"
    output_file = "result/submission_with_rules_fact_1125_fraud.jsonl"

    print("=" * 60)
    print(" 法律量刑预测系统 (规则化 Task2 版) ")
    print("=" * 60)

    # 优先使用 fact 格式数据
    if os.path.exists(fact_file):
        print(f"检测到 fact 格式数据文件: {fact_file}")
        try:
            fact_data = load_fact_data(fact_file)
        except Exception as e:
            print(f"\n加载 fact 数据时发生致命错误: {e}")
            return

        print("\n" + "=" * 60)
        print("开始模型预测...")
        print("=" * 60 + "\n")

        predictor = SentencingPredictor()
        results = predictor.process_fact_data(fact_data, output_file)

        print("\n" + "=" * 60)
        print("✓ 任务完成!")
        print(f"✓ 共处理 {len(results)} 条数据")
        print(f"✓ 结果已成功保存至: {output_file}")
        print("=" * 60)
        return

    # 否则退回使用预处理文件
    try:
        preprocessed_data = load_preprocessed_data(preprocessed_file)
    except Exception as e:
        print(f"\n加载数据时发生致命错误: {e}")
        return

    print("\n" + "=" * 60)
    print("开始模型预测...")
    print("=" * 60 + "\n")

    predictor = SentencingPredictor()
    results = predictor.process_all_data(preprocessed_data, output_file)

    print("\n" + "=" * 60)
    print("✓ 任务完成!")
    print(f"✓ 共处理 {len(results)} 条数据")
    print(f"✓ 结果已成功保存至: {output_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
