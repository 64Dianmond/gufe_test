import json
import os
import re
from openai import OpenAI
from dotenv import load_dotenv
from cal_dq import SentencingCalculator, SENTENCING_TOOLS, execute_tool_call

# 加载环境变量
load_dotenv()


class SentencingPredictor:
    """
    一个基于大型语言模型的法律量刑预测器。
    采用"提取-注入-计算"的三步混合法，并集成了权威的、分层的量刑计算规则。
    支持工具调用，使用专业计算器进行精确的刑期计算。
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
        self.temperature_task1 = 0.1  # Task1使用较高温度以增加多样性
        self.temperature_task2 = 0.1  # Task2使用较低温度以确保稳定性
        self.max_tokens = 32768

    def identify_crime_type(self, defendant_info, case_description):
        """
        增强版的罪名识别函数。
        优先从指控中识别,其次通过关键词匹配。
        """
        text = defendant_info + case_description
        text = text.replace(" ", "").replace("\n", "")

        # 1. 优先匹配指控罪名,这是最准确的方式
        charge_match = re.search(r'(因涉嫌|指控犯)(.*?)罪', text)
        if charge_match:
            crime = charge_match.group(2)
            if "盗窃" in crime: return "盗窃罪"
            if "故意伤害" in crime: return "故意伤害罪"
            if "诈骗" in crime: return "诈骗罪"
            if "职务侵占" in crime: return "职务侵占罪"

        # 2. 如果指控不明确,使用关键词作为备用方案
        theft_keywords = ["盗窃", "窃取", "扒窃", "盗走"]
        injury_keywords = ["故意伤害", "殴打", "打伤", "轻伤", "重伤"]
        fraud_keywords = ["诈骗", "骗取", "虚构事实"]
        embezzlement_keywords = ["职务侵占", "挪用资金", "非法占有"]

        if any(k in text for k in theft_keywords): return "盗窃罪"
        if any(k in text for k in injury_keywords): return "故意伤害罪"
        if any(k in text for k in fraud_keywords): return "诈骗罪"
        if any(k in text for k in embezzlement_keywords): return "职务侵占罪"

        # 3. 默认回退,根据数据集的多数罪名来定,此处以盗窃罪为例
        return "盗窃罪"

    def extract_region(self, defendant_info, case_description):
        """
        从案件信息中提取地区信息
        """
        text = defendant_info + case_description
        # 常见的地区关键词
        regions = ["北京", "上海", "天津", "重庆", "河北", "山西", "辽宁", "吉林",
                   "黑龙江", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南",
                   "湖北", "湖南", "广东", "海南", "四川", "贵州", "云南", "陕西",
                   "甘肃", "青海", "台湾", "内蒙古", "广西", "西藏", "宁夏", "新疆",
                   "香港", "澳门"]

        # 常见的城市关键词
        cities = ["江门", "深圳", "广州", "珠海", "佛山", "东莞", "中山", "杭州",
                  "宁波", "温州", "嘉兴", "绍兴", "台州", "义乌", "南京", "苏州",
                  "无锡", "常州", "徐州", "济南", "青岛", "烟台", "潍坊", "大连",
                  "沈阳", "哈尔滨", "长春", "成都", "西安", "武汉", "长沙", "福州",
                  "厦门", "贵阳", "昆明", "南宁", "石家庄", "太原", "南昌", "合肥",
                  "郑州", "海口", "乌鲁木齐", "呼和浩特", "银川", "西宁", "拉萨", "兰州"]

        # 先尝试查找省份
        for region in regions:
            if region in text:
                return region

        # 如果没有找到省份，尝试查找城市
        for city in cities:
            if city in text:
                return city

        # 如果没有找到明确的地区，返回默认值
        return "default"

    def build_prompt_task1_authoritative(self, defendant_info, case_description):
        """
        构建权威版的量刑情节提取Prompt (Task 1)。
        Prompt内容严格依据官方量刑指导意见中的情节分类。
        """
        crime_type = self.identify_crime_type(defendant_info, case_description)

        # 获取地区信息
        region = self.extract_region(defendant_info, case_description)

        # 构建地区特定的数额标准说明
        amount_standards = self._get_amount_standards_for_prompt(crime_type, region)

        prompt = f"""你是一位极其严谨的刑事法官。你的任务是阅读案件事实,按照中国刑法以及量刑指导意见,从中**系统、完整且准确地**提取所有对量刑有影响的关键情节。

