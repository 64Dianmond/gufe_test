# 法律量刑预测系统

本项目是一个基于大型语言模型的法律量刑预测系统，采用"提取-注入-计算"的三步混合法，并集成了权威的、分层的量刑计算规则。系统支持工具调用，使用专业计算器进行精确的刑期计算。

## 项目结构

```
E:\CAIL_test\1111\
├── predict_fact_function_call_merge.py  # 主要的预测程序
├── cal.py                              # 刑期计算器工具
├── sentencing_calculator.py             # 地区差异化刑期计算器工具
├── process.py                          # 数据处理脚本
├── add_province_to_extracted.py        # 添加省份信息到数据文件
├── predict_fact_llm_function_call.py   # LLM函数调用task6_fusai.jsonl数据集预测程序
├── predict_with_llm_function_call.py   # 使用LLM函数调用extracted_info_fusai1（提取被告人信息和案情描述）的预测程序
├── data/                               # 数据目录
│   └── task6_fusai.jsonl              # 用于task1的案件事实数据
├── extracted_info_fusai1.json          # 提取被告人信息和案情描述的结构化数据（目前在predict_fact_function_call_merge用于task2的任务）
└── submission_with_tools_fact_merge.jsonl  # 输出结果文件
```
predict_with_llm_function_call.py的结果为：Final_score: 0.435155, Task1_avg_F1: 0.4791, Task2_avg_Winkler: 0.3912。
predict_fact_llm_function_call.py的结果为：Final_score: 0.399151, Task1_avg_F1: 0.5294, Task2_avg_Winkler: 0.2689。
predict_fact_function_call_merge.jsonl的结果为：Final_score, Final_score: 0.452334, Task1_avg_F1: 0.5406, Task2_avg_Winkler: 0.3641
## 核心功能

### 1. 量刑情节提取 (Task 1)
- 从案件事实中提取所有对量刑有影响的关键情节
- 支持三类情节提取：
  - 犯罪构成与基本事实情节 (决定量刑起点和基准刑)
  - 法定从重、从轻、减轻处罚情节 (必须依法调节)
  - 酌定从重、从轻处罚情节 (可以酌情调节)

### 2. 刑期预测 (Task 2)
- 使用专业计算器工具进行精确刑期计算
- 支持分层量刑计算规则：
  - 第一层面情节(连乘)：未成年人、从犯、胁从犯、犯罪预备、犯罪中止、犯罪未遂
  - 第二层面情节(加减)：累犯、自首、坦白、立功、认罪认罚、退赔、取得谅解、前科
- 生成最终刑期区间

## 主要文件说明

### predict_fact_function_call_merge.py
主程序文件，包含以下主要方法：
- `predict_task1_authoritative`: 执行Task 1，提取量刑情节
- `predict_task2_with_tools`: 执行Task 2，使用工具调用进行刑期预测
- `process_fact_data`: 处理fact格式的数据(task6_fusai.jsonl)用于Task 1
- `process_all_data`: 处理结构化数据(extracted_info_fusai1.json)用于Task 2

### cal.py
刑期计算器工具，提供精确的量刑计算功能：
- `calculate_base_sentence`: 计算基准刑
- `calculate_layered_sentence`: 分层计算最终刑期
- `months_to_range`: 将中心月数转换为刑期区间

### 数据文件
- `data/task6_fusai.jsonl`: Task 1输入数据，包含案件事实字段
- `extracted_info_fusai1.json`: Task 2输入数据，包含结构化提取信息
- `submission_with_tools_fact_merge.jsonl`: 输出结果文件，JSONL格式

## 使用方法

1. 配置环境变量：
   - OPENAI_API_KEY: API密钥
   - OPENAI_BASE_URL: API基础URL
   - OPENAI_MODEL: 使用的模型名称(默认为qwen-max)

2. 运行程序：
   ```bash
   python predict_fact_function_call_merge.py
   ```

3. 程序会自动检测数据文件并处理：
   - 如果存在`data/task6_fusai.jsonl`，则处理Task 1数据
   - 否则处理`extracted_info_fusai1.json`，即Task 2数据

## 技术特点

1. **双温度参数设置**：
   - Task 1使用较高温度(1.0)以增加多样性
   - Task 2使用较低温度(0.1)以确保稳定性

2. **工具调用机制**：
   - 使用OpenAI Function Calling机制调用计算器工具
   - 避免LLM直接进行数值计算，提高准确性

3. **分层量刑计算**：
   - 第一层面情节使用连乘计算
   - 第二层面情节使用加减计算
   - 符合法律量刑实践

4. **地区差异化处理**：
   - 支持不同地区数额标准的差异化计算
   - 考虑各地司法实践的差异

## 输出格式

结果以JSONL格式保存在`submission_with_tools_fact_merge.jsonl`文件中，每行一个JSON对象：
```json
{
  "id": 1,
  "answer1": ["盗窃金额既遂3320元", "盗窃数额较大", "扒窃", "坦白", "退赔2800元", "取得谅解", "认罪认罚"],
  "answer2": [6, 12]
}
```

- `answer1`: 提取的量刑情节列表
- `answer2`: 预测的刑期区间(月)