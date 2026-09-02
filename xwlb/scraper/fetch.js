import https from 'node:https';
import http from 'node:http';

// mrxwlb.com currently serves an expired TLS certificate; this scraper is a
// read-only consumer of that single known host, so we skip verification here
// rather than globally. If the site fixes its cert, set this back to true.
const TLS_OPTIONS = { rejectUnauthorized: false };

export function fetch(url, options = {}) {
  return new Promise((resolve, reject) => {
    const mod = url.startsWith('https') ? https : http;
    const req = mod.get(url, {
      ...TLS_OPTIONS,
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; XWLB-Bot/1.0)',
        'Accept': 'text/html',
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
    req.setTimeout(15000, () => { req.destroy(); reject(new Error('timeout')); });
  });
}