请在内部按如下两个阶段进行推理,但最终**只输出最后的情节标签 JSON 数组**,不要展示你的推理过程。

【评测说明】不大本任务用 F1 值进行评测,需要在"准确"和"完整"之间取得平衡:
- 不允许凭空捏造情节,也不允许与案情矛盾;
- 对于案情中已经**明确记载或可以直接、唯一推导出来**的情节,应当尽可能完整地提取,避免遗漏。

-------------------------
【阶段一(在你内部进行,不要输出): 事实要点梳理】

围绕以下问题,在你内部整理一个"事实要点表"(不要输出):

1. 数额与次数
- 涉案金额是多少? 是既遂还是未遂?
- 有几次盗窃/诈骗/犯罪行为? 原文如何表述?

2. 手段与客体
- 是否提到特定犯罪方式: 入户盗窃、扒窃、携带凶器盗窃、电信网络诈骗等?
- 是否有故意伤害致轻伤/重伤/死亡的结果?

3. 被告人人身情况与前科
- 是否有前科? 前科是指被告人在本案之前因犯罪受过刑罚处罚的经历。
- 能否构成累犯?构成累犯的法律条件为：在前罪刑罚执行完毕或赦免后5年内，再犯应当判处有期徒刑以上刑罚之罪。
- 案件一旦依法认定被告人为累犯，在量刑时仅以“累犯”作为从重情节予以评价。对已作为累犯基础的同一前科，不得再单独作为“有前科”的独立从重情节进行叠加评价，以避免重复评价
- 请严肃区分累犯与前科。

4. 归案经过与供述情况
- 是抓捕归案,还是主动投案?
- 是否如实供述自己的罪行(坦白)?
- 是否在庭审或侦查阶段认罪认罚?

5. 退赃、退赔与谅解
- 是否退赃/退赔? 退赔数额是多少?
- 是否取得被害人的谅解(有无明确记载)?

6. 其他
- 是否有"多次盗窃"的表述?二年内盗窃三次以上即构成“多次盗窃”，不论每次数额是否达到当地“数额较大”的起点，也无需累计金额达标，只要满三次就多次盗窃
- 是否有未成年人、从犯、犯罪未遂、中止、防卫过当等典型法定减轻或从重情节?
- 是否有主犯情节?
- 是否是主犯、是否有教唆他人犯罪等情节?
- 是否针对弱势群体(老年人、残疾人、未成年人等)实施犯罪?
- 是否在重大灾害期间实施犯罪?

-------------------------
【阶段二(需要输出): 将事实映射为标准化情节标签】

根据你在阶段一梳理的事实,使用**下面给定的固定模版**输出情节标签。禁止使用未列出的新表述。

1. 数额与后果类(根据罪名选择)——金额必须来自原文:
- "盗窃金额既遂XXXX元" / "盗窃金额未遂XXXX元"
- "诈骗金额既遂XXXX元" / "诈骗金额未遂XXXX元"
- "职务侵占金额既遂XXXX元"
- "故意伤害致X人轻伤"
- "故意伤害致X人重伤X级"
- "故意伤害致X人死亡"

2. 数额档次(必须严格按照下面提供的地区标准来判断，并且只有在可以唯一确定时才输出):
- "盗窃数额较大" / "盗窃数额巨大" / "盗窃数额特别巨大"
- "诈骗数额较大" / "诈骗数额巨大" / "诈骗数额特别巨大"
- "职务侵占数额较大" / "职务侵占数额巨大" / "职务侵占数额特别巨大"

**数额判断标准（基于案件地区）**:
{amount_standards}

3. 次数与多次犯罪:
- "盗窃次数X次"
- "诈骗次数X次"
- "多次盗窃"
- "多次诈骗"
- "多次犯罪"

4. 犯罪手段/方式(仅当案情有明确记载时使用,表述要贴近原文):
- "入户盗窃"
- "扒窃"
- "携带凶器盗窃"
- "电信网络诈骗"
- 其他类似特殊方式,仅在原文明确出现时使用。

5. 法定从重、从轻、减轻情节(只要构成,即使没有写出"从重/从轻"字样,也要输出):
- "累犯"
- "自首"
- "立功"
- "重大立功"
- "未成年人犯罪"
- "从犯"
- "胁从犯"
- "主犯"
- "犯罪预备"
- "犯罪中止"
- "犯罪未遂"

