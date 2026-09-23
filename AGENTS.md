# DailyBoard

> 最后更新: 2026-09-23 | 当前分支: main（与 origin/main 同步）| 当前阶段: 四个模块全部上线、CI 全自动运行；日常只需维护 monitor 的人工填报字段

## 是什么

个人数据看板仓。所有内容由 GitHub Actions 定时抓取 → 生成静态页 → 直接提交 main → GitHub Pages 部署，无需人工参与。

- 线上: https://panhaoneo.github.io/DailyBoard/
- 仓库: `git@github.com:panhaoneo/DailyBoard.git`（SSH 协议）
- 四模块: 新闻联播文字版 `xwlb/`、A股市场日报 `daily-markt-report/`、新事物看板 `new-things/`、数据跟踪面板 `monitor/`（个股 3 只 + 猪周期主题）
- 线上子入口: `/xwlb/`、`/market/`、`/new-things/`、`/monitor/`

## 目录地图

- `.github/workflows/` — 调度中心，改任何自动化节奏都先看这里
  - `xwlb-scrape.yml` — 每天 UTC 15:50（北京 23:50）抓新闻联播；支持 `date` 输入手动补抓；Node 20
  - `market-report.yml` — 工作日 UTC 08:00（北京 16:00）生成日报；注入 repo secret `IWENCAI_API_KEY`
  - `monitor-update.yml` — 每天 UTC 02:00（北京 10:00）构建监控面板；commit `monitor/docs/` + `monitor/state/`
  - `deploy-pages.yml` — push main 触发，且在三个数据 workflow 完成后（workflow_run）再触发一次；构建 `_site/` 并部署
- `xwlb/` — `scraper/index.js`（抓取主逻辑 + 多源回退链）、`scraper/fetch.js`（HTTP 封装 + TLS 特例）、`scraper/build-site.js`（生成站点）；`content/*.md` 归档、`docs/` 站点产物（均入库）
- `daily-markt-report/` — `main.py` 入口；`config.py`（API 地址）；`data_fetcher.py`（东财全市场快照 + Sina 回退）；`market_stats.py`（统计）；`iwencai_fetcher.py`（创历史新高，问财 API，失败回退 THS/AKShare）；`report_generator.py`；`build_index.py`（output 索引页）；`cache/*.json`、`output/*`（增量缓存与产物，均入库）
- `new-things/` — 极简：`build.py` 把 `content/*.md` 转成 `docs/`
- `monitor/` — 最活跃模块
  - `build.py` 入口。加载 `stocks/*.json` 渲染个股页；内置抓取器：东财行情、东财业绩报表 `fetch_em_quarterly`（单季营收/净利/毛利率）、机构盈利预测 `fetch_em_forecast`（东财一致预期 RPT_WEB_RESPREDICT + 研报列表 reportapi、按机构去重）、上交所 CTFI `fetch_sse_ctfi_ct1`
  - `pigcycle.py`：猪周期主题页（玄田数据、新浪期货、新猪派抓取 + 手写 SVG 图表 + 拐点信号评估）；含"数据源不可用则保留上一版页面"守卫 `_xt_available`
  - `stocks/601872.json` 招商轮船、`603259.json` 药明康德、`603268.json` 松发股份（恒力重工）
  - `themes/pig_cycle.json` 猪周期主题
  - `state/last_values.json` — CTFI 历史读数（供页面"较上次"变化标签，必须持续入库）
  - `docs/` — 产物（已入库，同时充当部署构建失败时的回退版本）
- 根级: `convert_md_to_html.py`（部署时把 md 报告转简洁 HTML）；`skills/`（本地 skillhub 安装，被 gitignore）；`.qoder/settings.local.json`（CLI 权限白名单，被 git 跟踪但应视为本机文件）

## 环境与依赖

- 本机: Python 3.10.4（pyenv）、Node v24、gh CLI 已登录（panhaoneo）
- CI 固定: Python 3.11 / Node 20 —— 代码需保持 3.10 兼容（见已知坑 8）
- 依赖安装:
  - `pip install -r monitor/requirements.txt`（仅 requests）
  - `pip install -r daily-markt-report/requirements.txt`（requests + akshare，akshare 仅回退用）
  - `cd xwlb && npm ci`（cheerio）
