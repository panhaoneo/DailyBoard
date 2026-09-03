"""
统计计算模块 - 计算各项市场统计指标
"""

import statistics
from datetime import datetime, timedelta
from config import CHANGE_RANGES
from profit_growth_stocks import extract_profit_growth_stocks


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
    使用每只股票的K线数据计算期间涨幅，然后汇总统计
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

    period_changes = {'year': [], 'month': [], 'week': []}

    for stock in stocks:
        klines = stock.get('klines', [])
        if not klines or len(klines) < 2:
            continue

        # K线按日期升序排列
        def find_close_before(target_date):
            result = None
            for k in klines:
                k_date = datetime.strptime(k["date"], "%Y-%m-%d").date()
                if k_date <= target_date:
                    result = k["close"]
                else:
                    break
            return result

        latest_close = klines[-1]["close"]

        # 计算各期间涨幅
        for period_name, start_date in [('year', year_start), ('month', month_start), ('week', week_start)]:
            start_close = find_close_before(start_date)
            if start_close and start_close > 0 and latest_close > 0:
                change_pct = round((latest_close - start_close) / start_close * 100, 2)
                period_changes[period_name].append(change_pct)

    # 对每个期间计算统计数据
    result = {}
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

    print("[统计] 计算创新高/新低股票...")
    stock_extremes = calc_stock_extremes(stocks)

    print("[统计] 计算指数期间涨幅和BIAS25...")
    index_returns = calc_index_period_returns(histories)

    return {
        "stock": stock_stats,
        "period_stats": period_stats,
        "stock_extremes": stock_extremes,
        "index_returns": index_returns,
        "date": datetime.now().strftime("%Y-%m-%d"),
    }
