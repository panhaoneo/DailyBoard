import * as cheerio from 'cheerio';
import { fetch } from './fetch.js';
import fs from 'node:fs';
import path from 'node:path';

const BASE_URL = 'http://mrxwlb.com';
const GOV_BASE_URL = 'https://cn.govopendata.com/xinwenlianbo';

function buildUrl(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  const encoded = `${y}%e5%b9%b4${m}%e6%9c%88${d}%e6%97%a5%e6%96%b0%e9%97%bb%e8%81%94%e6%92%ad%e6%96%87%e5%ad%97%e7%89%88`;
  return `${BASE_URL}/${y}/${m}/${d}/${encoded}/`;
}

function buildGovUrl(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${GOV_BASE_URL}/${y}${m}${d}/`;
}

function htmlToMarkdown(html, dateStr) {
  const $ = cheerio.load(html);
  const content = $('.entry-content');
  if (!content.length) return null;

  content.find('script, style, .sharedaddy, .jp-relatedposts').remove();

  const lines = [];
  lines.push(`# ${dateStr} 新闻联播文字版`);
  lines.push('');
  lines.push(`> 来源：[每日新闻联播](${BASE_URL})`);
  lines.push('');

  content.children().each((_, el) => {
    const tag = el.tagName;
    if (tag === 'p') {
      const text = $(el).text().trim();
      if (!text) return;
      const strong = $(el).find('strong');
      if (strong.length) {
        const strongText = strong.text().trim();
        if (strongText.includes('主要内容') || strongText.includes('文字版全文')) {
          lines.push(`**${strongText}**`);
          lines.push('');
          return;
        }
        const before = $(el).clone();
        before.find('strong').remove();
        const beforeText = before.text().trim();
        if (beforeText) lines.push(beforeText);
        lines.push('');
        lines.push(`## ${strongText}`);
        lines.push('');
        const after = strong.next();
        if (after.length && after[0].tagName !== 'strong') {
          // remaining text in p after strong is handled by next iterations
        }
        return;
      }
      lines.push(text);
      lines.push('');
    } else if (tag === 'ul' || tag === 'ol') {
      $(el).find('li').each((__, li) => {
        lines.push(`- ${$(li).text().trim()}`);
      });
      lines.push('');
    } else if (tag === 'h1' || tag === 'h2' || tag === 'h3') {
      const level = parseInt(tag[1]) + 1;
      lines.push(`${'#'.repeat(level)} ${$(el).text().trim()}`);
      lines.push('');
    }
  });

  return lines.join('\n').replace(/\n{3,}/g, '\n\n').trim() + '\n';
}

function govHtmlToMarkdown(html, dateStr) {
  const $ = cheerio.load(html);
  const articles = $('article.content-section');
  if (!articles.length) return null;

  const lines = [];
  lines.push(`# ${dateStr} 新闻联播文字版`);
  lines.push('');
  lines.push(`> 来源：[cn.govopendata.com 新闻联播](${GOV_BASE_URL})`);
  lines.push('');

  let count = 0;
  articles.each((_, el) => {
    const $el = $(el);
    const title = $el.find('h2.content-heading').first().text().trim();
    const paras = [];
    $el.find('.content-body p').each((__, p) => {
      const t = $(p).text().trim();
      if (t) paras.push(t);
    });
    if (!title && !paras.length) return;
    count++;
    if (title) {
      lines.push(`## ${title}`);
      lines.push('');
    }
    paras.forEach((t) => {
      lines.push(t);
      lines.push('');
    });
  });

  if (!count) return null;
  return lines.join('\n').replace(/\n{3,}/g, '\n\n').trim() + '\n';
}

function jinaToMarkdown(text, dateStr) {
  // r.jina.ai 返回: 头部元信息 + "Markdown Content:" + 正文markdown
  const marker = 'Markdown Content:';
  const idx = text.indexOf(marker);
  if (idx === -1) return null;
  const body = text.slice(idx + marker.length).trim();
  if (!body) return null;

  const lines = [];
  lines.push(`# ${dateStr} 新闻联播文字版`);
  lines.push('');
  lines.push(`> 来源：[cn.govopendata.com 新闻联播](${GOV_BASE_URL})`);
  lines.push('');
  lines.push(body);
  return lines.join('\n').replace(/\n{3,}/g, '\n\n').trim() + '\n';
}

