import json
import os
import re
from openai import OpenAI
from dotenv import load_dotenv
from cal_zp import SENTENCING_TOOLS, execute_tool_call,SentencingCalculator

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
        self.temperature_task1 = 0.1 # Task1使用较高温度以增加多样性
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
        crime_type = "诈骗罪"
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

    def _get_amount_standards_for_prompt(self, crime_type, region):
        """
        根据罪名和地区的数额标准生成提示信息
        """
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

        # 特殊处理：如果诈骗次数>=3次，添加"多次诈骗"情节
        if crime_type == "诈骗罪":
            for factor in sentencing_factors:
                if "诈骗次数" in factor:
                    try:
                        fraud_count = int(re.search(r'诈骗次数(\d+)次', factor).group(1))
                        if fraud_count >= 3 and "多次诈骗" not in sentencing_factors:
                            sentencing_factors.append("多次诈骗")
                            factors_str = "\n- ".join(sentencing_factors)
                        break
                    except:
                        pass

        prompt = f"""你是一位精通量刑计算的刑事法官。你必须使用提供的专业计算器工具来进行精确计算, 任何涉及加减乘除的数值运算都不能凭心算或估计。

        **重要束条件:**
        1. 所有数值运算(金额折算、比例乘法、年/月换算等)都要调用计算器工具完成。
        2. 总体从轻调节幅度原则上不得超过基准刑的 50%(除非存在法定减轻情节且情节明显, 确有必要突破)。
        3. 本案{'有' if has_statutory else '无'}法定减轻情节。
        4. 金额、数额档次、犯罪次数等**已经在确定基准刑时充分考虑**, 在后续调节环节**不要重复评价**。

        **已认定的量刑情节(来自 Task1 的输出):**
        {factors_str}

        **案件地区:** {region}

        请严格按照以下 4 个步骤完成计算:

        ------------------------------------------------
        **步骤1: 计算基准刑(月数)**
        
        首先，根据已提取的量刑情节和案件信息，使用 `calculate_base_sentence` 工具计算基准刑（单位：月）。

        - 传入参数包括：罪名（crime_type）、涉案金额（amount）、地区（region）等；
        - 对于诈骗罪，还需要传入相应的次数参数（fraud_count）；
        - 工具会根据地区性的数额标准以及罪名相关的量刑规范，计算出准确的基准刑月份。

        ------------------------------------------------
        **步骤2: 识别量刑情节并分层**

        请从 {factors_str} 中抽取、归类量刑情节, 并且**统一映射为标准名称**, 分成两个层次:

        1. **第一层面情节(连乘, 法定减轻/法定从轻优先处理)**:
           - 未成年人犯罪 → "未成年人"
           - 从犯 → "从犯"
           - 胁从犯 → "胁从犯"
           - 犯罪预备 → "犯罪预备"
           - 犯罪中止 → "犯罪中止"
           - 犯罪未遂 → "犯罪未遂"

        2. **第二层面情节(在第一层面处理完成后的加减)**:
           - 累犯
           - 自首
           - 坦白
           - 立功 / 重大立功
           - 认罪认罚
           - 退赃/退赔(包括 “退赔XXXX元”“退赃XXXX元”“退赔全部损失”等标签)
           - 取得谅解
           - 前科(仅在未构成累犯时使用)
           - 多次诈骗
           - 电信网络诈骗
           - 主犯
           - 犯罪对象为弱势群体(如“针对老年人实施诈骗”)
           - 重大灾害期间犯罪

        【映射规则举例】:
        - 任何以“退赔”“退赃”开头的标签都归入“退赃/退赔”情节;
        - “针对老年人实施诈骗”等归入“犯罪对象为弱势群体”;
        - 若存在“累犯”, 不再把同一前案单独作为“前科”再次从重;
        - 已用于确定基准刑的“数额档次”“次数”不要再当作第二层面情节;
        - 当诈骗次数大于等于3次时，应添加“多次诈骗”情节到第二层面。

        ------------------------------------------------
        **步骤3: 选择调节比例, 调用分层计算工具**

        先为每个情节选择一个合理的调节系数 ratio, 再调用 `calculate_layered_sentence_with_constraints` 工具。
        使用下面的标准比例:

        【法定从重情节】(通常放在第二层面)
        - 累犯: 1.20   # 增加20%

        【酌定从重情节】
        - 前科: 1.10                      # 增加10%
        - 犯罪对象为弱势群体: 1.10        # 增加10%
        - 重大灾害期间犯罪: 1.20          # 增加20%
        - 多次诈骗: 1.15 # 增加15%
        - 电信网络诈骗: 1.30              # 增加30%
        - 主犯: 1.25                      # 增加25%

        【法定从轻、减轻情节】(第一层面, 按顺序连乘)
        - 未成年人: 0.70   # 降低30%
        - 从犯: 0.90       # 降低10%
        - 胁从犯: 0.80     # 降低20%
        - 犯罪预备: 0.50   # 减半
        - 犯罪中止: 0.50   # 减半
        - 犯罪未遂: 0.50   # 减半

        【酌定从轻情节】(第二层面, 在第一层结果基础上连续微调)
        - 自首: 0.75      # 降25%
        - 坦白: 0.80      # 降低20%
        - 立功: 0.80      # 降低20%
        - 重大立功: 0.50  # 减半
        - 认罪认罚: 0.95  # 降低5%
        - 退赃/退赔: 0.85 # 降低15%
        - 取得谅解: 0.95 # 降低5%

        【重要约束】:
        - 第一层面情节: 在基准刑基础上**依次连乘**其 ratio;
        - 第二层面情节: 在第一层面结果基础上继续按比例连续调节;
        - 第一层面 + 第二层面合并后的总从轻幅度, 原则上不得超过基准刑的 50%。如本案{'有' if has_statutory else '无'}法定减轻情节且情节显著, 才可以适度突破, 但也要保持合理。

        在完成情节识别与比例选择后:

        1. 组装第一层面情节列表, 格式如:
           第一层面 = [{{"name": "从犯", "ratio": 0.9}}, {{"name": "犯罪未遂", "ratio": 0.5}}]

        2. 组装第二层面情节列表, 格式如:
           第二层面 = [{{"name": "自首", "ratio": 0.75}}, {{"name": "认罪认罚", "ratio": 0.95}}, ...]

        3. 使用 `calculate_layered_sentence_with_constraints` 工具:
           - 传入: 基准刑(月数)、罪名、总金额、第一层面情节列表、第二层面情节列表、是否有法定减轻情节;
           - 让工具在内部检查并保证“总减轻幅度原则上不超过基准刑 50%”这一束条件。

        工具返回**最终折算的刑期月数**。

        ------------------------------------------------
        **步骤4: 生成刑期区间**

        1. 使用 `months_to_range` 工具, 将最终刑期月数转换为一个合理区间 [下限, 上限]:
           - 一般案件可在最终月数上下各浮动 3~6 个月形成区间;
           - 情节复杂、量刑不确定性较大的案件, 区间可以适当加宽, 但总宽度一般控制在 6~18 个月内;
           - 如果计算得到的区间下限小于或等于 0, 请将下限调整为 1。

        2. 最终只输出刑期区间, 例如:
           [32, 38]

        不要输出任何解释性文字。
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
                    if function_name == "calculate_base_sentence" and "crime_type" in function_args and function_args[
                        "crime_type"] == "盗窃罪":
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
                    if function_name == "calculate_base_sentence" and "crime_type" in function_args and function_args[
                        "crime_type"] == "诈骗罪":
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
    fact_file = "../data/zp.jsonl"
    output_file = "../result/submission_with_tools_fact_1125_2.jsonl"

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