"""
统计计算模块 - 计算各项市场统计指标
"""

import statistics
from datetime import datetime, timedelta
from config import CHANGE_RANGES
from profit_growth_stocks import extract_profit_growth_stocks
from ths_fetcher import fetch_ths_extremes
from iwencai_fetcher import fetch_iwencai_hist_high


def calc_change_distribution(changes):
    """
    计算涨幅区间分布（百分比）
    changes: list[float] 所有股票的涨跌幅
    返回: dict {区间名: 百分比}
    """
    total = len(changes)
    if total == 0:
        return {name: 0.0 for name, _ in CHANGE_RANGES}

    result = {}
    for name, condition in CHANGE_RANGES:
        count = sum(1 for c in changes if condition(c))
        result[name] = round(count / total * 100, 2)
    return result


def calc_change_distribution_counts(changes):
    """
    计算涨幅区间分布（个数）
    changes: list[float] 所有股票的涨跌幅
    返回: dict {区间名: 个数}
    """
    if not changes:
        return {name: 0 for name, _ in CHANGE_RANGES}

    result = {}
    for name, condition in CHANGE_RANGES:
        count = sum(1 for c in changes if condition(c))
        result[name] = count
    return result


def calc_basic_stats(stocks):
    """
    计算A股基本统计数据
    返回: dict 包含所有基本统计指标
    """
    if not stocks:
        return {}

    changes = [s["change_pct"] for s in stocks]
    total = len(changes)

    up_count = sum(1 for c in changes if c > 0)
    down_count = sum(1 for c in changes if c < 0)
    flat_count = sum(1 for c in changes if c == 0)

    up_ratio = round(up_count / total * 100, 2) if total else 0
    down_ratio = round(down_count / total * 100, 2) if total else 0

    avg_change = round(statistics.mean(changes), 2)
    median_change = round(statistics.median(changes), 2)

    dist = calc_change_distribution(changes)
    dist_counts = calc_change_distribution_counts(changes)

    return {
        "total": total,
        "up_count": up_count,
        "down_count": down_count,
        "flat_count": flat_count,
        "up_ratio": up_ratio,
        "down_ratio": down_ratio,
        "avg_change": avg_change,
        "median_change": median_change,
        "distribution": dist,
        "distribution_counts": dist_counts,
    }


def calc_stock_extremes(stocks, profit_growth_codes=None):
    """
    计算当天创年内新高/新低的股票列表
    排除北交所股票（代码以4或8开头，或以bj开头）
    使用当日最高/最低价与年内高低比较
    profit_growth_codes: 中报利润增长股票代码集合
    返回: dict {
        'year_high': [{code, name, price, change_pct, year_high, profit_growth}],
        'year_low': [{code, name, price, change_pct, year_low}]
    }
    """
    if profit_growth_codes is None:
        profit_growth_codes = extract_profit_growth_stocks()

    if not stocks:
        return {'year_high': [], 'year_low': []}

    # 过滤掉北交所股票（代码以4或8开头，或以bj开头）
    sh_sz_stocks = [
        s for s in stocks
        if not (s['code'].startswith('4') or s['code'].startswith('8') or s['code'].startswith('bj'))
    ]

    year_high_stocks = []
    year_low_stocks = []

    for s in sh_sz_stocks:
        today_high = s.get('high', 0)   # 当日最高价
        today_low = s.get('low', 0)     # 当日最低价
        year_high = s.get('year_high', 0)  # 年内最高（来自年K线）
        year_low = s.get('year_low', 0)    # 年内最低（来自年K线）

        # 判断是否创年内新高（当日最高价 >= 年内最高）
        if year_high > 0 and today_high >= year_high * 0.999:
            is_profit_growth = s['code'] in profit_growth_codes
            year_high_stocks.append({
                'code': s['code'],
                'name': s['name'],
                'price': s['price'],
                'change_pct': s['change_pct'],
                'year_high': year_high,
                'profit_growth': is_profit_growth,
            })

        # 判断是否创年内新低（当日最低价 <= 年内最低）
        if year_low > 0 and today_low <= year_low * 1.001:
            year_low_stocks.append({
                'code': s['code'],
                'name': s['name'],
                'price': s['price'],
                'change_pct': s['change_pct'],
                'year_low': year_low,
            })

    return {
        'year_high': year_high_stocks,
        'year_low': year_low_stocks,
    }


