import json
import os
import re
from openai import OpenAI
from dotenv import load_dotenv
from cal_gysh import SentencingCalculator, SENTENCING_TOOLS, execute_tool_call

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
        self.temperature_task1 = 1.0 # Task1使用较高温度以增加多样性
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
        return "故意伤害罪"

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
        构建故意伤害罪量刑情节提取Prompt (Task 1)。
        """
        crime_type = self.identify_crime_type(defendant_info, case_description)
        region = self.extract_region(defendant_info, case_description)

        prompt = f"""你是一名只负责【故意伤害罪】的量刑情节标注员，只做“看文书→打标签”的工作，不做复杂法理推理。

        目标是在不胡编乱造的前提下，**优先保证标签准确和与标注体系的一致性，其次再考虑不要漏掉特别明显、容易识别的情节**。对于边界模糊、把握不大的情节，宁可不标，也不要勉强输出。

        -------------------------
        【一、内部阅读要点（不要输出）】

        请围绕以下几点在心里先读一遍案情：

        1. 伤害结果（本罪最重要）
           - 有几名被害人实际受伤？
           - 有无“经鉴定”“构成轻伤/重伤/死亡”的表述？
           - 是否有“轻伤一级/轻伤二级/重伤二级/死亡”等明确结论？
           - 对于同一被害人，如文书中写明多处损伤、不同伤情等级，要注意是否有“综合评定为××伤”“损伤程度为××”等最终结论。

        2. 到案方式与供述
           - 是否出现“自动投案”“到公安机关投案”“主动到案”“投案自首”等表述？
           - 是否出现“如实供述自己的罪行”“如实供述主要犯罪事实”“供认不讳”“供述”“供述自己的犯罪事实”等？

        3. 认罪认罚
           - 是否出现“认罪认罚”“签署认罪认罚具结书”
           - 或“对指控事实、罪名及量刑建议无异议并愿意接受处罚”等固定用语？

        4. 赔偿与谅解
           - **本任务中一律不输出任何赔偿类标签**，即使文书写明赔偿金额或“全部赔偿”等表述，也不要输出"赔偿XXXX元"或"赔偿全部损失"。
           - 是否写明“取得被害人谅解”“达成和解并表示谅解”“出具谅解书”等？

        5. 前科 / 累犯
           - 是否写明：曾因××罪被判处有期徒刑、拘役等并服刑？
           - 是否有“系累犯”“构成累犯”的明确认定用语？

        6. 其他与故意伤害罪相关的典型情节
           - 是否有“防卫过当”“正当防卫中超过必要限度”等用语？
           - 是否说明被害人先动手、辱骂、挑衅、酗酒滋事等明显过错？
           - 是否有“再次殴打”“又持××殴打”等可以看出多次伤害同一人的情形？

        -------------------------
        【二、只能使用的固定标签】

        你只能从下列标签中选择，不能创造新标签或改写标签：

        1. 伤害结果类（故意伤害罪 **几乎必有一类**）
           - "故意伤害致1人轻伤一级"
           - "故意伤害致1人轻伤二级"
           - "故意伤害致1人轻伤"      # 无一级/二级区分时使用
           - "故意伤害致1人重伤一级"
           - "故意伤害致1人重伤二级"
           - "故意伤害致1人死亡"

           如有多名被害人、不同伤情，可分别标注，例如：
           ["故意伤害致1人重伤二级", "故意伤害致1人轻伤一级"]

           【特别提醒】
           - 同一名被害人即使有多处损伤、并在文书中出现不同伤情等级描述（例如既有重伤又有轻伤），也只按该被害人的**最高伤情等级**标注 1 个结果标签。
           - 不要为同一被害人同时打“轻伤”“重伤”等多个结果标签。

        2. 行为方式类
           - "多次伤害"      

        3. 法定从轻/减轻情节
           - "自首"
           - "立功"
           - "重大立功"
           - "未成年人犯罪"
           - "从犯"
           - "胁从犯"
           - "主犯"
           - "防卫过当"
           - "避险过当"

        4. 酌定情节
           - "坦白"
           - "认罪认罚"
           - "取得谅解"
           - "前科"
           - "累犯"
           - "被害人过错"

        【评测专用说明：本任务中**一律不输出任何赔偿类标签**，即使文书写明赔偿金额或“全部赔偿”等表述，也不要输出"赔偿XXXX元"或"赔偿全部损失"。】

        -------------------------
        【三、关键判定规则（针对故意伤害罪，务必遵守）】

        1. 关于“自首”“坦白”“认罪认罚”的关系（**自首与坦白不可同时出现**）

           - 自首：
             - 只有同时出现“主动到案（自动投案、投案自首、到公安机关投案等）” + “如实供述自己的罪行”时，才标注“自首”。
             - 一旦案件符合“自首”条件并已经标注"自首"，**同一案件中不得再标注"坦白"**。

           - 坦白：
             - **本任务中，在不构成“自首”的前提下，只要文书中出现与“供述”相关的表述，即视为“坦白”的线索。**
               例如包括但不限于：“供述”“如实供述自己的罪行”“如实供述主要犯罪事实”“供述自己的犯罪事实”“对指控事实供认不讳”等。
             - 若不满足“自首”认定条件（如系被动到案、抓获归案等），但出现上述任何“供述”类表述，则标注“坦白”。
             - **“自首”和“坦白”两个标签在同一案件中是互斥的：要么“自首”，要么“坦白”，不得同时出现。**

           - 认罪认罚：
             - 只要出现“认罪认罚”“签署认罪认罚具结书”“对指控事实、罪名及量刑建议无异议并愿意接受处罚”等典型表述，就标注"认罪认罚"。
             - 可以与“自首”并存，也可以与“坦白”并存（但“自首”和“坦白”本身互斥）。

        2. 关于“前科”“累犯”
           - 文书只记载以前有刑罚执行经历，未写“累犯” → 标注"前科"。
           - 明确写“系累犯”“构成累犯” → 至少标注"累犯"；如同时也详细写明前罪判决，可同时保留"前科"和"累犯"。

        3. 关于“被害人过错”“防卫过当”
           - 被害人过错：只有当文书写明被害人先动手、挑衅、辱骂、酗酒滋事等，才标"被害人过错"。
           - 防卫过当：只有明确出现“防卫过当”“正当防卫超过必要限度”等认定语句，才标"防卫过当"。

        4. 关于“多次伤害”
           - 本任务中的“多次伤害”，是对行为人**在事实层面实施了两次及以上相对独立的伤害行为**的概括，并非刑法条文中“多次犯罪”的法定概念。
           - 可以标注“多次伤害”的典型情形（满足任一即可）：
             1）文书中出现明确的次数或反复用语，能够看出多次实施伤害行为，例如：
                “多次殴打被害人”“反复对被害人进行殴打”
                “屡次用拳击打其头面部”
                “再次持木棒殴打”“又持菜刀朝其砍击”等。
             2）事实叙述上存在清晰先后分段，能看出至少两段伤害行为，例如：
                “先是××，后又××殴打”
                “期间离开现场后折返再次殴打”
                “将其拉至楼下后，又在楼道内继续殴打”
                “事后又持刀追砍”等。
           - **仅为单次打斗/殴打过程**的，一般不标“多次伤害”，例如：
             - 只写“用拳打脚踢对其进行殴打”“对被害人头面部连打数拳”，
               虽然动作上有多次击打，但整体是一次连续的殴打行为，
               且文书中没有“多次、反复、再次、又”等用语，也看不出明显分段的，
               原则上不标“多次伤害”。
           - 对同一被害人的多处伤情，或在一次殴打中使用多种方式（拳打、脚踢、拿凳子砸等），
             如整体属于同一时间、同一地点、基于同一犯意的一次连续行为，
             仍视为“一次伤害行为”，**不因多处损伤或多种手段而单独打“多次伤害”标签**。

        5. 关于“单一被害人多处不同伤情等级”的处理
           - 同一名被害人如果存在多处损伤，并在文书中出现不同伤情等级（例如：头部损伤构成重伤二级，四肢损伤构成轻伤二级）：
             - 按司法鉴定或判决书中对该被害人**最终、综合的伤情结论**为准；
             - 在标注时，只以该被害人伤情中的**最高等级**打 1 个结果标签；
               例如：“故意伤害致1人重伤二级”。
           - 不要因为同一名被害人身体上存在多处不同等级的损伤，而为其同时打多个结果标签。

        -------------------------
        【四、输出前的自检】

        在正式输出标签数组前，在心里快速检查：

        - 是否已经至少包含了一个“故意伤害致…伤”的标签？（这是故意伤害罪的核心结果情节）
        - 如有多名被害人，是否分别按各自的最高伤情打标签？
        - 案件中如有明显的“认罪认罚”“谅解”“自首/供述/如实供述”“前科/累犯”等关键词，是否都已经有对应标签？
        - 是否出现了“自首”和“坦白”同时标注的情况？如有，必须改为二者只保留其一。
        - 如果案情明显有谅解，而你只打了 1 个标签，极可能漏标，请回去补充。

        -------------------------
        【案件信息】
        案情描述：{case_description}
        罪名：故意伤害罪

        -------------------------
        【最终输出格式】

        只输出一个 JSON 数组，例如：
        ["故意伤害致1人轻伤二级", "自首", "认罪认罚", "取得谅解"]

        不要输出任何解释文字或Markdown，不要加字段名或嵌套对象。

        """

        return prompt

    def build_prompt_task2_with_tools(self, defendant_info, case_description, sentencing_factors):
        """
        构建故意伤害罪刑期预测Prompt (Task 2)。
        """
        # 判断是否有法定减轻情节
        statutory_mitigation_keywords = [
            "自首", "立功", "重大立功",
            "未成年人", "已满十四周岁不满十八周岁",
            "从犯", "胁从犯",
            "防卫过当", "避险过当",
            "七十五周岁", "75周岁"
        ]
        has_statutory = any(kw in str(sentencing_factors) for kw in statutory_mitigation_keywords)

        crime_type = self.identify_crime_type(defendant_info, case_description)
        factors_str = "\n- ".join(sentencing_factors)

        # 提取伤情等级和受害人数
        injury_level = None
        victim_count = 1  # 默认至少有一个受害者
        
        for factor in sentencing_factors:
            # 提取伤害等级
            if "轻伤一级" in factor:
                injury_level = "轻伤一级"
                break
            elif "轻伤二级" in factor:
                injury_level = "轻伤二级"
                break
            elif "重伤一级" in factor:
                injury_level = "重伤一级"
                break
            elif "重伤二级" in factor:
                injury_level = "重伤二级"
                break
            elif "死亡" in factor:
                injury_level = "致人死亡"
                break
                
        # 提取受害人数
        for factor in sentencing_factors:
            # 匹配"故意伤害致X人..."模式
            match = re.search(r'故意伤害致(\d+)人', factor)
            if match:
                victim_count = int(match.group(1))
                break

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
根据伤害后果确定基准刑:
- 轻伤二级: 12个月
- 轻伤一级: 18个月
- 重伤二级: 48个月
- 重伤一级: 72个月
- 致人死亡: 120个月

使用 `calculate_base_sentence` 工具,传入:
- crime_type: "故意伤害罪"
- injury_level: 伤情等级(如"轻伤二级")
- victim_count: 受害者人数(如2)

**步骤2: 分析和分层情节**
从上述情节中,识别:
- **第一层面情节(连乘)**: 未成年人、从犯、胁从犯、防卫过当、避险过当
- **第二层面情节(加减)**: 累犯、自首、坦白、立功、认罪认罚、赔偿、取得谅解、前科、被害人过错、手段特别残忍、针对弱势群体

**标准调节比例参考:**

【法定从重情节】
- 累犯: 1.30 (增加30%)

【酌定从重情节】
- 前科: 1.10 (增加10%)
- 使用刀具/危险工具: 1.15 (增加15%)
- 手段特别残忍: 1.30 (增加30%)
- 伤害要害部位: 1.15 (增加15%)
- 多次伤害: 1.20 (增加20%)
- 针对弱势群体: 1.15 (增加15%)
- 在公共场所作案: 1.10 (增加10%)
- 主犯: 1.25 (增加25%)

【法定从轻、减轻情节】
- 未成年人: 0.70 (减30%)
- 从犯: 0.90 (减10%)
- 胁从犯: 0.80 (减20%)
- 防卫过当: 0.50 (减50%)
- 避险过当: 0.50 (减50%)

【酌定从轻情节】
- 自首: 0.75 (减25%)
- 坦白: 0.90 (减10%)
- 立功: 0.80 (减20%)
- 重大立功: 0.50 (减50%)
- 认罪认罚: 0.95 (减5%)
- 赔偿/赔偿全部损失: 0.85 (减15%)
- 取得谅解: 0.85 (减15%)
- 被害人过错: 0.80 (减20%)

**步骤3: 计算最终刑期**
- 使用 `calculate_layered_sentence_with_constraints` 工具
- 传入基准刑、罪名、第一层面情节列表、第二层面情节列表和是否有法定减轻情节
- 注意：第一层面和第二层面情节需要以如下格式传入：
  第一层面: [{{"name": "从犯", "ratio": 0.9}}]
  第二层面: [{{"name": "自首", "ratio": 0.75}}, {{"name": "认罪认罚", "ratio": 0.95}}, ...]
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
             "content": "你是一位刑事法官,必须使用提供的计算器工具进行精确计算,不要自己估算数值。"},
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

                    # 特殊处理：在调用calculate_base_sentence时，确保故意伤害罪有injury_level和victim_count参数
                    if function_name == "calculate_base_sentence" and "crime_type" in function_args and function_args["crime_type"] == "故意伤害罪":
                        # 确保injury_level参数存在
                        if "injury_level" not in function_args:
                            # 从量刑情节中提取伤害等级
                            injury_level = None
                            for factor in sentencing_factors:
                                if "轻伤一级" in factor:
                                    injury_level = "轻伤一级"
                                    break
                                elif "轻伤二级" in factor:
                                    injury_level = "轻伤二级"
                                    break
                                elif "重伤一级" in factor:
                                    injury_level = "重伤一级"
                                    break
                                elif "重伤二级" in factor:
                                    injury_level = "重伤二级"
                                    break
                                elif "死亡" in factor or "致人死亡" in factor:
                                    injury_level = "致人死亡"
                                    break

                            if injury_level is not None:
                                function_args["injury_level"] = injury_level
                                print(f"     添加伤害等级参数: {injury_level}")
                        
                        # 提取受害人数
                        if "victim_count" not in function_args:
                            victim_count = 1
                            for factor in sentencing_factors:
                                match = re.search(r'故意伤害致(\d+)人', factor)
                                if match:
                                    victim_count = int(match.group(1))
                                    break
                                    
                            function_args["victim_count"] = victim_count
                            print(f"     添加受害人数参数: {victim_count}")
                        
                        # 如果没有伤害金额，确保amount为None而不是默认值
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

    def predict_task2_direct_calculation(self, defendant_info, case_description, sentencing_factors):
        """
        执行Task 2:直接使用代码进行刑期预测，不使用工具调用。
        """
        if not sentencing_factors:
            sentencing_factors = ["犯罪情节较轻"]

        # 判断是否有法定减轻情节
        statutory_mitigation_keywords = [
            "自首", "立功", "重大立功",
            "未成年人", "已满十四周岁不满十八周岁",
            "从犯", "胁从犯",
            "防卫过当", "避险过当",
            "七十五周岁", "75周岁"
        ]
        has_statutory = any(kw in str(sentencing_factors) for kw in statutory_mitigation_keywords)

        # 提取伤情等级和受害人数
        injury_level = None
        victim_count = 1  # 默认至少有一个受害者
        
        for factor in sentencing_factors:
            # 提取伤害等级
            if "轻伤一级" in factor:
                injury_level = "轻伤一级"
                break
            elif "轻伤二级" in factor:
                injury_level = "轻伤二级"
                break
            elif "重伤一级" in factor:
                injury_level = "重伤一级"
                break
            elif "重伤二级" in factor:
                injury_level = "重伤二级"
                break
            elif "死亡" in factor:
                injury_level = "致人死亡"
                break
                
        # 提取受害人数
        for factor in sentencing_factors:
            # 匹配"故意伤害致X人..."模式
            match = re.search(r'故意伤害致(\d+)人', factor)
            if match:
                victim_count = int(match.group(1))
                break

        # 步骤1: 计算基准刑
        calculator = SentencingCalculator()
        base_sentence_result = calculator.calculate_base_sentence(
            crime_type="故意伤害罪",
            injury_level=injury_level,
            victim_count=victim_count
        )
        print(f"  基准刑: {base_sentence_result}个月")

        # 步骤2: 分析和分层情节
        # 定义标准调节比例
        factor_ratios = {
            # 法定从重情节
            "累犯": 1.30,
            
            # 酌定从重情节
            "前科": 1.10,
            "多次伤害": 1.20,
            "主犯": 1.25,
            
            # 法定从轻、减轻情节
            "未成年人犯罪": 0.70,
            "从犯": 0.90,
            "胁从犯": 0.80,
            "防卫过当": 0.50,
            "避险过当": 0.50,
            
            # 酌定从轻情节
            "自首": 0.75,
            "坦白": 0.90,
            "立功": 0.80,
            "重大立功": 0.50,
            "认罪认罚": 0.95,
            "赔偿全部损失": 0.85,
            "取得谅解": 0.85,
            "被害人过错": 0.80
        }
        
        # 第一层面情节(连乘): 未成年人、从犯、胁从犯、防卫过当、避险过当
        layer1_keywords = ["未成年人犯罪", "从犯", "胁从犯", "防卫过当", "避险过当"]
        layer1_factors = []
        for factor in sentencing_factors:
            for keyword in layer1_keywords:
                if keyword in factor:
                    if keyword in factor_ratios:
                        layer1_factors.append({
                            "name": keyword,
                            "ratio": factor_ratios[keyword]
                        })
        
        # 第二层面情节(加减): 其他情节
        layer2_keywords = [k for k in factor_ratios.keys() if k not in layer1_keywords]
        layer2_factors = []
        # 特殊处理赔偿金额
        compensation_amount = 0
        for factor in sentencing_factors:
            # 处理具体赔偿金额
            compensation_match = re.search(r'赔偿(\d+)元', factor)
            if compensation_match:
                compensation_amount = int(compensation_match.group(1))
                # 根据赔偿金额确定调节比例
                compensation_factor = 0.85  # 默认有赔偿
                if compensation_amount > 0:
                    layer2_factors.append({
                        "name": f"赔偿{compensation_amount}元",
                        "ratio": compensation_factor
                    })
            else:
                # 处理其他情节
                for keyword in layer2_keywords:
                    if keyword in factor:
                        if keyword in factor_ratios:
                            layer2_factors.append({
                                "name": keyword,
                                "ratio": factor_ratios[keyword]
                            })
        
        # 步骤3: 计算最终刑期
        final_sentence_result = calculator.calculate_layered_sentence_with_constraints(
            base_months=base_sentence_result,
            crime_type="故意伤害罪",
            layer1_factors=layer1_factors,
            layer2_factors=layer2_factors,
            has_statutory_mitigation=has_statutory,
            injury_level=injury_level,
            victim_count=victim_count
        )
        
        print("  计算步骤:")
        for step in final_sentence_result['calculation_steps']:
            print(f"    {step}")
        
        final_months = final_sentence_result['final_months']
        print(f"  最终刑期: {final_months}个月")

        # 步骤4: 生成刑期区间
        range_result = calculator.months_to_range(final_months)
        print(f"  刑期区间: {range_result}")
        
        return range_result

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

                # 第二步:使用直接计算进行刑期预测
                print("\n【步骤2: 使用直接计算刑期】")
                answer2 = self.predict_task2_direct_calculation(
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

                # 第二步:使用直接计算进行刑期预测
                print("\n【步骤2: 使用直接计算刑期】")
                # 从案件信息中提取地区
                answer2 = self.predict_task2_direct_calculation(
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
    fact_file = "data/gysh.jsonl"
    output_file = "result1202/submission_with_tools_fact_1202_gysh.jsonl"

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