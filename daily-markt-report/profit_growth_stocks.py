#!/usr/bin/env python3
"""
提取中报利润增长股票列表
从 stock_screen_classified_*.md 文件中提取股票代码
"""

import os
import re
import glob


def extract_profit_growth_stocks(screen_file=None):
    """
    从选股分类文件中提取股票代码列表
    返回: set of stock codes (without suffix, e.g., "300750")
    """
    if screen_file is None:
        # 查找最新的 stock_screen_classified_*.md 文件
        pattern = os.path.join(os.path.dirname(__file__), "stock_screen_classified_*.md")
        files = glob.glob(pattern)
        if not files:
            return set()
        screen_file = sorted(files)[-1]  # 使用最新的文件

    if not os.path.exists(screen_file):
        return set()

    stock_codes = set()

    # 匹配表格中的股票代码行，如 "| 300750.SZ | 宁德时代 |"
    code_pattern = re.compile(r'^\|\s*(\d{6})\.(SZ|SH|BJ)\s*\|')

    with open(screen_file, 'r', encoding='utf-8') as f:
        for line in f:
            match = code_pattern.match(line)
            if match:
                code = match.group(1)
                stock_codes.add(code)

    print(f"[利润增长] 从 {os.path.basename(screen_file)} 提取了 {len(stock_codes)} 只股票")
    return stock_codes


if __name__ == "__main__":
    codes = extract_profit_growth_stocks()
    print(f"共提取 {len(codes)} 只股票")
    if codes:
        sample = list(codes)[:10]
        print(f"示例: {', '.join(sample)}")
