import json
import re


def extract_province(fact_text):
    """
    从案件事实文本中提取省份信息

    优先级：
    1. 从公诉机关中提取（如：广东省某区人民检察院 -> 广东省）
    2. 从户籍所在地提取（如：河南省*** -> 河南省）
    3. 从住址提取（如：陕西省某市某县 -> 陕西省）
    4. 从其他描述中提取省份
    """

    # 省份列表（包含直辖市和自治区）
    provinces = [
        '北京市', '天津市', '上海市', '重庆市',
        '河北省', '山西省', '辽宁省', '吉林省', '黑龙江省',
        '江苏省', '浙江省', '安徽省', '福建省', '江西省', '山东省',
        '河南省', '湖北省', '湖南省', '广东省', '海南省',
        '四川省', '贵州省', '云南省', '陕西省', '甘肃省', '青海省', '台湾省',
        '内蒙古自治区', '广西壮族自治区', '西藏自治区', '宁夏回族自治区', '新疆维吾尔自治区',
        '香港特别行政区', '澳门特别行政区'
    ]

    # 简化版省份（用于模糊匹配）
    simple_provinces = {
        '北京': '北京市', '天津': '天津市', '上海': '上海市', '重庆': '重庆市',
        '河北': '河北省', '山西': '山西省', '辽宁': '辽宁省', '吉林': '吉林省', '黑龙江': '黑龙江省',
        '江苏': '江苏省', '浙江': '浙江省', '安徽': '安徽省', '福建': '福建省', '江西': '江西省', '山东': '山东省',
        '河南': '河南省', '湖北': '湖北省', '湖南': '湖南省', '广东': '广东省', '海南': '海南省',
        '四川': '四川省', '贵州': '贵州省', '云南': '云南省', '陕西': '陕西省', '甘肃': '甘肃省', '青海': '青海省',
        '台湾': '台湾省',
        '内蒙古': '内蒙古自治区', '广西': '广西壮族自治区', '西藏': '西藏自治区',
        '宁夏': '宁夏回族自治区', '新疆': '新疆维吾尔自治区',
        '香港': '香港特别行政区', '澳门': '澳门特别行政区'
    }

    # 策略1: 从公诉机关提取
    prosecutor_pattern = r'公诉机关(.*?)人民检察院'
    prosecutor_match = re.search(prosecutor_pattern, fact_text)
    if prosecutor_match:
        prosecutor_text = prosecutor_match.group(1)
        for province in provinces:
            if province in prosecutor_text:
                return province
        # 尝试简化匹配
        for simple, full in simple_provinces.items():
            if simple in prosecutor_text and '省' in prosecutor_text[:50]:
                return full

    # 策略2: 从户籍所在地提取
    huji_pattern = r'户籍所在地[：:](.*?)(?:[。\n]|$)'
    huji_match = re.search(huji_pattern, fact_text)
    if huji_match:
        huji_text = huji_match.group(1)
        for province in provinces:
            if province in huji_text:
                return province
        for simple, full in simple_provinces.items():
            if huji_text.startswith(simple):
                return full

    # 策略3: 从住址提取
    address_pattern = r'住(.*?)(?:[。\n，,]|$)'
    address_match = re.search(address_pattern, fact_text)
    if address_match:
        address_text = address_match.group(1)
        for province in provinces:
            if province in address_text:
                return province
        for simple, full in simple_provinces.items():
            if address_text.startswith(simple):
                return full

    # 策略4: 全文搜索第一个出现的省份
    for province in provinces:
        if province in fact_text:
            return province

    # 如果都没找到，返回未知
    return "未知"


def main():
    # 读取task6_fusai.jsonl
    task6_data = {}
    with open('./data/task6_fusai.jsonl', 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                province = extract_province(item['fact'])
                task6_data[item['id']] = province

    # 读取extracted_info_fusai.json
    with open('extracted_info_fusai.json', 'r', encoding='utf-8') as f:
        extracted_data = json.load(f)

    # 添加省份字段
    for item in extracted_data:
        item_id = item['id']
        item['province'] = task6_data.get(item_id, "未知")

    # 保存更新后的数据
    with open('extracted_info_fusai1.json', 'w', encoding='utf-8') as f:
        json.dump(extracted_data, f, ensure_ascii=False, indent=2)

    print("处理完成！")
    print(f"共处理 {len(extracted_data)} 条记录")

    # 输出统计信息
    province_count = {}
    for item in extracted_data:
        province = item['province']
        province_count[province] = province_count.get(province, 0) + 1

    print("\n省份分布：")
    for province, count in sorted(province_count.items(), key=lambda x: x[1], reverse=True):
        print(f"  {province}: {count}条")


if __name__ == "__main__":
    main()
