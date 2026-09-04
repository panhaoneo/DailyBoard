#!/usr/bin/env python3
"""
从同花顺获取创新高/新低股票数据
使用 AKShare 的 stock_rank_cxg_ths 接口
"""

import akshare as ak
from datetime import datetime


def fetch_ths_year_high():
    """
    获取同花顺"一年新高"股票列表
    返回: list[dict] 包含 code, name, price, change_pct, year_high, high_date
    """
    print("[AKShare] 获取同花顺一年新高数据...")
    try:
        df = ak.stock_rank_cxg_ths(symbol="一年新高")
        if df is None or df.empty:
            print("  [!] 返回数据为空")
            return []

        result = []
        for _, row in df.iterrows():
            code = str(row.get("股票代码", "")).strip()
            name = str(row.get("股票简称", "")).strip()
            price = row.get("最新价", 0)
            change_pct = row.get("涨跌幅", 0)
            high_price = row.get("前期高点", 0)
            high_date = str(row.get("前期高点日期", "")).strip()

            if not code:
                continue

            result.append({
                "code": code,
                "name": name,
                "price": float(price) if price else 0,
                "change_pct": float(change_pct) if change_pct else 0,
                "year_high": float(high_price) if high_price else 0,
                "high_date": high_date,
            })

        print(f"  获取到 {len(result)} 只一年新高股票")
        return result
    except Exception as e:
        print(f"  [!] 获取一年新高失败: {e}")
        return []


def fetch_ths_hist_high():
    """
    获取同花顺"历史新高"股票列表
    返回: list[dict]
    """
    print("[AKShare] 获取同花顺历史新高数据...")
    try:
        df = ak.stock_rank_cxg_ths(symbol="历史新高")
        if df is None or df.empty:
            print("  [!] 返回数据为空")
            return []

        result = []
        for _, row in df.iterrows():
            code = str(row.get("股票代码", "")).strip()
            name = str(row.get("股票简称", "")).strip()
            price = row.get("最新价", 0)
            change_pct = row.get("涨跌幅", 0)
            high_price = row.get("前期高点", 0)
            high_date = str(row.get("前期高点日期", "")).strip()

            if not code:
                continue

            result.append({
                "code": code,
                "name": name,
                "price": float(price) if price else 0,
                "change_pct": float(change_pct) if change_pct else 0,
                "hist_high": float(high_price) if high_price else 0,
                "hist_high_date": high_date,
            })

        print(f"  获取到 {len(result)} 只历史新高股票")
        return result
    except Exception as e:
        print(f"  [!] 获取历史新高失败: {e}")
        return []


def fetch_ths_extremes():
    """
    获取同花顺创新高数据（一年新高 + 历史新高）
    返回: dict {
        'year_high': [...],
        'hist_high': [...]
    }
    """
    year_high = fetch_ths_year_high()
    hist_high = fetch_ths_hist_high()

    return {
        "year_high": year_high,
        "hist_high": hist_high,
    }


if __name__ == "__main__":
    data = fetch_ths_extremes()
    print(f"\n一年新高: {len(data['year_high'])} 只")
    print(f"历史新高: {len(data['hist_high'])} 只")
    if data['year_high']:
        print(f"\n示例: {data['year_high'][0]}")