- 本地 shell（`~/.zshrc`）: `IWENCAI_API_KEY`、`IWENCAI_BASE_URL` 两个环境变量（本地跑 market report 时需要；值不写在本文档）

## 常用命令

- 构建监控面板: `cd monitor && python3 build.py`（生成 docs/*.html；本地东财行情偶发失败属正常现象，页面其余部分照常生成）
- 本地跑 A股日报: `cd daily-markt-report && python3 main.py`；`--no-fetch` 用缓存重新生成（调试排版时用）
- 本地抓新闻联播: `cd xwlb && npm run scrape && npm run build`；补抓指定日期：`node scraper/index.js 2026-09-01`
- 构建新事物看板: `cd new-things && python3 build.py`
- 手动触发 CI: `gh workflow run monitor-update.yml`（同名命令可触发其它三个 workflow）
- 查看/跟踪 CI: `gh run list --limit 5`；`gh run watch <run-id> --exit-status`
- 线上验证: `curl -sL -o /dev/null -w "%{http_code}\n" https://panhaoneo.github.io/DailyBoard/monitor/`

## 凭证与数据

- GitHub repo secrets: `IWENCAI_API_KEY`（由 market-report.yml 注入环境变量同名使用）
- 本机 `~/.zshrc`: `IWENCAI_API_KEY` / `IWENCAI_BASE_URL`（换机需手动带）
- 问财 skillhub CLI 安装在项目外: `~/.iwencai-skillhub/`（换机需手动带或重装；历史坑见下）
- 无需密钥的公开数据源: 东财、新浪、上交所、玄田数据（xt.yangzhu.vip）、新猪派（xinmunet.com）——具体端点见各 fetcher 注释
- 入库产物即"数据备份": `monitor/state/`、`monitor/docs/`、`daily-markt-report/cache|output/`、`xwlb/content|docs/`、`new-things/docs/` —— 目录复制即可带走
- 不随目录迁移: GitHub Actions run 历史、Pages 部署记录、`~/.qoder-cn` 下的会话记录与自动记忆

## 硬约束与约定

- CI 每天多次向 main 直接提交（`chore: update ...`），本地推送前必须先 `git pull --rebase`；冲突处理固定套路见"已知坑 3"
- monitor 人工填报统一放 `stocks/*.json` / `themes/*.json` 的 `manual_value` + `manual_updated`（页面会按频率自动显示"待更新"提醒）
- monitor 页面新增自动数据的流程: ① build.py 写抓取函数 → ② `render_indicator_cell` 加渲染分支 → ③ JSON 指标行加 `auto_ref` → ④ 若是有状态抓取，同步改 `monitor-update.yml` 的 `git add` 列表（当前: `monitor/docs/ monitor/state/`）
- 数值变化必须用 chip 高亮（`delta_chip` / `pct_chip` 在 `pigcycle.py`，`build.py` 直接 import），保持一致视觉
- `.qoder/settings.local.json` 有本地改动时不要提交（用 stash 模式处理）

## 已知坑

1. **东财 push2 接口本地偶发 `RemoteDisconnected`** — 本机网络到东财不稳，CI 正常。重试即可，别为此改代码；`datacenter-web.eastmoney.com`（业绩/盈利预测）明显更稳，优先用它。
2. **玄田 xt.yangzhu.vip 对部分 CI runner 不可达（连接黑洞）** — 已做四层防护：超时 `(5, 15)`、连续 3 次失败熔断、核心源不可用时保留上一版页面（`_xt_available`）、deploy 步骤 `continue-on-error` + 8 分钟超时（失败时部署已提交的 docs）。改 pigcycle 抓取逻辑时不要破坏这些守卫。
3. **rebase 冲突是常态**（CI 每天提交撞车），固定操作:
   `git stash push -m wip -- .qoder/settings.local.json` → `git pull --rebase` → 冲突文件取舍：`git checkout --ours <file>` = 保留远程/CI 版本；`git checkout --theirs <file>` = 保留你本次本地提交的版本 → `git add` → `GIT_EDITOR=true git rebase --continue` → `git push` → `git stash pop`
4. **提交生成页前先看 diff**：本地跑东财行情失败时会生成"无报价"页面，不要用它覆盖 CI 的好版本（发现降级就 `git checkout -- <file>` 还原后再提交其余文件）。
5. **GITHUB_TOKEN 的 push 不触发其它 workflow** — 所以 deploy-pages.yml 同时监听 `push` 和 `workflow_run`（这是刻意设计，不是冗余）。
6. **xwlb 源链的历史环境坑**（改 `scraper/index.js` 回退链前必读）：mrxwlb.com 证书过期（`fetch.js` 里 `rejectUnauthorized: false` 是针对该单域的刻意设置）；govopendata 有 Cloudflare 挑战（机房 IP 403，靠 allorigins 代理绕过，慢、超时给 45s）；r.jina.ai 必须用极简请求头否则 403；baidaya 免费仅覆盖近 ~9 天（更早要登录）。
7. **cron 时点有业务含义**: xwlb 定北京 23:50 是因为 mrxwlb 约 23:45 才更新当天文字版；monitor 定北京 10:00 是因为玄田当日猪价约 9:00 前更新。调整前先确认数据源更新时点。
8. **保持 Python 3.10 兼容**: 别用嵌套同引号 f-string（3.12 语法）等新特性——本机 3.10.4 会直接语法报错。
9. **问财 key 缺失时的降级**: market report 的"创历史新高"会自动回退 THS/AKShare 源，页面不空但口径略不同；iwencai skillhub CLI 曾因命名空间冲突需要用 `touch ~/.iwencai-skillhub/cli/__init__.py` 修复。
10. **玄田接口口径**: `getzhujiahitsdata` 仅支持 ptype 1-5（日频价格）；`getmapdata` 的生猪产能止于 2025-10（陈旧），所以能繁母猪季度值改走新猪派 lab 页文本解析；新浪期货行情需带 Referer 头。

## 进行中的工作

- 已完成（全部入库并上线）: 四模块 + 猪周期主题页 + 3 只个股面板；monitor 具备变化高亮 chips、机构盈利预测自动抓取（一致预期 + 隐含 Q3/Q4）、油运"三面镜子/五问/复航账本"框架、猪周期拐点信号清单。
- 无未完成功能；日常由 CI 自动运行（节奏见目录地图）。
- 人工维护点（没有免费自动源的部分，季报/新闻出现新数字时更新 `manual_value` + `manual_updated`）:
  - `monitor/themes/pig_cycle.json` — 自繁自养利润、出栏均重、冻品库容率等
  - `monitor/stocks/601872.json` — 一年期期租报价、二手 VLCC 成交价
  - `monitor/stocks/603268.json` — 手持订单变化、新签节奏
- 未决问题（需用户拍板）: 霍尔木兹局势的新闻自动监控指标（曾建议，未采纳）。

## 迁移到新机器（清单）

1. `rsync -a` 整个目录（带隐藏文件）；重点确认 `.git`、`.github`、`.qoder`、`monitor/state`、`skills/` 都在 —— `skills/` 被 gitignore，只能靠目录复制带走。
2. 手动带（不在项目目录内）: `~/.iwencai-skillhub/`；`~/.zshrc` 中 IWENCAI_* 两行；如需 `--resume` 旧会话再加 `~/.qoder-cn/projects/-home-pan-DailyBoard/`。
3. 新机准备: SSH key 加 GitHub 或 `gh auth login`（git 走 SSH）；Python 3.10+、Node 20+；`pip install -r monitor/requirements.txt`、`cd xwlb && npm ci`。
4. 接管自检（一条命令批量核验）: `git status` 与 origin 同步 → `cd monitor && python3 build.py` 能生成 5 个页面 → `curl -sI https://panhaoneo.github.io/DailyBoard/` 和各子入口 200。

## 变更记录

- 2026-09-23: 初版。覆盖 4 模块结构、4 个 workflow 调度、secrets 路径、10 条历史坑、迁移清单与会话恢复路径。
