"""
报告生成模块 - 生成 Markdown 和 HTML 格式的市场报告
"""

import os
from datetime import datetime


def _fmt(val, suffix="%", default="-"):
    """格式化数值，None时返回默认值"""
    if val is None:
        return default
    if isinstance(val, float):
        return f"{val}{suffix}"
    return f"{val}{suffix}"


def _get_period_val(period_stats, period, key, suffix="%", default="-"):
    """从period_stats获取指定期间和字段的值"""
    period_data = period_stats.get(period, {})
    val = period_data.get(key)
    if val is None:
        return default
    if isinstance(val, float):
        return f"{val}{suffix}"
    return f"{val}{suffix}"


def generate_markdown(stats):
    """生成 Markdown 格式的市场报告（统一表格格式）"""
    date = stats["date"]
    stock = stats["stock"]
    period_stats = stats.get("period_stats", {})
    stock_extremes = stats.get("stock_extremes", {})
    index_returns = stats["index_returns"]

    lines = []
    lines.append(f"# A股市场日报 - {date}\n")
    lines.append(f"> 数据更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 统一表格：按照原图格式
    lines.append("## 市场数据总览\n")
    lines.append("| 名称 | 今年 | 本月 | 本周 | 当天 | BIAS25 |")
    lines.append("|------|------|------|------|------|--------|")

    # A股统计行 - 使用period_stats填充今年/本月/本周
    gp_count = lambda key: _get_period_val(period_stats, 'year', key, suffix="", default="-")
    mp_count = lambda key: _get_period_val(period_stats, 'month', key, suffix="", default="-")
    wp_count = lambda key: _get_period_val(period_stats, 'week', key, suffix="", default="-")
    gp = lambda key: _get_period_val(period_stats, 'year', key, default="-")
    mp = lambda key: _get_period_val(period_stats, 'month', key, default="-")
    wp = lambda key: _get_period_val(period_stats, 'week', key, default="-")

    lines.append(f"| A股总数量 | {gp_count('total')} | {mp_count('total')} | {wp_count('total')} | {stock.get('total', '-')} | - |")
    lines.append(f"| A股上涨数量 | {gp_count('up_count')} | {mp_count('up_count')} | {wp_count('up_count')} | {stock.get('up_count', '-')} | - |")
    lines.append(f"| A股下跌数量 | {gp_count('down_count')} | {mp_count('down_count')} | {wp_count('down_count')} | {stock.get('down_count', '-')} | - |")
    lines.append(f"| A股零涨幅数量 | {gp_count('flat_count')} | {mp_count('flat_count')} | {wp_count('flat_count')} | {stock.get('flat_count', '-')} | - |")

    # 涨幅分布行 - 使用个数而非百分比
    dist_counts = stock.get("distribution_counts", {})
    year_dist_counts = period_stats.get('year', {}).get('distribution_counts', {})
    month_dist_counts = period_stats.get('month', {}).get('distribution_counts', {})
    week_dist_counts = period_stats.get('week', {}).get('distribution_counts', {})
    for name in dist_counts.keys():
        yv = year_dist_counts.get(name, "-")
        mv = month_dist_counts.get(name, "-")
        wv = week_dist_counts.get(name, "-")
        dv = dist_counts.get(name, "-")
        lines.append(f"| {name} | {yv} | {mv} | {wv} | {dv} | - |")

    # 比例和平均行
    lines.append(f"| A股上涨比例 | {gp('up_ratio')} | {mp('up_ratio')} | {wp('up_ratio')} | {_fmt(stock.get('up_ratio'))} | - |")
    lines.append(f"| A股下跌比例 | {gp('down_ratio')} | {mp('down_ratio')} | {wp('down_ratio')} | {_fmt(stock.get('down_ratio'))} | - |")
    lines.append(f"| A股算术平均涨幅 | {gp('avg_change')} | {mp('avg_change')} | {wp('avg_change')} | {_fmt(stock.get('avg_change'))} | - |")
    lines.append(f"| A股涨幅中位数 | {gp('median_change')} | {mp('median_change')} | {wp('median_change')} | {_fmt(stock.get('median_change'))} | - |")

    # 指数行
    for name, data in index_returns.items():
        yr = _fmt(data.get("year_return"), default="-")
        mo = _fmt(data.get("month_return"), default="-")
        wk = _fmt(data.get("week_return"), default="-")
        dy = _fmt(data.get("day_return"), default="-")
        bias = _fmt(data.get("bias25"), default="-")
        lines.append(f"| {name} | {yr} | {mo} | {wk} | {dy} | {bias} |")

    lines.append("")

    # 创新高股票统计
    year_high = stock_extremes.get('year_high', [])
    today_new_high = stats.get('today_new_high', [])
    sector_summary = stats.get('sector_summary', {})

    lines.append("## 创年内新高股票（沪交所+深交所，排除北交所）\n")
    lines.append(f"- 创年内新高: **{len(year_high)}只**")
    lines.append(f"- 当日创新高: **{len(today_new_high)}只**")
    lines.append("")

    # 详细股票列表
    if year_high:
        lines.append(f"### 创年内新高 ({len(year_high)}只)\n")
        lines.append("| 代码 | 名称 | 所属行业 | 收盘价 | 涨跌幅 | 年内最高 | 高点日期 | 利润增长 |")
        lines.append("|------|------|----------|--------|--------|----------|----------|----------|")
        for s in year_high[:50]:
            chg = f"+{s['change_pct']}%" if s['change_pct'] > 0 else f"{s['change_pct']}%"
            high_date = s.get('high_date', '')
            profit_mark = "✓" if s.get('profit_growth') else ""
            industry = s.get('industry', '')
            lines.append(f"| {s['code']} | {s['name']} | {industry} | {s['price']} | {chg} | {s['year_high']} | {high_date} | {profit_mark} |")
        if len(year_high) > 50:
            lines.append(f"\n*...还有{len(year_high)-50}只*\n")
        lines.append("")

    # 当日创新高板块分类总结
    if sector_summary:
        lines.append("### 当日创新高板块分布\n")
        sorted_sectors = sorted(sector_summary.items(), key=lambda x: len(x[1]), reverse=True)
        for sector, names in sorted_sectors:
            lines.append(f"- **{sector}** ({len(names)}只): {', '.join(names)}")
        lines.append("")

    # 创历史新高
    hist_high = stock_extremes.get('hist_high', [])
    lines.append("## 创历史新高股票（沪交所+深交所，排除北交所）\n")
    lines.append(f"- 创历史新高: **{len(hist_high)}只**（数据来源: 同花顺问财）\n")
    if hist_high:
        lines.append(f"### 创历史新高 ({len(hist_high)}只)\n")
        lines.append("| 代码 | 名称 | 所属行业 | 收盘价 | 涨跌幅 | 历史最高 | 高点日期 | 利润增长 |")
        lines.append("|------|------|----------|--------|--------|----------|----------|----------|")
        for s in hist_high[:50]:
            chg = f"+{s['change_pct']}%" if s['change_pct'] > 0 else f"{s['change_pct']}%"
            hist_val = s.get('hist_high', s.get('year_high', '-'))
            hist_val = hist_val if hist_val is not None else "-"
            hist_date = s.get('hist_high_date', s.get('high_date', '')) or "-"
            profit_mark = "✓" if s.get('profit_growth') else ""
            industry = s.get('industry', '')
            lines.append(f"| {s['code']} | {s['name']} | {industry} | {s['price']} | {chg} | {hist_val} | {hist_date} | {profit_mark} |")
        if len(hist_high) > 50:
            lines.append(f"\n*...还有{len(hist_high)-50}只*\n")
        lines.append("")

    # 市场情绪总结
    lines.append("## 市场情绪总结\n")
    up_ratio = stock.get("up_ratio", 0)
    avg_change = stock.get("avg_change", 0)
    median_change = stock.get("median_change", 0)
    total_turnover = stats.get("total_turnover", 0)

    if up_ratio >= 70:
        sentiment = "强势上涨"
    elif up_ratio >= 55:
        sentiment = "偏强震荡"
    elif up_ratio >= 45:
        sentiment = "多空平衡"
    elif up_ratio >= 30:
        sentiment = "偏弱震荡"
    else:
        sentiment = "弱势下跌"

    # 格式化成交额（亿元）
    if total_turnover >= 1e8:
        turnover_str = f"{total_turnover / 1e8:.2f}亿"
    elif total_turnover >= 1e4:
        turnover_str = f"{total_turnover / 1e4:.2f}万"
    else:
        turnover_str = f"{total_turnover:.0f}"

    lines.append(f"- **市场情绪**: {sentiment}")
    lines.append(f"- **两市总成交额**: {turnover_str}")
    lines.append(f"- **上涨比例**: {up_ratio}%")
    lines.append(f"- **平均涨幅**: {avg_change}%")
    lines.append(f"- **中位数涨幅**: {median_change}%")

    if avg_change > 2:
        lines.append("- **市场特征**: 普涨行情，多数股票上涨")
    elif avg_change > 0:
        lines.append("- **市场特征**: 结构性行情，个股分化")
    elif avg_change > -2:
        lines.append("- **市场特征**: 震荡调整，个股分化明显")
    else:
        lines.append("- **市场特征**: 普跌行情，多数股票下跌")

    lines.append("")
    lines.append("---")
    lines.append(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    lines.append("*数据来源: 东方财富、腾讯财经、同花顺问财（免费公开数据）*")

    return "\n".join(lines)


def _html_cell(v):
    """生成带颜色的HTML表格单元格"""
    if v is None:
        return '<td class="flat">-</td>'
    cls = "up" if v > 0 else "down" if v < 0 else "flat"
    prefix = "+" if v > 0 else ""
    return f'<td class="{cls}">{prefix}{v}%</td>'


def generate_html(stats):
    """生成 HTML 格式的市场报告（统一表格格式）"""
    date = stats["date"]
    stock = stats["stock"]
    period_stats = stats.get("period_stats", {})
    stock_extremes = stats.get("stock_extremes", {})
    index_returns = stats["index_returns"]

    up_ratio = stock.get("up_ratio", 0)
    avg_change = stock.get("avg_change", 0)

    if up_ratio >= 70:
        sentiment, s_color = "强势上涨", "#e74c3c"
    elif up_ratio >= 55:
        sentiment, s_color = "偏强震荡", "#e67e22"
    elif up_ratio >= 45:
        sentiment, s_color = "多空平衡", "#f39c12"
    elif up_ratio >= 30:
        sentiment, s_color = "偏弱震荡", "#2980b9"
    else:
        sentiment, s_color = "弱势下跌", "#2c3e50"

    # 辅助函数：获取期间值
    def gp(key): return _get_period_val(period_stats, 'year', key, default="-")
    def mp(key): return _get_period_val(period_stats, 'month', key, default="-")
    def wp(key): return _get_period_val(period_stats, 'week', key, default="-")

    # 构建统一表格行
    table_rows = ""

    # A股统计行 - 使用period_stats填充
    table_rows += f'<tr><td style="text-align:left">A股总数量</td><td>{gp("total")}</td><td>{mp("total")}</td><td>{wp("total")}</td><td>{stock.get("total", "-")}</td><td>-</td></tr>'
    table_rows += f'<tr><td style="text-align:left">A股上涨数量</td><td>{gp("up_count")}</td><td>{mp("up_count")}</td><td>{wp("up_count")}</td><td>{stock.get("up_count", "-")}</td><td>-</td></tr>'
    table_rows += f'<tr><td style="text-align:left">A股下跌数量</td><td>{gp("down_count")}</td><td>{mp("down_count")}</td><td>{wp("down_count")}</td><td>{stock.get("down_count", "-")}</td><td>-</td></tr>'
    table_rows += f'<tr><td style="text-align:left">A股零涨幅数量</td><td>{gp("flat_count")}</td><td>{mp("flat_count")}</td><td>{wp("flat_count")}</td><td>{stock.get("flat_count", "-")}</td><td>-</td></tr>'

    # 涨幅分布行 - 使用个数而非百分比
    dist_counts = stock.get("distribution_counts", {})
    year_dist_counts = period_stats.get('year', {}).get('distribution_counts', {})
    month_dist_counts = period_stats.get('month', {}).get('distribution_counts', {})
    week_dist_counts = period_stats.get('week', {}).get('distribution_counts', {})
    for name, val in dist_counts.items():
        yv = year_dist_counts.get(name, "-")
        mv = month_dist_counts.get(name, "-")
        wv = week_dist_counts.get(name, "-")
        table_rows += f'<tr><td style="text-align:left">{name}</td><td>{yv}</td><td>{mv}</td><td>{wv}</td><td>{val}</td><td>-</td></tr>'

    # 比例和平均行
    table_rows += f'<tr><td style="text-align:left">A股上涨比例</td><td>{gp("up_ratio")}</td><td>{mp("up_ratio")}</td><td>{wp("up_ratio")}</td><td>{stock.get("up_ratio", "-")}%</td><td>-</td></tr>'
    table_rows += f'<tr><td style="text-align:left">A股下跌比例</td><td>{gp("down_ratio")}</td><td>{mp("down_ratio")}</td><td>{wp("down_ratio")}</td><td>{stock.get("down_ratio", "-")}%</td><td>-</td></tr>'
    table_rows += f'<tr><td style="text-align:left">A股算术平均涨幅</td><td>{gp("avg_change")}</td><td>{mp("avg_change")}</td><td>{wp("avg_change")}</td><td class="{"up" if avg_change > 0 else "down" if avg_change < 0 else "flat"}">{"+" if avg_change > 0 else ""}{stock.get("avg_change", "-")}%</td><td>-</td></tr>'
    med = stock.get("median_change", 0)
    table_rows += f'<tr><td style="text-align:left">A股涨幅中位数</td><td>{gp("median_change")}</td><td>{mp("median_change")}</td><td>{wp("median_change")}</td><td class="{"up" if med > 0 else "down" if med < 0 else "flat"}">{"+" if med > 0 else ""}{med}%</td><td>-</td></tr>'

    # 指数行
    for name, data in index_returns.items():
        yr = data.get('year_return')
        mo = data.get('month_return')
        wk = data.get('week_return')
        dy = data.get('day_return')
        bias = data.get('bias25')
        table_rows += f"""
                    <tr>
                        <td style="text-align:left;font-weight:600">{name}</td>
                        {_html_cell(yr)}
                        {_html_cell(mo)}
                        {_html_cell(wk)}
                        {_html_cell(dy)}
                        {_html_cell(bias)}
                    </tr>"""

    # 构建创新高股票表格
    def build_high_table(stock_list, value_key, value_label, date_key='high_date'):
        if not stock_list:
            return "<p style='color:#999;padding:10px 0'>今日无相关股票</p>"
        rows = ""
        for s in stock_list[:100]:
            chg = s['change_pct']
            chg_cls = "up" if chg > 0 else "down" if chg < 0 else "flat"
            chg_prefix = "+" if chg > 0 else ""
            date_val = s.get(date_key, '') or ''
            if not date_val:
                alt_key = 'hist_high_date' if date_key == 'high_date' else 'high_date'
                date_val = s.get(alt_key, '') or ''
            date_val = date_val if date_val else "-"
            value_val = s.get(value_key)
            value_val = value_val if value_val is not None else "-"
            profit_mark = "✓" if s.get('profit_growth') else ""
            industry = s.get('industry', '')
            rows += f"""
                    <tr>
                        <td style="text-align:left">{s['code']}</td>
                        <td style="text-align:left">{s['name']}</td>
                        <td>{industry}</td>
                        <td>{s['price']}</td>
                        <td class="{chg_cls}">{chg_prefix}{chg}%</td>
                        <td>{value_val}</td>
                        <td>{date_val}</td>
                        <td style='text-align:center'>{profit_mark}</td>
                    </tr>"""
        more_info = f"<p style='color:#999;font-size:12px;margin-top:8px'>共 {len(stock_list)} 只</p>" if len(stock_list) > 100 else ""
        return f"""
            <table>
                <thead><tr><th style="text-align:left">代码</th><th style="text-align:left">名称</th><th>所属行业</th><th>收盘价</th><th>涨跌幅</th><th>{value_label}</th><th>高点日期</th><th style='text-align:center'>利润增长</th></tr></thead>
                <tbody>{rows}
                </tbody>
            </table>{more_info}"""

    year_high_table = build_high_table(stock_extremes.get('year_high', []), 'year_high', '年内最高')
    hist_high_table = build_high_table(stock_extremes.get('hist_high', []), 'hist_high', '历史最高')

    year_high_count = len(stock_extremes.get('year_high', []))
    hist_high_count = len(stock_extremes.get('hist_high', []))
    today_new_high_count = len(stats.get('today_new_high', []))
    sector_summary = stats.get('sector_summary', {})
    total_turnover = stats.get('total_turnover', 0)

    # 格式化成交额
    if total_turnover >= 1e8:
        turnover_str = f"{total_turnover / 1e8:.2f}亿"
    elif total_turnover >= 1e4:
        turnover_str = f"{total_turnover / 1e4:.2f}万"
    else:
        turnover_str = f"{total_turnover:.0f}"

    # 板块分布HTML
    sector_html = ""
    if sector_summary:
        sorted_sectors = sorted(sector_summary.items(), key=lambda x: len(x[1]), reverse=True)
        sector_items = ""
        for sector, names in sorted_sectors:
            sector_items += f'<li><strong>{sector}</strong> ({len(names)}只): {", ".join(names)}</li>'
        sector_html = f"""
        <div style="margin-top:16px;padding:16px;background:#f8f9fb;border-radius:8px">
            <h4 style="font-size:14px;color:#333;margin-bottom:10px">当日创新高板块分布</h4>
            <ul style="list-style:none;padding:0;margin:0">{sector_items}</ul>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>A股市场日报 - {date}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                         "PingFang SC", "Microsoft YaHei", sans-serif;
            background: #f0f2f5; color: #333; line-height: 1.6; padding: 20px;
        }}
        .container {{ max-width: 1100px; margin: 0 auto; }}
        .header {{
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            color: white; padding: 30px 40px; border-radius: 12px; margin-bottom: 24px;
        }}
        .header h1 {{ font-size: 28px; margin-bottom: 8px; }}
        .header .subtitle {{ font-size: 14px; opacity: 0.8; }}
        .section {{
            background: white; border-radius: 12px; padding: 24px 30px;
            margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }}
        .section h2 {{
            font-size: 20px; color: #1a1a2e; margin-bottom: 16px;
            padding-bottom: 10px; border-bottom: 2px solid #eef2f7;
        }}
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
        th, td {{ padding: 10px 14px; text-align: center; border-bottom: 1px solid #eef2f7; }}
        th {{ background: #f8f9fb; color: #555; font-weight: 600; font-size: 13px; }}
        tr:hover {{ background: #fafbfc; }}
        .up {{ color: #e74c3c; font-weight: bold; }}
        .down {{ color: #27ae60; font-weight: bold; }}
        .flat {{ color: #999; }}
        .stat-grid {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px; margin-bottom: 10px;
        }}
        .stat-card {{
            background: #f8f9fb; border-radius: 8px; padding: 16px; text-align: center;
        }}
        .stat-card .label {{ font-size: 13px; color: #888; margin-bottom: 6px; }}
        .stat-card .value {{ font-size: 24px; font-weight: bold; }}
        .sentiment-bar {{
            height: 8px; border-radius: 4px; background: #eee;
            margin: 12px 0; overflow: hidden;
        }}
        .sentiment-fill {{ height: 100%; border-radius: 4px; }}
        .footer {{ text-align: center; padding: 20px; color: #999; font-size: 12px; }}
        .tag {{
            display: inline-block; padding: 4px 12px; border-radius: 20px;
            font-size: 13px; font-weight: 600; color: white;
        }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>A股市场日报</h1>
        <div class="subtitle">
            日期: {date} | 更新: {datetime.now().strftime('%H:%M:%S')} | 数据源: 东方财富/腾讯/问财
        </div>
    </div>

    <div class="section">
        <h2>市场数据总览</h2>
        <table>
            <thead>
                <tr><th style="text-align:left">名称</th><th>今年</th><th>本月</th><th>本周</th><th>当天</th><th>BIAS25</th></tr>
            </thead>
            <tbody>{table_rows}
            </tbody>
        </table>
    </div>

    <div class="section">
        <h2>创新高股票（沪交所+深交所，排除北交所）</h2>
        <div class="stat-grid">
            <div class="stat-card">
                <div class="label">创年内新高</div>
                <div class="value up">{year_high_count}只</div>
            </div>
            <div class="stat-card">
                <div class="label">当日创新高</div>
                <div class="value up">{today_new_high_count}只</div>
            </div>
            <div class="stat-card">
                <div class="label">创历史新高</div>
                <div class="value up">{hist_high_count}只</div>
            </div>
        </div>

        <h3 style="font-size:16px;color:#333;margin:20px 0 10px">📈 创年内新高</h3>
        {year_high_table}
        {sector_html}

        <h3 style="font-size:16px;color:#333;margin:20px 0 10px">🏆 创历史新高</h3>
        {hist_high_table}
    </div>

    <div class="section">
        <h2>市场情绪总结</h2>
        <div style="padding:10px 0">
            <p><strong>市场情绪:</strong> <span class="tag" style="background:{s_color}">{sentiment}</span></p>
            <p style="margin-top:10px"><strong>两市总成交额:</strong> {turnover_str}</p>
            <p><strong>上涨比例:</strong> {up_ratio}%</p>
            <p><strong>平均涨幅:</strong> <span class="{"up" if avg_change > 0 else "down" if avg_change < 0 else "flat"}">{"+" if avg_change > 0 else ""}{avg_change}%</span></p>
            <p><strong>中位数涨幅:</strong> <span class="{"up" if med > 0 else "down" if med < 0 else "flat"}">{"+" if med > 0 else ""}{med}%</span></p>
        </div>
    </div>

    <div class="footer">
        报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
        数据来源: 东方财富、腾讯财经、同花顺问财（免费公开数据）<br>
        创历史新高数据来源于同花顺问财
    </div>
</div>
</body>
</html>"""
    return html


def save_reports(stats, output_dir="output"):
    """生成并保存 Markdown 和 HTML 报告"""
    os.makedirs(output_dir, exist_ok=True)

    date = stats["date"]
    md_path = os.path.join(output_dir, f"market_report_{date}.md")
    html_path = os.path.join(output_dir, f"market_report_{date}.html")

    md_content = generate_markdown(stats)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"  Markdown 报告已保存: {md_path}")

    html_content = generate_html(stats)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"  HTML 报告已保存: {html_path}")

    # 同时保存 latest 版本
    latest_md = os.path.join(output_dir, "latest_report.md")
    latest_html = os.path.join(output_dir, "latest_report.html")
    with open(latest_md, "w", encoding="utf-8") as f:
        f.write(md_content)
    with open(latest_html, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"  最新报告: {latest_md} / {latest_html}")

    return md_path, html_path
