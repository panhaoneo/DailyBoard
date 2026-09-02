#!/usr/bin/env python3
"""
将 Markdown 报告转换为简洁的 HTML（纯表格数据，无颜色，手机友好）
"""

import os
import re
from pathlib import Path


def md_to_simple_html(md_content, title):
    """转换 Markdown 为简洁 HTML"""
    
    # 转换表格
    def convert_table(lines):
        if len(lines) < 2:
            return ""
        
        html = '<div class="table-wrapper"><table>\n'
        
        # 表头
        header = lines[0]
        cells = [c.strip() for c in header.split('|')[1:-1]]
        html += '<thead><tr>'
        for cell in cells:
            html += f'<th>{cell}</th>'
        html += '</tr></thead>\n'
        
        # 表体（跳过分割行）
        html += '<tbody>\n'
        for line in lines[2:]:
            if not line.strip() or set(line.strip()) <= {'|', '-', ' ', ':'}:
                continue
            cells = [c.strip() for c in line.split('|')[1:-1]]
            html += '<tr>'
            for cell in cells:
                html += f'<td>{cell}</td>'
            html += '</tr>\n'
        html += '</tbody></table></div>\n'
        return html
    
    lines = md_content.split('\n')
    html_parts = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # 标题
        if line.startswith('# '):
            html_parts.append(f'<h1>{line[2:]}</h1>\n')
        elif line.startswith('## '):
            html_parts.append(f'<h2>{line[3:]}</h2>\n')
        elif line.startswith('### '):
            html_parts.append(f'<h3>{line[4:]}</h3>\n')
        
        # 引用
        elif line.startswith('> '):
            html_parts.append(f'<blockquote>{line[2:]}</blockquote>\n')
        
        # 列表
        elif line.startswith('- '):
            html_parts.append(f'<li>{line[2:]}</li>\n')
        
        # 表格（检测连续的多行 | 开头）
        elif line.startswith('|') and i + 1 < len(lines) and lines[i + 1].startswith('|'):
            table_lines = []
            while i < len(lines) and lines[i].startswith('|'):
                table_lines.append(lines[i])
                i += 1
            html_parts.append(convert_table(table_lines))
            continue
        
        # 普通段落
        elif line.strip():
            html_parts.append(f'<p>{line}</p>\n')
        
        i += 1
    
    body = '\n'.join(html_parts)
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    background: #fff; color: #333; line-height: 1.6; padding: 20px;
    max-width: 100%; overflow-x: auto;
}}
h1 {{ font-size: 24px; margin: 20px 0 10px; }}
h2 {{ font-size: 20px; margin: 24px 0 10px; }}
h3 {{ font-size: 16px; margin: 18px 0 8px; }}
p {{ margin: 10px 0; font-size: 14px; }}
blockquote {{
    border-left: 3px solid #ddd; padding-left: 12px;
    margin: 10px 0; color: #666; font-size: 13px;
}}
li {{ margin: 6px 0 6px 20px; font-size: 14px; }}
.table-wrapper {{
    overflow-x: auto; margin: 16px 0;
    -webkit-overflow-scrolling: touch;
}}
table {{
    width: 100%; border-collapse: collapse;
    font-size: 13px; min-width: 500px;
}}
th, td {{
    padding: 8px 10px; text-align: left;
    border: 1px solid #e0e0e0; white-space: nowrap;
}}
th {{ background: #f5f5f5; font-weight: 600; }}
tr:nth-child(even) {{ background: #fafafa; }}
@media (max-width: 768px) {{
    body {{ padding: 12px; }}
    h1 {{ font-size: 20px; }}
    h2 {{ font-size: 18px; }}
    table {{ font-size: 12px; }}
    th, td {{ padding: 6px 8px; }}
}}
</style>
</head>
<body>
{body}
</body>
</html>'''
    
    return html


def convert_all_markdown_files(output_dir):
    """转换目录下所有 markdown 文件"""
    md_pattern = re.compile(r'^market_report_(\d{4}-\d{2}-\d{2})\.md$')
    converted = 0
    
    for filename in os.listdir(output_dir):
        match = md_pattern.match(filename)
        if match:
            date_str = match.group(1)
            md_path = os.path.join(output_dir, filename)
            html_path = os.path.join(output_dir, f'market_report_{date_str}.html')
            
            with open(md_path, 'r', encoding='utf-8') as f:
                md_content = f.read()
            
            title = f'A股市场日报 - {date_str}'
            html_content = md_to_simple_html(md_content, title)
            
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            converted += 1
            print(f'Converted: {filename} -> market_report_{date_str}.html')
    
    return converted


if __name__ == '__main__':
    output_dir = 'daily-markt-report/output'
    count = convert_all_markdown_files(output_dir)
    print(f'\nConverted {count} markdown files to HTML')
