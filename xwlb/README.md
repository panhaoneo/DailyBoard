# 新闻联播文字版

每日自动抓取 [CCTV 新闻联播](http://mrxwlb.com) 文字版，以 Markdown 格式归档，通过 GitHub Pages 展示。

## 项目结构

```
xwlb/
├── content/          # 抓取的 Markdown 文件 (YYYY-MM-DD.md)
├── docs/             # GitHub Pages 静态站点 (自动生成)
├── scraper/
│   ├── index.js      # 抓取脚本
│   ├── fetch.js      # HTTP 请求工具
│   └── build-site.js # 静态站点生成
├── .github/
│   └── workflows/
│       └── daily-scrape.yml  # 每日自动抓取 Action
└── package.json
```

## 使用方法

### 手动抓取

```bash
npm install

# 抓取今天
npm run scrape

# 抓取指定日期
node scraper/index.js 2026-09-01

# 抓取日期范围
node scraper/index.js 2026-08-01 2026-09-01
```

### 构建站点

```bash
npm run build
```

生成的静态站点在 `docs/` 目录。

## 自动抓取

GitHub Actions 每天北京时间 20:30 自动抓取当日新闻联播文字版，并部署到 GitHub Pages。

也可通过 Actions 页面手动触发，支持指定日期。

## 数据来源

- [每日新闻联播](http://mrxwlb.com)