async function scrapeDate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  const dateStr = `${y}年${m}月${d}日`;

  // 数据源按顺序尝试：主源 → govopendata直连 → 代理1(allorigins) → 代理2(jina)
  // govopendata 对机房IP有 Cloudflare JS 质询(403)，机房环境需走代理
  // jina 拒绝类浏览器请求头(403)，需用极简头
  const govUrl = buildGovUrl(date);
  const sources = [
    { name: 'mrxwlb', url: buildUrl(date), toMd: htmlToMarkdown },
    { name: 'govopendata', url: govUrl, toMd: govHtmlToMarkdown },
    {
      name: 'govopendata-proxy',
      url: `https://api.allorigins.win/raw?url=${encodeURIComponent(govUrl)}`,
      toMd: govHtmlToMarkdown,
      timeout: 45000,
    },
    {
      name: 'govopendata-jina',
      url: `https://r.jina.ai/${govUrl}`,
      toMd: jinaToMarkdown,
      timeout: 30000,
      rawHeaders: { 'User-Agent': 'Mozilla/5.0', 'Accept': '*/*' },
    },
  ];

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const MAX_ATTEMPTS = 3;

  for (const source of sources) {
    let md = null;
    for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
      const retryNote = attempt > 1 ? ` (retry ${attempt}/${MAX_ATTEMPTS})` : '';
      console.log(`Fetching: ${dateStr} -> ${source.url} (${source.name})${retryNote}`);
      try {
        const res = await fetch(source.url, {
          headers: source.headers,
          rawHeaders: source.rawHeaders,
          timeout: source.timeout,
        });
        if (!res.ok) {
          console.log(`  HTTP ${res.status}`);
          if (attempt < MAX_ATTEMPTS) { await sleep(5000 * attempt); continue; }
          break;
        }
        const html = await res.text();
        md = source.toMd(html, dateStr);
        if (!md) {
          console.log('  No content found');
          if (attempt < MAX_ATTEMPTS) { await sleep(5000 * attempt); continue; }
          break;
        }
        console.log(`  OK from ${source.name} (${md.length} chars)`);
        return { dateStr, md, slug: `${y}-${m}-${d}` };
      } catch (err) {
        console.error(`  Error: ${err.message}`);
        if (attempt < MAX_ATTEMPTS) { await sleep(5000 * attempt); continue; }
        break;
      }
    }
    console.log(`  Source ${source.name} exhausted, trying next source`);
  }

  console.log('  All sources failed, skipping');
  return null;
}

function getDateRange(startStr, endStr) {
  const dates = [];
  const current = new Date(startStr + 'T12:00:00');
  const end = new Date(endStr + 'T12:00:00');
  while (current <= end) {
    dates.push(new Date(current));
    current.setDate(current.getDate() + 1);
  }
  return dates;
}

async function main() {
  const contentDir = path.resolve(import.meta.dirname, '..', 'content');
  fs.mkdirSync(contentDir, { recursive: true });

  let startDate, endDate;

  const dateArg = process.argv[2];
  const rangeArg = process.argv[3];

  if (dateArg && /^\d{4}-\d{2}-\d{2}$/.test(dateArg)) {
    startDate = dateArg;
    endDate = rangeArg || dateArg;
  } else {
    const today = new Date();
    const y = today.getFullYear();
    const m = String(today.getMonth() + 1).padStart(2, '0');
    const d = String(today.getDate()).padStart(2, '0');
    startDate = `${y}-${m}-${d}`;
    endDate = startDate;
  }

  const dates = getDateRange(startDate, endDate);
  console.log(`Scraping ${dates.length} day(s): ${startDate} to ${endDate}\n`);

  let count = 0;
  for (const date of dates) {
    const result = await scrapeDate(date);
    if (result) {
      const filePath = path.join(contentDir, `${result.slug}.md`);
      fs.writeFileSync(filePath, result.md, 'utf-8');
      console.log(`  Saved: ${filePath}`);
      count++;
    }
    await new Promise(r => setTimeout(r, 1000));
  }

  console.log(`\nDone. Scraped ${count}/${dates.length} day(s).`);

  if (count < dates.length) {
    console.error(`Warning: ${dates.length - count} day(s) not scraped (HTTP 404 or no content)`);
    process.exitCode = 1;
  }
}

main().catch(console.error);
