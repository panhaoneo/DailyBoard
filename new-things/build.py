#!/usr/bin/env python3
"""
构建"新事物"看板静态站点
将 content/*.md 转换为 docs/*.html + docs/index.html
"""

import os
import re
import glob
from datetime import datetime


CONTENT_DIR = os.path.join(os.path.dirname(__file__), "content")
DOCS_DIR = os.path.join(os.path.dirname(__file__), "docs")


def md_to_html(md):
    """简单的 Markdown 转 HTML"""
    html = md
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
    html = re.sub(r'^> (.+)$', r'<blockquote>\1</blockquote>', html, flags=re.MULTILINE)
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)
    html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    html = re.sub(r'(<li>.*</li>\n?)+', lambda m: f'<ul>{m.group(0)}</ul>', html)

    paragraphs = html.split('\n\n')
    result = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if re.match(r'^<(h[1-6]|ul|ol|blockquote|table)', p):
            result.append(p)
        else:
            result.append(f'<p>{p.replace(chr(10), "<br>")}</p>')
    return '\n'.join(result)


def render_page(title, body, is_index=False):
    """渲染页面模板"""
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} - 新事物看板</title>
<style>
:root {{ --bg: #fff; --fg: #1a1a1a; --muted: #666; --border: #e5e5e5; --accent: #27ae60; --link: #2980b9; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg: #1a1a1a; --fg: #e5e5e5; --muted: #999; --border: #333; --accent: #2ecc71; --link: #5dade2; }}
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif; background: var(--bg); color: var(--fg); line-height: 1.8; max-width: 800px; margin: 0 auto; padding: 2rem 1.5rem; }}
header {{ border-bottom: 3px solid var(--accent); padding-bottom: 1rem; margin-bottom: 2rem; }}
header h1 {{ font-size: 1.5rem; }}
header h1 a {{ color: var(--fg); text-decoration: none; }}
header p {{ color: var(--muted); font-size: 0.9rem; margin-top: 0.3rem; }}
h1 {{ font-size: 1.8rem; margin-bottom: 1rem; line-height: 1.3; }}
h2 {{ font-size: 1.3rem; margin: 2rem 0 0.8rem; color: var(--accent); border-left: 4px solid var(--accent); padding-left: 0.8rem; }}
h3 {{ font-size: 1.1rem; margin: 1.5rem 0 0.5rem; }}
p {{ margin-bottom: 0.8rem; text-indent: 2em; }}
blockquote {{ color: var(--muted); border-left: 3px solid var(--border); padding-left: 1rem; margin: 1rem 0; font-style: italic; }}
blockquote a {{ color: var(--link); }}
ul {{ margin: 0.5rem 0 1rem 2rem; }}
li {{ margin-bottom: 0.3rem; }}
a {{ color: var(--link); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.post-list {{ list-style: none; margin: 0; padding: 0; }}
.post-list li {{ border-bottom: 1px solid var(--border); padding: 1rem 0; }}
.post-list .date {{ color: var(--muted); font-size: 0.85rem; }}
.post-list .title {{ font-size: 1.1rem; font-weight: 600; display: block; margin-top: 0.2rem; }}
.post-list .preview {{ color: var(--muted); font-size: 0.9rem; margin-top: 0.3rem; }}
.quote {{ background: #f8f9fa; border-left: 3px solid var(--accent); padding: 12px 16px; margin-bottom: 24px; font-size: 0.95rem; color: #444; line-height: 1.8; }}
@media (prefers-color-scheme: dark) {{
  .quote {{ background: #2a2a2a; color: #ccc; }}
}}
footer {{ margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border); color: var(--muted); font-size: 0.8rem; text-align: center; }}
</style>
</head>
<body>
<header>
  <h1><a href="{'index.html' if not is_index else ''}">新事物看板</a></h1>
  <p>发现生活中的新业态、新产品</p>
</header>
<main>
{body}
</main>
<footer>
  人工收集与编辑 | 持续更新中
</footer>
</body>
</html>'''


def get_all_posts():
    """获取所有 markdown 文件"""
    if not os.path.exists(CONTENT_DIR):
        return []
    files = glob.glob(os.path.join(CONTENT_DIR, "*.md"))
    posts = []
    for f in sorted(files, reverse=True):
        slug = os.path.basename(f).replace('.md', '')
        with open(f, 'r', encoding='utf-8') as fh:
            content = fh.read()
        first_line = content.split('\n')[0] if content else ''
        title = re.sub(r'^#\s*', '', first_line).strip()
        if not title:
            title = slug
        preview_lines = [l for l in content.split('\n') if l.strip() and not l.startswith('#') and not l.startswith('>')]
        preview = ' '.join(preview_lines)[:120]
        posts.append({
            'slug': slug,
            'title': title,
            'preview': preview,
            'content': content,
            'filepath': f,
        })
    return posts


def build_index(posts):
    """构建首页"""
    quote = '<div class="quote">从生活角度出发，看这个世界有什么"新"业态、新产品在持续出现，举例：近两年的好想来、泡泡玛特，一旦发现，紧密跟踪。</div>'

    if not posts:
        body = quote + '<p style="color:var(--muted)">暂无内容，敬请期待。</p>'
        return render_page('首页', body, is_index=True)

    body = quote
    for post in posts:
        body += f'''<div style="border-bottom:1px solid var(--border);padding:1rem 0;">
  <span style="color:var(--muted);font-size:0.85rem;">{post["slug"]}</span>
  <a href="{post["slug"]}.html" style="font-size:1.1rem;font-weight:600;display:block;margin-top:0.2rem;">{post["title"]}</a>
  <div style="color:var(--muted);font-size:0.9rem;margin-top:0.3rem;">{post["preview"]}...</div>
</div>
'''

    return render_page('首页', body, is_index=True)


def build_post(post):
    """构建单篇文章"""
    body = md_to_html(post['content'])
    return render_page(post['title'], body)


def main():
    os.makedirs(DOCS_DIR, exist_ok=True)

    posts = get_all_posts()
    print(f"Building new-things site with {len(posts)} posts...")

    index_html = build_index(posts)
    with open(os.path.join(DOCS_DIR, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(index_html)
    print("  Built index.html")

    for post in posts:
        post_html = build_post(post)
        with open(os.path.join(DOCS_DIR, f'{post["slug"]}.html'), 'w', encoding='utf-8') as f:
            f.write(post_html)
        print(f"  Built {post['slug']}.html")

    print(f"Site built in {DOCS_DIR}/")


if __name__ == '__main__':
    main()