def calc_index_period_returns(histories):
    """
    计算各指数的期间涨幅（今年、本月、本周、当天）和BIAS25
    histories: dict {index_name: [kline_data]}
    返回: dict {index_name: {year_return, month_return, week_return, day_return, bias25}}
    """
    today = datetime.now().date()
    year_start = datetime(today.year, 1, 1).date()

    # 本月第一天
    month_start = datetime(today.year, today.month, 1).date()

    # 本周一
    weekday = today.weekday()  # 0=Monday
    week_start = today - timedelta(days=weekday)

    results = {}

    for name, klines in histories.items():
        if len(klines) < 2:
            continue

        # 最新数据
        latest = klines[-1]
        latest_close = latest["close"]

        # 找到各期间起始日的收盘价
        # klines按日期升序排列，找到 <= 目标日期的最后一条记录
        def find_close_before(target_date):
            """找到 <= target_date 的最近一个交易日的收盘价"""
            result = None
            for k in klines:
                k_date = datetime.strptime(k["date"], "%Y-%m-%d").date()
                if k_date <= target_date:
                    result = k["close"]
                else:
                    break  # 已排序，后面的都更大
            return result

        prev_close = klines[-2]["close"] if len(klines) >= 2 else latest_close
        year_start_close = find_close_before(year_start)
        month_start_close = find_close_before(month_start)
        week_start_close = find_close_before(week_start)

        # 计算期间涨幅
        def calc_return(start_price, end_price):
            if start_price and start_price > 0 and end_price > 0:
                return round((end_price - start_price) / start_price * 100, 2)
            return None

        year_return = calc_return(year_start_close, latest_close)
        month_return = calc_return(month_start_close, latest_close)
        week_return = calc_return(week_start_close, latest_close)
        day_return = round((latest_close - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0

        # 计算BIAS25（25日乖离率）
        bias25 = None
        if len(klines) >= 25:
            recent_closes = [k["close"] for k in klines[-25:]]
            ma25 = statistics.mean(recent_closes)
            if ma25 > 0:
                bias25 = round((latest_close - ma25) / ma25 * 100, 2)

        results[name] = {
            "year_return": year_return,
            "month_return": month_return,
            "week_return": week_return,
            "day_return": day_return,
            "bias25": bias25,
        }

    return results


def calc_stock_period_stats(stocks):
    """
    计算A股各期间（今年、本月、本周）的统计数据
    今年: 直接使用东方财富快照数据中的年初至今涨跌幅(ytd_change_pct)
    本月/本周: 使用K线数据计算期间涨幅
    返回: dict {
        'year': {total, up_count, down_count, ...},
        'month': {...},
        'week': {...}
    }
    """
    if not stocks:
        return {'year': {}, 'month': {}, 'week': {}}

    today = datetime.now().date()
    year_start = datetime(today.year, 1, 1).date()
    month_start = datetime(today.year, today.month, 1).date()
    weekday = today.weekday()
    week_start = today - timedelta(days=weekday)

    # 今年: 直接使用ytd_change_pct（来自东方财富快照）
    year_changes = []
    for stock in stocks:
        ytd = stock.get('ytd_change_pct')
        if ytd is not None:
            year_changes.append(ytd)
    # 缺少ytd的股票（如回退新浪数据源）用K线补算
    kline_year_needed = any(s.get('ytd_change_pct') is None for s in stocks)

    # 本月/本周: 使用K线数据计算
    period_changes = {'month': [], 'week': []}

    for stock in stocks:
        klines = stock.get('klines', [])
        if not klines or len(klines) < 2:
            continue

        latest_close = klines[-1]["close"]

        def find_close_before(target_date):
            result = None
            for k in klines:
                k_date = datetime.strptime(k["date"], "%Y-%m-%d").date()
                if k_date <= target_date:
                    result = k["close"]
                else:
                    break
            return result

        if kline_year_needed and stock.get('ytd_change_pct') is None:
            # K线只含当年数据时没有年初前收盘价，用年内首条K线收盘价作基准近似
            year_start_close = find_close_before(year_start)
            if year_start_close is None and klines:
                year_start_close = klines[0]["close"]
            if year_start_close and year_start_close > 0 and latest_close > 0:
                year_changes.append(round((latest_close - year_start_close) / year_start_close * 100, 2))

        for period_name, start_date in [('month', month_start), ('week', week_start)]:
            start_close = find_close_before(start_date)
            if start_close and start_close > 0 and latest_close > 0:
                change_pct = round((latest_close - start_close) / start_close * 100, 2)
                period_changes[period_name].append(change_pct)

    # 对每个期间计算统计数据
    result = {}

    # 今年
    if year_changes:
        total = len(year_changes)
        up_count = sum(1 for c in year_changes if c > 0)
        down_count = sum(1 for c in year_changes if c < 0)
        flat_count = sum(1 for c in year_changes if c == 0)
        up_ratio = round(up_count / total * 100, 2) if total else 0
        down_ratio = round(down_count / total * 100, 2) if total else 0
        avg_change = round(statistics.mean(year_changes), 2)
        median_change = round(statistics.median(year_changes), 2)
        dist = calc_change_distribution(year_changes)
        dist_counts = calc_change_distribution_counts(year_changes)
        result['year'] = {
            'total': total,
            'up_count': up_count,
            'down_count': down_count,
            'flat_count': flat_count,
            'up_ratio': up_ratio,
            'down_ratio': down_ratio,
            'avg_change': avg_change,
            'median_change': median_change,
            'distribution': dist,
            'distribution_counts': dist_counts,
        }
    else:
        result['year'] = {}

    # 本月/本周
    for period_name, changes in period_changes.items():
        if not changes:
            result[period_name] = {}
            continue

        total = len(changes)
        up_count = sum(1 for c in changes if c > 0)
        down_count = sum(1 for c in changes if c < 0)
        flat_count = sum(1 for c in changes if c == 0)
        up_ratio = round(up_count / total * 100, 2) if total else 0
        down_ratio = round(down_count / total * 100, 2) if total else 0
        avg_change = round(statistics.mean(changes), 2)
        median_change = round(statistics.median(changes), 2)
        dist = calc_change_distribution(changes)
        dist_counts = calc_change_distribution_counts(changes)

        result[period_name] = {
            'total': total,
            'up_count': up_count,
            'down_count': down_count,
            'flat_count': flat_count,
            'up_ratio': up_ratio,
            'down_ratio': down_ratio,
            'avg_change': avg_change,
            'median_change': median_change,
            'distribution': dist,
            'distribution_counts': dist_counts,
        }

    return result


def calc_all_stats(market_data):
    """
    计算所有统计数据
    market_data: fetch_market_data() 的返回值
    返回: dict 包含所有统计结果
    """
    stocks = market_data["stocks"]
    histories = market_data["histories"]

    print("[统计] 计算A股统计数据...")
    stock_stats = calc_basic_stats(stocks)

    print("[统计] 计算A股各期间统计数据...")
    period_stats = calc_stock_period_stats(stocks)

    print("[统计] 获取同花顺创新高数据...")
    ths_extremes = fetch_ths_extremes()

    # 合并THS数据和利润增长数据
    profit_growth_codes = extract_profit_growth_stocks()

    # 构建代码到行业的映射
    code_to_industry = {}
    for s in stocks:
        code = s.get("code", "")
        industry = s.get("industry", "")
        if code and industry:
            code_to_industry[code] = industry

    # 为THS的year_high添加profit_growth标记和行业信息
    year_high = ths_extremes.get("year_high", [])
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_new_high = []
    for s in year_high:
        s["profit_growth"] = s["code"] in profit_growth_codes
        s["industry"] = code_to_industry.get(s["code"], "")
        if s.get("high_date") == today_str:
            today_new_high.append(s)

    # 按行业排序
    year_high.sort(key=lambda x: x.get("industry", "") or "zzz")

    # 创历史新高: 优先问财（数据来源: 同花顺问财），失败回退同花顺AKShare
    print("[统计] 获取创历史新高股票（问财优先）...")
    iwencai_hist_high = fetch_iwencai_hist_high()
    if iwencai_hist_high is not None:
        hist_high = iwencai_hist_high
    else:
        print("[统计] 问财不可用，回退同花顺AKShare历史新高数据...")
        hist_high = ths_extremes.get("hist_high", [])

    for s in hist_high:
        s["profit_growth"] = s["code"] in profit_growth_codes
        s["industry"] = code_to_industry.get(s["code"], "")

    hist_high.sort(key=lambda x: x.get("industry", "") or "zzz")

    # 计算两市总成交额
    total_turnover = sum(s.get("amount", 0) for s in stocks)

    # 按行业统计今日创新高的股票
    sector_summary = {}
    for s in today_new_high:
        ind = s.get("industry", "未知")
        if not ind:
            ind = "未知"
        if ind not in sector_summary:
            sector_summary[ind] = []
        sector_summary[ind].append(s["name"])

    stock_extremes = {
        "year_high": year_high,
        "hist_high": hist_high,
    }

    print("[统计] 计算指数期间涨幅和BIAS25...")
    index_returns = calc_index_period_returns(histories)

    return {
        "stock": stock_stats,
        "period_stats": period_stats,
        "stock_extremes": stock_extremes,
        "index_returns": index_returns,
        "total_turnover": total_turnover,
        "today_new_high": today_new_high,
        "sector_summary": sector_summary,
        "date": datetime.now().strftime("%Y-%m-%d"),
    }