6. 酌定量刑情节:
- "坦白"               # 被动到案后如实供述自己罪行
- "认罪认罚"           # 自愿认罪并同意签署具结书
- "退赔XXXX元" / "退赃XXXX元" / "退赔全部损失"
- "取得谅解"
- "前科"
- "被害人过错"
- "多次盗窃"
- "多次诈骗"
- "多次犯罪"


7. 法定减轻标签:
- 如果存在"自首、立功/重大立功、未成年人犯罪、从犯/胁从犯、主犯、犯罪预备、中止、未遂、防卫过当"等任意一种,请在输出数组中额外加入一个标签: "法定减轻"。

【严格限制】
- 金额、次数等数字必须与案情原文完全一致。
- 如果某类信息原文完全没有,就不要输出该类标签。
- 如果两个标签含义完全重复,只保留一种最标准表达。

-------------------------
【案件信息】
案情描述: {case_description}
本案罪名(初步判断): {crime_type}
案件地区: {region}

-------------------------
【最终输出格式要求】

- 最终只输出一个 JSON 数组, 例如:
  ["盗窃金额既遂3631元", "盗窃次数1次", "盗窃数额较大", "扒窃", "当庭自愿认罪", "前科"]
- 不要输出任何解释、分析过程或 Markdown。
- 不要输出键名、字段名, 也不要套一层对象, 直接输出数组本身。

"""
        return prompt

    def _get_amount_standards_for_prompt(self, crime_type, region):
        """
        根据罪名和地区的数额标准生成提示信息
        """
        # 导入计算器中的标准
        from cal_dq import SentencingCalculator

        # 获取地区标准
        if region in SentencingCalculator.REGIONAL_STANDARDS:
            standards = SentencingCalculator.REGIONAL_STANDARDS[region]
        elif region in SentencingCalculator.REGIONAL_STANDARDS.get("cities_to_provinces", {}):
            province = SentencingCalculator.REGIONAL_STANDARDS["cities_to_provinces"][region]
            standards = SentencingCalculator.REGIONAL_STANDARDS[province]
        else:
            standards = SentencingCalculator.REGIONAL_STANDARDS["default"]

        # 生成提示文本
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
            # 默认标准
            return """**全国通用数额标准参考:**
- **盗窃罪**:
  - 数额较大: 1000元以上不满30000元
  - 数额巨大: 30000元以上不满300000元
  - 数额特别巨大: 300000元以上
- **诈骗罪**:
  - 数额较大: 3000元以上不满30000元
  - 数额巨大: 30000元以上不满500000元
  - 数额特别巨大: 500000元以上"""

    def build_prompt_task2_with_tools(self, defendant_info, case_description, sentencing_factors):
        """
        构建支持工具调用的刑期预测Prompt (Task 2)。
        模型将使用计算器工具进行精确的刑期计算。
        """
        # 判断是否有法定减轻情节
        statutory_mitigation_keywords = [
            "自首", "立功", "重大立功",
            "未成年人", "已满十四周岁不满十八周岁",
            "从犯", "胁从犯",
            "犯罪中止", "犯罪未遂", "犯罪预备",
            "防卫过当", "避险过当",
            "七十五周岁", "75周岁"
        ]
        has_statutory = any(kw in str(sentencing_factors) for kw in statutory_mitigation_keywords)

        crime_type = self.identify_crime_type(defendant_info, case_description)
        factors_str = "\n- ".join(sentencing_factors)

        # 提取金额用于计算
        amount = None
        for factor in sentencing_factors:
            if "盗窃金额既遂" in factor or "诈骗金额既遂" in factor:
                # 确保我们提取的是盗窃或诈骗金额，而不是退赔金额
                if "退赔" not in factor and "退赃" not in factor:
                    try:
                        amount = float(re.search(r'(\d+\.?\d*)元', factor).group(1))
                    except:
                        pass
                    break

        # 提取地区信息
        region = self.extract_region(defendant_info, case_description)

        prompt = f"""你是一位精通量刑计算的刑事法官。你必须使用提供的专业计算器工具来进行精确计算,不要自己估算数值。
 **重要约束条件:**
    1. 总调节减轻幅度原则上不得超过基准刑的50%(除非有法定减轻情节)
    2. 本案{'有' if has_statutory else '无'}法定减轻情节

