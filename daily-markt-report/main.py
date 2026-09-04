#!/usr/bin/env python3
"""
每日A股市场报告生成器

从东方财富、新浪等免费公开API获取A股实时行情数据，
计算各项统计指标，生成 Markdown 和 HTML 格式的市场日报。

用法:
    python main.py              # 获取数据并生成报告
    python main.py --no-fetch   # 使用缓存数据重新生成报告（调试用）
"""

import os
import sys
import json
import argparse
from datetime import datetime

from data_fetcher import fetch_market_data
from market_stats import calc_all_stats
from report_generator import save_reports


CACHE_FILE = "cache/latest_data.json"
SAMPLE_DATA_FILE = "cache/sample_data.json"


def save_cache(market_data):
    """缓存原始数据到本地"""
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(market_data, f, ensure_ascii=False, indent=2)
    print(f"\n数据已缓存到：{CACHE_FILE}")


def load_cache():
    """从本地缓存加载数据"""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def load_sample_data():
    """加载示例数据（用于演示）"""
    if os.path.exists(SAMPLE_DATA_FILE):
        with open(SAMPLE_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def main():
    parser = argparse.ArgumentParser(description="A股市场日报生成器")
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="使用缓存数据，不重新获取（调试用）",
    )
    parser.add_argument(
        "--output",
        default="output",
        help="输出目录（默认: output）",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="使用示例数据生成报告（演示用）",
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("  A 股市场日报生成器")
    print(f"  运行时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 获取数据
    if args.sample:
        print("\n使用示例数据（演示模式）...")
        market_data = load_sample_data()
        if market_data is None:
            print("  [错误] 未找到示例数据文件")
            sys.exit(1)
    elif args.no_fetch:
        print("\n使用缓存数据...")
        market_data = load_cache()
        if market_data is None:
            print("  [错误] 未找到缓存数据，请先运行一次不带 --no-fetch 的命令")
            sys.exit(1)
    else:
        market_data = fetch_market_data()
        save_cache(market_data)

    # 计算统计
    print("\n[统计] 开始计算各项指标...")
    stats = calc_all_stats(market_data)

    # 生成报告
    print(f"\n[报告] 生成 Markdown 和 HTML 报告...")
    md_path, html_path = save_reports(stats, output_dir=args.output)

    # 打印摘要
    stock = stats["stock"]
    stock_extremes = stats.get("stock_extremes", {})
    print("\n" + "=" * 60)
    print("  报告摘要")
    print("=" * 60)
    print(f"  日期:       {stats['date']}")
    print(f"  A股总数:    {stock.get('total', '-')}")
    print(f"  上涨/下跌:  {stock.get('up_count', '-')}/{stock.get('down_count', '-')}")
    print(f"  上涨比例:   {stock.get('up_ratio', '-')}%")
    print(f"  平均涨幅:   {stock.get('avg_change', '-')}%")
    print(f"  中位数涨幅: {stock.get('median_change', '-')}%")
    print(f"\n  创年内新高: {len(stock_extremes.get('year_high', []))}只")
    print(f"  创历史新高: {len(stock_extremes.get('hist_high', []))}只")
    print(f"\n  Markdown: {md_path}")
    print(f"  HTML:     {html_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
