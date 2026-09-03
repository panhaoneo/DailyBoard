#!/usr/bin/env python3
"""
生成 output/ 目录的 index.html，作为 GitHub Pages 首页。
扫描所有 market_report_YYYY-MM-DD.html 文件，按日期倒序列表。
"""

import os
import re
from datetime import datetime

OUTPUT_DIR = "output"
REPO_BASE = "https://github.com/panhaoneo/DailyBoard/blob/main/daily-markt-report/output"


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
                <td><a href="{REPO_BASE}/{md_file}">Markdown</a></td>
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
            font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
            background: #f5f5f5; color: #333; line-height: 1.6; padding: 16px;
        }}
        .container {{ max-width: 700px; margin: 0 auto; }}
        .header {{
            background: #1a1a2e; color: white; padding: 24px;
            border-radius: 8px; margin-bottom: 16px;
        }}
        .header h1 {{ font-size: 22px; margin-bottom: 4px; }}
        .header .subtitle {{ font-size: 13px; opacity: 0.7; }}
        .section {{
            background: white; border-radius: 8px; padding: 16px;
            margin-bottom: 16px;
        }}
        .section h2 {{
            font-size: 17px; color: #333; margin-bottom: 12px;
            padding-bottom: 8px; border-bottom: 1px solid #eee;
        }}
        .table-wrapper {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; min-width: 400px; }}
        th, td {{ padding: 10px 12px; text-align: center; border-bottom: 1px solid #eee; }}
        th {{ background: #fafafa; color: #666; font-weight: 600; font-size: 13px; text-align: left; }}
        tr:hover {{ background: #fafafa; }}
        a {{ color: #2980b9; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .footer {{ text-align: center; padding: 16px; color: #999; font-size: 12px; }}
        @media (max-width: 768px) {{
            body {{ padding: 10px; }}
            .header {{ padding: 18px; }}
            .header h1 {{ font-size: 19px; }}
            .section {{ padding: 12px; }}
            table {{ font-size: 13px; }}
            th, td {{ padding: 8px; }}
        }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>A股市场日报</h1>
        <div class="subtitle">每日收盘后自动生成 | 最近更新: {today}</div>
    </div>

    <div class="section">
        <div style="background:#f8f9fa;border-left:3px solid #1a1a2e;padding:12px 16px;font-size:0.95rem;color:#444;line-height:1.8;">
从专业角度出发，看财报、调研、交流、投研看什么行业集体处于景气上行区间，什么行业已至拐点，什么行业景气度爆满。
        </div>
    </div>

    <div class="section">
        <h2>历史报告</h2>
        <div class="table-wrapper">
        <table>
            <thead>
                <tr><th style="text-align:left">日期</th><th>报告</th><th>源文件</th></tr>
            </thead>
            <tbody>{rows}
            </tbody>
        </table>
        </div>
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