**已认定的量刑情节:**
- {factors_str}

**案件地区:** {region}

**你的任务:**
严格按照以下步骤使用工具进行计算:

**步骤1: 计算基准刑**
首先，根据已提取的量刑情节和案件信息，使用 `calculate_base_sentence` 工具计算基准刑（单位：月）。
- 传入参数包括：罪名（crime_type）、涉案金额（amount）、地区（region）等；注意，退赔金额不作为涉案金额（amount）
- 对于盗窃罪，还需要传入相应的次数参数（theft_count）；
- 工具会根据地区性的数额标准以及罪名相关的量刑规范，计算出准确的基准刑月份。

**步骤2: 分析和分层情节**
从上述情节中,识别:
- **第一层面情节(连乘)**: 未成年人、从犯、胁从犯、犯罪预备、犯罪中止、犯罪未遂
- **第二层面情节(加减)**: 累犯、自首、坦白、立功、认罪认罚、退赔、取得谅解、前科、多次盗窃、多次犯罪

**标准调节比例参考:**

【法定从重情节】
- 累犯: 1.30 (增加30%)

【酌定从重情节】
- 前科: 1.10(增加10%)
- 犯罪对象为弱势群体: 1.10 (增加10%)
- 重大灾害期间犯罪: 1.20 (增加20%)
- 多次盗窃/多次诈骗/多次犯罪: 1.13 (增加13%)
- 入户盗窃: 1.30 (增加30%)
- 携带凶器盗窃: 1.2(增加20%)
- 扒窃: 1.1(增加10%)
- 主犯: 1.25(增加25%)
- 教唆未成年人犯罪: 1.2 (增加20%)

【法定从轻、减轻情节】
- 未成年人: 0.7 (减30%)
- 从犯: 0.9 (减10%)
- 胁从犯: 0.8 (减20%)
- 犯罪预备: 0.5 (减半)
- 犯罪中止: 0.5 (减半)
- 犯罪未遂: 0.5 (减50%)

【酌定从轻情节】
- 自首: 0.75 (减25%)
- 坦白: 0.75 (减75%)
- 立功: 0.8 (减20%)
- 重大立功: 0.5 (减半)
- 认罪认罚: 0.95 (减5%)
- 退赃/退赔: 0.75 (减75%)
- 取得谅解: 0.90 (减10%)


**步骤3: 计算最终刑期**
- 使用 `calculate_layered_sentence_with_constraints` 工具
- 传入基准刑、罪名、金额、第一层面情节列表、第二层面情节列表和是否有法定减轻情节
- 注意：第一层面和第二层面情节需要以如下格式传入：
  第一层面: [{{"name": "从犯", "ratio": 0.9}}]
  第二层面: [{{"name": "自首", "ratio": 0.8}}, {{"name": "认罪认罚", "ratio": 0.95}}, ...]
  重要：确保使用 "name" 字段而不是 "factor" 字段

**步骤4: 生成刑期区间**
- 使用 `months_to_range` 工具
- 将最终月数转换为合理区间

