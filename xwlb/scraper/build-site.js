import fs from 'node:fs';
import path from 'node:path';

const contentDir = path.resolve(import.meta.dirname, '..', 'content');
const siteDir = path.resolve(import.meta.dirname, '..', 'docs');

fs.mkdirSync(siteDir, { recursive: true });

function getAllPosts() {
  if (!fs.existsSync(contentDir)) return [];
  return fs.readdirSync(contentDir)
    .filter(f => f.endsWith('.md'))
    .sort()
    .reverse()
    .map(f => {
      const slug = f.replace('.md', '');
      const content = fs.readFileSync(path.join(contentDir, f), 'utf-8');
      const firstLine = content.split('\n')[0] || '';
      const title = firstLine.replace(/^#\s*/, '');
      const preview = content.split('\n').filter(l => l && !l.startsWith('#') && !l.startsWith('>')).slice(0, 2).join(' ').slice(0, 120);
      return { slug, title, preview };
    });
}

function mdToHtml(md) {
  let html = md
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/^\> (.+)$/gm, '<blockquote>$1</blockquote>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2">$1</a>')
    .replace(/^- (.+)$/gm, '<li>$1</li>');

  html = html.replace(/(<li>.*<\/li>\n?)+/g, (match) => `<ul>${match}</ul>`);

  const paragraphs = html.split(/\n\n+/);
  html = paragraphs.map(p => {
    p = p.trim();
    if (!p) return '';
    if (/^<(h[1-6]|ul|ol|blockquote|li)/.test(p)) return p;
    return `<p>${p.replace(/\n/g, '<br>')}</p>`;
  }).join('\n');

  return html;
}

function renderPage(title, bodyContent, isIndex = false) {
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${title} - 新闻联播文字版</title>
<style>
  :root { --bg: #fff; --fg: #1a1a1a; --muted: #666; --border: #e5e5e5; --accent: #c0392b; --link: #2980b9; }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #1a1a1a; --fg: #e5e5e5; --muted: #999; --border: #333; --accent: #e74c3c; --link: #5dade2; }
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif; background: var(--bg); color: var(--fg); line-height: 1.8; max-width: 800px; margin: 0 auto; padding: 2rem 1.5rem; }
  header { border-bottom: 3px solid var(--accent); padding-bottom: 1rem; margin-bottom: 2rem; }
  header h1 { font-size: 1.5rem; }
  header h1 a { color: var(--fg); text-decoration: none; }
  header p { color: var(--muted); font-size: 0.9rem; margin-top: 0.3rem; }
  h1 { font-size: 1.8rem; margin-bottom: 1rem; line-height: 1.3; }
  h2 { font-size: 1.3rem; margin: 2rem 0 0.8rem; color: var(--accent); border-left: 4px solid var(--accent); padding-left: 0.8rem; }
  h3 { font-size: 1.1rem; margin: 1.5rem 0 0.5rem; }
  p { margin-bottom: 0.8rem; text-indent: 2em; }
  blockquote { color: var(--muted); border-left: 3px solid var(--border); padding-left: 1rem; margin: 1rem 0; font-style: italic; }
  blockquote a { color: var(--link); }
  ul { margin: 0.5rem 0 1rem 2rem; }
  li { margin-bottom: 0.3rem; }
  a { color: var(--link); text-decoration: none; }
  a:hover { text-decoration: underline; }
  .post-list { list-style: none; margin: 0; padding: 0; }
  .post-list li { border-bottom: 1px solid var(--border); padding: 1rem 0; }
  .post-list .date { color: var(--muted); font-size: 0.85rem; }
  .post-list .title { font-size: 1.1rem; font-weight: 600; display: block; margin-top: 0.2rem; }
  .post-list .preview { color: var(--muted); font-size: 0.9rem; margin-top: 0.3rem; }
  footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border); color: var(--muted); font-size: 0.8rem; text-align: center; }
  nav.pagination { margin-top: 2rem; text-align: center; }
  nav.pagination a { display: inline-block; padding: 0.5rem 1rem; border: 1px solid var(--border); border-radius: 4px; margin: 0 0.3rem; }
</style>
</head>
<body>
<header>
  <h1><a href="${isIndex ? '' : 'index.html'}">新闻联播文字版</a></h1>
  <p>每日新闻联播文字版归档</p>
</header>
<main>
${bodyContent}
</main>
<footer>
  数据来源：<a href="http://mrxwlb.com" target="_blank">每日新闻联播</a> | 每日自动抓取
</footer>
</body>
</html>`;
}

function buildIndex(posts) {
  const byMonth = {};
  for (const post of posts) {
    const month = post.slug.slice(0, 7);
    if (!byMonth[month]) byMonth[month] = [];
    byMonth[month].push(post);
  }

  let html = '';
  for (const [month, monthPosts] of Object.entries(byMonth)) {
    const [y, m] = month.split('-');
    html += `<h2>${y}年${parseInt(m)}月</h2>\n<ul class="post-list">\n`;
    for (const post of monthPosts) {
      html += `<li>
  <span class="date">${post.slug}</span>
  <a class="title" href="${post.slug}.html">${post.title}</a>
  <div class="preview">${post.preview}...</div>
</li>\n`;
    }
    html += '</ul>\n';
  }

  return renderPage('首页', html, true);
}

function buildPost(post) {
  const filePath = path.join(contentDir, `${post.slug}.md`);
  const md = fs.readFileSync(filePath, 'utf-8');
  const body = mdToHtml(md);
  return renderPage(post.title, body);
}

const posts = getAllPosts();
console.log(`Building site with ${posts.length} posts...`);

fs.writeFileSync(path.join(siteDir, 'index.html'), buildIndex(posts), 'utf-8');
console.log('  Built index.html');

for (const post of posts) {
  fs.writeFileSync(path.join(siteDir, `${post.slug}.html`), buildPost(post), 'utf-8');
}
console.log(`  Built ${posts.length} post pages`);
console.log('Site built in docs/');
