#!/usr/bin/env python3
"""
生成 output/ 目录的 index.html，作为 GitHub Pages 首页。
扫描所有 market_report_YYYY-MM-DD.html 文件，按日期倒序列表。
"""

import os
import re
from datetime import datetime

OUTPUT_DIR = "output"


def build_index():
    reports = []
    pattern = re.compile(r"^market_report_(\d{4}-\d{2}-\d{2})\.html$")

    for f in os.listdir(OUTPUT_DIR):
        m = pattern.match(f)
        if m:
            date_str = m.group(1)
            reports.append((date_str, f))

    reports.sort(reverse=True)

    rows = ""
    for date_str, filename in reports:
        md_file = filename.replace(".html", ".md")
        rows += f"""
            <tr>
                <td style="text-align:left;font-weight:600">{date_str}</td>
                <td><a href="{filename}">查看报告</a></td>
                <td><a href="{md_file}">Markdown</a></td>
            </tr>"""

    today = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>A股市场日报</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                         "PingFang SC", "Microsoft YaHei", sans-serif;
            background: #f0f2f5; color: #333; line-height: 1.6; padding: 20px;
        }}
        .container {{ max-width: 800px; margin: 0 auto; }}
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
        table {{ width: 100%; border-collapse: collapse; font-size: 15px; }}
        th, td {{ padding: 12px 16px; text-align: center; border-bottom: 1px solid #eef2f7; }}
        th {{ background: #f8f9fb; color: #555; font-weight: 600; font-size: 13px; }}
        tr:hover {{ background: #fafbfc; }}
        a {{ color: #2980b9; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .latest {{
            display: inline-block; background: #e74c3c; color: white;
            padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-left: 8px;
        }}
        .footer {{ text-align: center; padding: 20px; color: #999; font-size: 12px; }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>A股市场日报</h1>
        <div class="subtitle">每日收盘后自动生成 | 最近更新: {today}</div>
    </div>

    <div class="section">
        <h2>历史报告</h2>
        <table>
            <thead>
                <tr><th style="text-align:left">日期</th><th>HTML</th><th>Markdown</th></tr>
            </thead>
            <tbody>{rows}
            </tbody>
        </table>
    </div>

    <div class="footer">
        数据来源: 新浪财经、腾讯财经（免费公开数据）<br>
        本项目仅供学习研究，不构成投资建议
    </div>
</div>
</body>
</html>"""

    index_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Index generated: {index_path} ({len(reports)} reports)")


if __name__ == "__main__":
    build_index()
