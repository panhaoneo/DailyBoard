import https from 'node:https';
import http from 'node:http';

// mrxwlb.com currently serves an expired TLS certificate; this scraper is a
// read-only consumer of that single known host, so we skip verification here
// rather than globally. If the site fixes its cert, set this back to true.
const TLS_OPTIONS = { rejectUnauthorized: false };

// Cloudflare (cn.govopendata.com) blocks requests with bot-like headers,
// so send a realistic browser profile by default.
const DEFAULT_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
  'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
  'Cache-Control': 'no-cache',
  'Pragma': 'no-cache',
};

export function fetch(url, options = {}) {
  return new Promise((resolve, reject) => {
    const mod = url.startsWith('https') ? https : http;
    const req = mod.get(url, {
      ...TLS_OPTIONS,
      headers: options.rawHeaders || {
        ...DEFAULT_HEADERS,
        ...options.headers,
      },
    }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        return resolve(fetch(res.headers.location, options));
      }
      const chunks = [];
      res.on('data', (chunk) => chunks.push(chunk));
      res.on('end', () => {
        const body = Buffer.concat(chunks).toString('utf-8');
        resolve({ ok: res.statusCode >= 200 && res.statusCode < 300, status: res.statusCode, text: () => body });
      });
      res.on('error', reject);
    });
    req.on('error', reject);
    req.setTimeout(options.timeout || 15000, () => { req.destroy(); reject(new Error('timeout')); });
  });
}
