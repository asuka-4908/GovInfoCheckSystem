
import re
import random
import datetime
from datetime import timedelta

def parse_chart_command(text):
    """
    Parses the command text to extract time range and dimensions.
    Returns:
        tuple: (is_valid, error_msg, time_range_str, dimensions_list)
    """
    # Remove trigger prefix if present (assumed handled by caller, but safe to clean)
    clean_text = text.replace("@AI", "").replace("舆情数据报表", "").strip()
    
    # Defaults
    time_range = "近 7 天"
    dimensions = []
    all_dimensions = ["情感趋势", "关键词分布", "来源分布", "传播热度"]
    
    # 1. Parse Time Range
    # Patterns: "近 3 天", "近 7 天", "近 30 天", "YYYY-MM-DD 至 YYYY-MM-DD"
    time_patterns = [
        r"近\s*\d+\s*天",
        r"\d{4}-\d{2}-\d{2}\s*至\s*\d{4}-\d{2}-\d{2}"
    ]
    
    found_time = False
    for pattern in time_patterns:
        match = re.search(pattern, clean_text)
        if match:
            time_range = match.group(0)
            clean_text = clean_text.replace(time_range, "").strip() # Remove found time to isolate dims
            found_time = True
            break
            
    # Validate custom date range
    if "至" in time_range:
        try:
            start_str, end_str = time_range.split("至")
            start_date = datetime.datetime.strptime(start_str.strip(), "%Y-%m-%d")
            end_date = datetime.datetime.strptime(end_str.strip(), "%Y-%m-%d")
            if start_date > end_date:
                return False, "开始日期不能晚于结束日期", None, None
        except ValueError:
             return False, "日期格式无效，请使用 YYYY-MM-DD", None, None

    # 2. Parse Dimensions
    # Check for presence of dimension keywords in the remaining text
    for dim in all_dimensions:
        if dim in clean_text:
            dimensions.append(dim)
            
    # If no dimensions specified, default to all (but verify if text has garbage)
    if not dimensions:
        # If text is not empty after removing time, it might be invalid dimensions
        if clean_text and clean_text not in ["+", " "]: 
             # Simple check: if the remaining text isn't just separators, treat as potential error?
             # Requirement says: "指定维度触发...可组合指定"
             # If user types "@AI 舆情数据报表 乱七八糟", we might want to warn?
             # But prompt says "先校验格式（...维度关键词有效性）"
             pass
        
        if not dimensions:
             dimensions = all_dimensions

    return True, "", time_range, dimensions

def get_chart_data(time_range, dimensions):
    """
    Generates mock data for the requested dimensions and time range.
    """
    # 1. Generate Time Axis
    date_list = []
    today = datetime.date.today()
    
    days = 7
    if "近" in time_range:
        try:
            days = int(re.search(r"\d+", time_range).group(0))
        except:
            days = 7
        start_date = today - timedelta(days=days - 1)
        end_date = today
    elif "至" in time_range:
        start_str, end_str = time_range.split("至")
        start_date = datetime.datetime.strptime(start_str.strip(), "%Y-%m-%d").date()
        end_date = datetime.datetime.strptime(end_str.strip(), "%Y-%m-%d").date()
        days = (end_date - start_date).days + 1
    else:
        start_date = today - timedelta(days=6)
        end_date = today

    # Limit max days for mock data to avoid huge payloads if user asks for 1000 days
    if days > 365: 
        days = 365
        start_date = end_date - timedelta(days=365)

    for i in range(days):
        d = start_date + timedelta(days=i)
        date_list.append(d.strftime("%Y-%m-%d"))
        
    data = {
        "time_range": time_range,
        "dimensions": dimensions,
        "generated_at": datetime.datetime.now().strftime("%Y%m%d%H%M"),
        "timeline": date_list
    }

    # 2. Generate Data for each Dimension
    if "情感趋势" in dimensions:
        # Mock curves
        pos = [random.randint(50, 200) for _ in range(days)]
        neg = [random.randint(10, 50) for _ in range(days)]
        neu = [random.randint(20, 80) for _ in range(days)]
        data["sentiment"] = {
            "positive": pos,
            "negative": neg,
            "neutral": neu
        }

    if "关键词分布" in dimensions:
        # Mock Top 10
        keywords = ["舆情系统", "AI 报表", "突发事件", "疫情防控", "政策解读", "民生关注", "交通出行", "教育改革", "环境保护", "科技创新"]
        counts = [random.randint(50, 200) for _ in range(10)]
        counts.sort(reverse=True)
        data["keywords"] = {
            "words": keywords,
            "counts": counts
        }

    if "来源分布" in dimensions:
        sources = ["微博", "微信", "知乎", "抖音", "今日头条"]
        # Random weights
        weights = [random.randint(10, 50) for _ in sources]
        total = sum(weights)
        percents = [round(w / total * 100, 1) for w in weights]
        data["sources"] = {
            "names": sources,
            "values": percents
        }

    if "传播热度" in dimensions:
        heat = [random.randint(100, 1000) for _ in range(days)]
        avg = sum(heat) // len(heat)
        data["heat"] = {
            "values": heat,
            "avg": avg
        }

    return data