请按顺序调用工具,完成计算后,输出最终的刑期区间。如果刑期区间下限为0，请调整为1
"""
        return prompt

    def predict_task1_authoritative(self, defendant_info, case_description):
        """
        执行Task 1:提取量刑情节。
        """
        prompt = self.build_prompt_task1_authoritative(defendant_info, case_description)
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system",
                     "content": "你是一位经验丰富的刑事法官,精通中国刑法量刑情节认定,对细节极其敏感。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature_task1,  # Task1使用较高温度
                max_tokens=self.max_tokens
            )
            result_text = response.choices[0].message.content.strip()

            # 使用正则表达式从文本中提取JSON数组
            json_match = re.search(r'\[.*?\]', result_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            else:
                print(f"警告 (Task 1): 未能在输出中找到JSON数组。返回: {result_text}")
                return ["盗窃数额较大"]  # Fallback
        except Exception as e:
            print(f"错误 (Task 1): API调用或JSON解析失败: {e}")
            return ["盗窃数额较大"]  # Fallback

    def predict_task2_with_tools(self, defendant_info, case_description, sentencing_factors):
        """
        执行Task 2:使用工具调用进行刑期预测。
        """
        if not sentencing_factors:
            sentencing_factors = ["犯罪情节较轻"]

        prompt = self.build_prompt_task2_with_tools(defendant_info, case_description, sentencing_factors)

        messages = [
            {"role": "system",
             "content": "你是一位刑事法官,必须使用提供的计算器工具进行精确计算,不要自己估算数值。请根据案件信息判断案件所在地区，如无法判断则使用默认标准。"},
            {"role": "user", "content": prompt}
        ]

        # 多轮对话处理工具调用
        max_iterations = 10
        final_range = None

        for iteration in range(max_iterations):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    tools=SENTENCING_TOOLS,
                    temperature=self.temperature_task2,  # Task2使用较低温度
                    max_tokens=self.max_tokens
                )

                assistant_message = response.choices[0].message

                # 如果没有工具调用,说明完成
                if not assistant_message.tool_calls:
                    content = assistant_message.content
                    print(f"  模型最终回复: {content}")

                    # 从最终响应中提取区间
                    json_match = re.search(r'\[\s*(\d+)\s*,\s*(\d+)\s*\]', content)
                    if json_match:
                        final_range = [int(json_match.group(1)), int(json_match.group(2))]
                        break
                    elif final_range:  # 如果之前已经计算出了区间
                        break
                    else:
                        print(f"警告: 未找到刑期区间,使用默认值")
                        return [6, 12]

                # 添加助手消息
                messages.append({
                    "role": "assistant",
                    "content": assistant_message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        } for tc in assistant_message.tool_calls
                    ]
                })

                # 执行工具调用
                for tool_call in assistant_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)

                    print(f"  🔧 调用工具: {function_name}")
                    print(f"     参数: {json.dumps(function_args, ensure_ascii=False)}")

                    # 特殊处理：在调用calculate_base_sentence时，提取盗窃次数参数
                    if function_name == "calculate_base_sentence" and "crime_type" in function_args and function_args["crime_type"] == "盗窃罪":
                        # 从量刑情节中提取盗窃次数
                        theft_count = None
                        for factor in sentencing_factors:
                            if "盗窃次数" in factor:
                                try:
                                    theft_count = int(re.search(r'盗窃次数(\d+)次', factor).group(1))
                                    break
                                except:
                                    pass

                        if theft_count is not None:
                            function_args["theft_count"] = theft_count
                            print(f"     添加盗窃次数参数: {theft_count}")
                        
                        # 如果没有盗窃金额，确保amount为None而不是默认值
                        if "amount" not in function_args:
                            function_args["amount"] = None

                    # 特殊处理：在调用calculate_base_sentence时，提取诈骗次数参数
                    if function_name == "calculate_base_sentence" and "crime_type" in function_args and function_args["crime_type"] == "诈骗罪":
                        # 从量刑情节中提取诈骗次数
                        fraud_count = None
                        for factor in sentencing_factors:
                            if "诈骗次数" in factor:
                                try:
                                    fraud_count = int(re.search(r'诈骗次数(\d+)次', factor).group(1))
                                    break
                                except:
                                    pass

                        if fraud_count is not None:
                            function_args["fraud_count"] = fraud_count
                            print(f"     添加诈骗次数参数: {fraud_count}")
                        
                        # 如果没有诈骗金额，确保amount为None而不是默认值
                        if "amount" not in function_args:
                            function_args["amount"] = None

                    # 执行工具
                    function_response = execute_tool_call(function_name, function_args)
                    print(f"     结果: {function_response}")

                    # 检查是否是最终的区间结果
                    if function_name == "months_to_range":
                        try:
                            result_data = json.loads(function_response)
                            if "range" in result_data:
                                final_range = result_data["range"]
                        except:
                            pass

                    # 添加工具响应
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": function_response
                    })

            except Exception as e:
                print(f"工具调用错误: {e}")
                return [6, 12]  # Fallback

        if final_range:
            return final_range
        else:
            print("警告: 达到最大迭代次数但未获得结果")
            return [6, 12]  # Fallback

    def process_all_data(self, preprocessed_data, output_file):
        """
        主处理流程:遍历所有数据,执行两阶段预测,并保存结果。
        """
        results = []

        for idx, item in enumerate(preprocessed_data):
            print(f"\n{'=' * 60}")
            print(f"处理第 {idx + 1}/{len(preprocessed_data)} 条数据 (ID: {item['id']})")
            print(f"{'=' * 60}")

            answer1, answer2 = [], []
            try:
                # 第一步:调用权威版 Task 1 预测,提取量刑情节
                print("\n【步骤1: 提取量刑情节】")
                answer1 = self.predict_task1_authoritative(
                    item['defendant_info'],
                    item['case_description']
                )
                print(f"✓ 提取到的情节: {answer1}")

                # 第二步:使用工具调用进行刑期预测
                print("\n【步骤2: 使用工具计算刑期】")
                answer2 = self.predict_task2_with_tools(
                    item['defendant_info'],
                    item['case_description'],
                    answer1,
                )
                print(f"✓ 预测刑期区间: {answer2}")

            except Exception as e:
                print(f"!!! 处理ID {item['id']} 时发生未知严重错误: {e}")
                answer1 = answer1 if answer1 else ["盗窃数额较大"]
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

            # 每处理10条数据保存一次,防止意外中断丢失进度
            if (idx + 1) % 1 == 0:
                print(f"\n--- 进度保存:已处理 {idx + 1} 条数据 ---")
                self._save_results(results, output_file)

        # 最终保存所有结果
        self._save_results(results, output_file)
        print(f"\n所有数据处理完成,结果已保存至: {output_file}")
        return results

    def process_fact_data(self, fact_data, output_file):
        """
        处理fact格式的数据（新格式）
        """
        results = []

        for idx, item in enumerate(fact_data):
            print(f"\n{'=' * 60}")
            print(f"处理第 {idx + 1}/{len(fact_data)} 条数据 (ID: {item['id']})")
            print(f"{'=' * 60}")

            answer1, answer2 = [], []
            try:
                # 第一步:调用权威版 Task 1 预测,提取量刑情节
                print("\n【步骤1: 提取量刑情节】")
                answer1 = self.predict_task1_authoritative(
                    "",  # 被告人信息为空
                    item['fact']  # 使用fact字段作为案情描述
                )
                print(f"✓ 提取到的情节: {answer1}")

                # 第二步:使用工具调用进行刑期预测
                print("\n【步骤2: 使用工具计算刑期】")
                # 从案件信息中提取地区
                answer2 = self.predict_task2_with_tools(
                    "",  # 被告人信息为空
                    item['fact'],  # 使用fact字段作为案情描述
                    answer1,
                )
                print(f"✓ 预测刑期区间: {answer2}")

            except Exception as e:
                print(f"!!! 处理ID {item['id']} 时发生未知严重错误: {e}")
                answer1 = answer1 if answer1 else ["盗窃数额较大"]
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

            # 每处理10条数据保存一次,防止意外中断丢失进度
            if (idx + 1) % 1 == 0:
                print(f"\n--- 进度保存:已处理 {idx + 1} 条数据 ---")
                self._save_results(results, output_file)

        # 最终保存所有结果
        self._save_results(results, output_file)
        print(f"\n所有数据处理完成,结果已保存至: {output_file}")
        return results

    def _save_results(self, results, output_file):
        """
        将结果以jsonl格式保存到文件。
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
    加载fact格式的数据文件。
    """
    if not os.path.exists(fact_file):
        raise FileNotFoundError(f"错误:数据文件不存在: {fact_file}\n请确保文件路径正确。")

    print(f"正在加载fact数据: {fact_file}")
    data = []
    with open(fact_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line.strip()))
    print(f"✓ 成功加载 {len(data)} 条fact数据")
    return data


def main():
    """
    主函数:初始化并运行整个预测流程。
    """
    # 配置文件路径
    preprocessed_file = "extracted_info_fusai1.json"
    fact_file = "data/dq.jsonl"
    output_file = "result/submission_with_tools_fact_1124_month6-12.jsonl"

    print("=" * 60)
    print(" 法律量刑预测系统 (工具调用版) ")
    print("=" * 60)

    # 检查fact文件是否存在
    if os.path.exists(fact_file):
        print(f"检测到fact格式数据文件: {fact_file}")
        try:
            fact_data = load_fact_data(fact_file)
        except Exception as e:
            print(f"\n加载fact数据时发生致命错误: {e}")
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

    # 如果没有fact文件，则尝试加载预处理文件
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