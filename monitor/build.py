#!/usr/bin/env python3
"""
数据跟踪模块 - 个股关键指标与事件跟踪 + 行业周期主题（猪周期）

- 读取 stocks/*.json 配置（个股信息 + 需要跟踪的指标/事件）
- 读取 themes/*.json 配置（行业周期主题，见 pigcycle.py）
- 自动抓取可获取的数据：
    - 东方财富：个股行情、单季净利（财报）
    - 上海航运交易所：CTFI CT1（中东湾-中国宁波 VLCC）运价/TCE 参考
    - 玄田数据/新浪期货/新猪派：猪周期指标（日频猪价饲料、周度仔猪/猪粮比、季度能繁存栏）
- 生成 docs/index.html、docs/<股票代码>.html、docs/<主题>.html

更新节奏：每日运行（最高频指标为日度），低频指标按频率标记数据日期。
"""

import os
import re
import json
import glob
from datetime import datetime, date, timedelta
from html import escape as esc
from zoneinfo import ZoneInfo

import requests

import pigcycle
from pigcycle import delta_chip, pct_chip

ROOT = os.path.dirname(os.path.abspath(__file__))
STOCKS_DIR = os.path.join(ROOT, "stocks")
THEMES_DIR = os.path.join(ROOT, "themes")
DOCS_DIR = os.path.join(ROOT, "docs")
STATE_PATH = os.path.join(ROOT, "state", "last_values.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

FREQ_LABEL = {
    "weekly": "周",
    "monthly": "月",
    "quarterly": "季",
    "half_yearly": "半年",
    "yearly": "年度",
    "event": "事件",
}
FREQ_DAYS = {
    "weekly": 7,
    "monthly": 31,
    "quarterly": 92,
    "half_yearly": 184,
    "yearly": 366,
}


def now_bj():
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def record_ctfi_history(state, code, ctfi):
    """记录 CTFI 各期数据（同日幂等），返回上一期记录用于计算变化"""
    hist = state.setdefault(code, {}).setdefault("sse_ctfi_ct1", [])
    if ctfi and ctfi.get("date"):
        if not hist or hist[-1].get("date") != ctfi["date"]:
            hist.append({
                "date": ctfi["date"],
                "tce_std": ctfi.get("tce_std"),
                "ws": ctfi.get("ws"),
                "usd_per_ton": ctfi.get("usd_per_ton"),
            })
            del hist[:-30]
    return hist[-2] if len(hist) >= 2 else None


def calc_yoy(series):
    """单季净利同比：最新季度 vs 去年同季"""
    if not series or len(series) < 5:
        return None
    latest = series[-1]
    target = next(
        (s for s in series[:-1] if s["year"] == latest["year"] - 1 and s["quarter"] == latest["quarter"]),
        None,
    )
    if target and target.get("single"):
        return round((latest["single"] - target["single"]) / abs(target["single"]) * 100, 1)
    return None


def _pct_cls(v):
    return "up" if (v or 0) > 0 else "down" if (v or 0) < 0 else "flat"


def _safe_float(val, default=None):
    if val is None or val == "-" or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


# ============================================================
# 数据抓取
# ============================================================

def fetch_quote(market):
    """东方财富个股行情: market 形如 1.601872"""
    try:
        url = (
            f"https://push2.eastmoney.com/api/qt/stock/get"
            f"?secid={market}&fields=f43,f57,f58,f170,f169"
        )
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json().get("data") or {}
        price = _safe_float(data.get("f43"))
        chg = _safe_float(data.get("f170"))
        if price is None:
            return None
        return {
            "price": round(price / 100, 2),
            "change_pct": round(chg / 100, 2) if chg is not None else None,
        }
    except Exception as e:
        print(f"  [!] 行情获取失败: {e}")
        return None


def fetch_em_quarterly(code):
    """
    东方财富业绩报表 -> 单季净利/营收序列
    返回: {"latest": {...}, "series": [最近8个季度], "qoq": 环比%}
    """
    try:
        url = (
            "https://datacenter-web.eastmoney.com/api/data/v1/get"
            "?reportName=RPT_LICO_FN_CPD&columns=ALL"
            f"&filter=(SECURITY_CODE%3D%22{code}%22)"
            "&pageSize=12&sortColumns=REPORTDATE&sortTypes=-1"
        )
        resp = requests.get(url, headers=HEADERS, timeout=15)
        rows = ((resp.json().get("result") or {}).get("data")) or []
        if not rows:
            return None

        # 按报告期升序整理
        reports = []
        for r in rows:
            dt_str = (r.get("REPORTDATE") or "")[:10]
            net = _safe_float(r.get("PARENT_NETPROFIT"))
            if not dt_str or net is None:
                continue
            reports.append({
                "date": dt_str,
                "cum": net,
                "rev_cum": _safe_float(r.get("TOTAL_OPERATE_INCOME")),
                "ystz": _safe_float(r.get("YSTZ")),
                "sjltz": _safe_float(r.get("SJLTZ")),
                "xsmll": _safe_float(r.get("XSMLL")),
                "roe": _safe_float(r.get("WEIGHTAVG_ROE")),
            })
        reports.sort(key=lambda x: x["date"])

        # 计算单季净利 / 单季营收
        series = []
        prev_cum_by_year = {}
        prev_rev_by_year = {}
        for rep in reports:
            y = int(rep["date"][:4])
            q = (int(rep["date"][5:7]) - 1) // 3 + 1
            if q == 1 or y not in prev_cum_by_year:
                single = rep["cum"]
            else:
                single = rep["cum"] - prev_cum_by_year[y]
            prev_cum_by_year[y] = rep["cum"]

            rev_single = None
            if rep.get("rev_cum") is not None:
                if q == 1 or y not in prev_rev_by_year:
                    rev_single = rep["rev_cum"]
                else:
                    rev_single = rep["rev_cum"] - prev_rev_by_year[y]
                prev_rev_by_year[y] = rep["rev_cum"]

            series.append({
                "date": rep["date"],
                "year": y,
                "quarter": q,
                "single": single,
                "cum": rep["cum"],
                "rev_single": rev_single,
                "rev_cum": rep.get("rev_cum"),
                "ystz": rep.get("ystz"),
                "sjltz": rep.get("sjltz"),
                "xsmll": rep.get("xsmll"),
                "roe": rep.get("roe"),
            })

        if not series:
            return None

        latest = series[-1]
        qoq = None
        if len(series) >= 2 and series[-2]["single"] not in (0, None):
            qoq = round((latest["single"] - series[-2]["single"]) / abs(series[-2]["single"]) * 100, 1)

        return {
            "latest": latest,
            "series": series[-8:],
            "qoq": qoq,
        }
    except Exception as e:
        print(f"  [!] 财报获取失败: {e}")
        return None


def fetch_report_list(code, days=180):
    """东方财富个股研报列表（近 N 天）"""
    end = date.today()
    begin = end - timedelta(days=days)
    url = (
        "https://reportapi.eastmoney.com/report/list?industryCode=*&pageSize=50&industry=*"
        f"&rating=&ratingChange=&beginTime={begin.isoformat()}&endTime={end.isoformat()}"
        f"&pageNo=1&fields=&qType=0&orgCode=&code={code}&rcode=&p=1&pageNum=1"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        return resp.json().get("data") or []
    except Exception as e:
        print(f"  [!] 研报列表获取失败: {e}")
        return []


def fetch_em_forecast(code, quarterly=None):
    """
    机构盈利预测：东财一致预期 + 最新个股研报（按机构去重取最新）
    返回: {"orgs", "year_cur", "eps_cur", "np_cur", "np_next", "h1_np", "h2_implied",
           "tp_min", "tp_max", "shares", "reports": [{org, date, eps, title}]}
    """
    try:
        url = (
            "https://datacenter-web.eastmoney.com/api/data/v1/get"
            "?reportName=RPT_WEB_RESPREDICT&columns=ALL"
            f"&filter=(SECURITY_CODE%3D%22{code}%22)&pageSize=5"
        )
        resp = requests.get(url, headers=HEADERS, timeout=15)
        rows = ((resp.json().get("result") or {}).get("data")) or []
        if not rows:
            return None
        r = rows[0]
    except Exception as e:
        print(f"  [!] 盈利预测获取失败: {e}")
        return None

    year_actual = r.get("YEAR1")
    year_cur = r.get("YEAR2")
    eps_actual = _safe_float(r.get("EPS1"))
    eps_cur = _safe_float(r.get("EPS2"))
    eps_next = _safe_float(r.get("EPS3"))

    # 股本 = 已披露年度净利 / 当年实际 EPS
    shares = None
    h1_np = None
    if quarterly:
        for item in quarterly.get("series", []):
            if eps_actual and item["date"] == f"{year_actual}-12-31" and item.get("cum"):
                shares = item["cum"] / eps_actual
            if year_cur and item["date"] == f"{year_cur}-06-30" and item.get("cum"):
                h1_np = item["cum"] / 1e8

    np_cur = eps_cur * shares / 1e8 if (eps_cur and shares) else None
    np_next = eps_next * shares / 1e8 if (eps_next and shares) else None
    h2_implied = np_cur - h1_np if (np_cur is not None and h1_np is not None) else None

    # 最新研报，按机构去重
    by_org = {}
    for row in fetch_report_list(code):
        org = row.get("orgSName")
        d = (row.get("publishDate") or "")[:10]
        if not org or not d:
            continue
        if org not in by_org or d > by_org[org]["date"]:
            by_org[org] = {
                "org": org,
                "date": d,
                "eps": _safe_float(row.get("predictThisYearEps")),
                "title": (row.get("title") or "")[:24],
            }
    reports = sorted(by_org.values(), key=lambda x: x["date"], reverse=True)[:6]

    return {
        "orgs": r.get("RATING_ORG_NUM"),
        "year_cur": year_cur,
        "year_next": (year_cur + 1) if isinstance(year_cur, int) else None,
        "eps_cur": eps_cur,
        "np_cur": np_cur,
        "np_next": np_next,
        "h1_np": h1_np,
        "h2_implied": h2_implied,
        "tp_min": _safe_float(r.get("DEC_AIMPRICEMIN")),
        "tp_max": _safe_float(r.get("DEC_AIMPRICEMAX")),
        "shares": shares,
        "reports": reports,
    }


def fetch_sse_ctfi_ct1():
    """
    上海航运交易所 CTFI - CT1（中东湾拉斯坦努拉-中国宁波 270000MT VLCC）
    返回: {"date": ..., "ws": ..., "usd_per_ton": ..., "tce_std": ..., "tce_eco": ...}
    """
    try:
        s = requests.Session()
        s.headers.update(HEADERS)
        r = s.get("http://www.sse.net.cn/index/singleIndex?indexType=ctfi", timeout=15)
        token_m = re.search(r'name="CSRFToken" value="([^"]+)"', r.text)
        token = token_m.group(1) if token_m else ""
        r2 = s.post(
            "http://www.sse.net.cn/index/singleIndex?indexType=ctfi",
            data={"CSRFToken": token, "date": date.today().isoformat()},
            timeout=15,
        )
        html = r2.text

        date_m = re.search(r"CHINA IMPORT CRUDE OIL TANKER FREIGHT INDEX.*?(\d{4}-\d{2}-\d{2})", html, re.S)
        data_date = date_m.group(1) if date_m else None

        tbl = re.search(r"<table[^>]*>.*?</table>", html, re.S)
        if not tbl:
            return None
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbl.group(0), re.S)
        cells = []
        for row in rows:
            cs = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)
            cs = [re.sub(r"<[^>]+>", "", c).replace("\xa0", " ").strip() for c in cs]
            cells.append(cs)

        result = {"date": data_date}
        for i, cs in enumerate(cells):
            if cs and "(CT1)" in cs[0] and "中东湾" in cs[0]:
                for sub in cells[i + 1:i + 8]:
                    if not sub or len(sub) < 2:
                        break
                    unit, val = sub[0], _safe_float(sub[1])
                    if unit == "WS":
                        result["ws"] = val
                    elif unit == "美元/吨":
                        result["usd_per_ton"] = val
                    elif unit == "美元/天(标准航速)":
                        result["tce_std"] = val
                    elif unit == "美元/天(经济航速)":
                        result["tce_eco"] = val
                    elif "CT" in unit:  # 下一个航线，结束
                        break
                break
        return result if result.get("tce_std") or result.get("ws") else None
    except Exception as e:
        print(f"  [!] 上海航交所数据获取失败: {e}")
        return None


AUTO_FETCHERS = {
    "sse_ctfi_ct1": fetch_sse_ctfi_ct1,
    "em_quarterly": fetch_em_quarterly,
}


# ============================================================
# 页面渲染
# ============================================================

def fmt_amount(val):
    """亿元格式化"""
    if val is None:
        return "-"
    return f"{val / 1e8:.2f} 亿"


def freshness(indicator):
    """按频率检查手动更新是否过期，返回 (状态label, css class)"""
    freq = indicator.get("freq", "event")
    updated = indicator.get("manual_updated")
    if freq == "event" or not updated:
        return None
    try:
        upd = datetime.strptime(updated, "%Y-%m-%d").date()
    except ValueError:
        return None
    limit = FREQ_DAYS.get(freq)
    if limit and (date.today() - upd).days > limit:
        return (f"待更新（{FREQ_LABEL.get(freq, freq)}度）", "warn")
    return None


def render_indicator_cell(ind, auto_data):
    """渲染指标的"最新数据/状态"单元格"""
    parts = []

    manual_val = ind.get("manual_value")
    manual_upd = ind.get("manual_updated")
    unit = ind.get("unit", "")

    if manual_val not in (None, ""):
        val_txt = f"{manual_val}{unit}" if unit else str(manual_val)
        parts.append(
            f'<div class="value">{val_txt}</div>'
            f'<div class="sub">填报: {manual_upd or "-"}</div>'
        )

    auto_ref = ind.get("auto_ref")
    ref = auto_data.get(auto_ref) if auto_ref else None

    if auto_ref == "sse_ctfi_ct1":
        if ref:
            tce = ref.get("tce_std")
            prev = auto_data.get("sse_ctfi_ct1_prev")
            tce_chip = delta_chip(tce, prev.get("tce_std") if prev else None, unit=" 美元/天", digits=0, with_pct=True, ref_text=prev.get("date", "") if prev else "") if prev else ""
            ws_chip = delta_chip(ref.get("ws"), prev.get("ws") if prev else None, digits=0, ref_text=prev.get("date", "") if prev else "") if prev else ""
            tce_txt = f"{tce:,.0f} 美元/天{tce_chip}" if tce else "-"
            parts.append(
                f'<div class="value">{tce_txt}</div>'
                f'<div class="sub">参考（上海航交所 CT1 标准航速 TCE）<br>'
                f'WS {ref.get("ws", "-")}{ws_chip} · {ref.get("usd_per_ton", "-")} 美元/吨 · {ref.get("date", "-")}'
                f'</div>'
            )
        else:
            parts.append('<div class="sub">参考数据获取失败</div>')
    elif auto_ref == "em_quarterly":
        if ref:
            latest = ref["latest"]
            qoq = ref.get("qoq")
            yoy = calc_yoy(ref.get("series"))
            qoq_chip = pct_chip(qoq, ref_text="上季度")
            yoy_chip = pct_chip(yoy, ref_text="去年同期")
            warn = ' <span class="warn">⚠ 环比负增长</span>' if (qoq is not None and qoq < 0) else ""
            rev_line = ""
            if latest.get("rev_single") is not None:
                rev_line = f'单季营收 {fmt_amount(latest["rev_single"])}'
                if latest.get("xsmll") is not None:
                    rev_line += f' · 毛利率 {latest["xsmll"]:.1f}%'
                cum = []
                if latest.get("ystz") is not None:
                    cum.append(f'累计营收 <span class="{_pct_cls(latest["ystz"])}">{latest["ystz"]:+.1f}%</span>')
                if latest.get("sjltz") is not None:
                    cum.append(f'累计净利 <span class="{_pct_cls(latest["sjltz"])}">{latest["sjltz"]:+.1f}%</span>')
                if cum:
                    rev_line += f'（{" · ".join(cum)}）'
                rev_line = f'<div class="sub">{rev_line}</div>'
            parts.append(
                f'<div class="value">{latest["year"]}Q{latest["quarter"]} 单季净利 {fmt_amount(latest["single"])}</div>'
                f'{rev_line}'
                f'<div class="sub">净利环比 {qoq_chip or "-"} · 净利同比 {yoy_chip or "-"}</div>'
                f'<div class="sub">报告期 {latest["date"]}{warn}</div>'
            )
        else:
            parts.append('<div class="sub">财报数据获取失败</div>')
    elif auto_ref == "em_forecast":
        if ref:
            year = ref.get("year_cur")
            npc, nxt = ref.get("np_cur"), ref.get("np_next")
            cons = f"{npc:,.1f} 亿" if npc else (f'EPS {ref["eps_cur"]:.2f}' if ref.get("eps_cur") else "-")
            parts.append(f'<div class="value">{year}E 净利共识 {cons}（{ref.get("orgs", "-")} 家机构）</div>')
            line2 = []
            h2, h1 = ref.get("h2_implied"), ref.get("h1_np")
            if h2 is not None:
                chip = pct_chip((h2 - h1) / abs(h1) * 100, ref_text="上半年") if h1 else ""
                line2.append(f"隐含 H2（Q3+Q4）{h2:,.1f} 亿{chip}")
                if h1 is not None:
                    line2.append(f"H1 实际 {h1:,.1f} 亿")
            if nxt is not None:
                line2.append(f'{ref.get("year_next")}E {nxt:,.1f} 亿')
            if line2:
                parts.append(f'<div class="sub">{" · ".join(line2)}</div>')
            if ref.get("tp_min") or ref.get("tp_max"):
                parts.append(f'<div class="sub">机构目标价 {ref["tp_min"]} - {ref["tp_max"]}</div>')
            rpts = ref.get("reports") or []
            if rpts:
                items = []
                for x in rpts[:4]:
                    t = f'{x["org"]} {x["date"][5:]}'
                    if x.get("eps") and ref.get("shares"):
                        t += f'（{x["eps"] * ref["shares"] / 1e8:,.0f}亿）'
                    items.append(t)
                parts.append(f'<div class="sub">最新研报: {" · ".join(items)}</div>')
        else:
            parts.append('<div class="sub">盈利预测获取失败</div>')
    else:
        # 事件/人工跟踪类
        status = ind.get("status")
        if status:
            parts.append(
                f'<div class="value">{status}</div>'
                f'<div class="sub">更新: {manual_upd or "-"}</div>'
            )
        elif manual_val in (None, ""):
            parts.append('<div class="sub">待跟踪</div>')

    fresh = freshness(ind)
    if fresh:
        parts.append(f'<div class="warn">{fresh[0]}</div>')

    if not parts:
        parts.append('<div class="sub">-</div>')
    return "\n".join(parts)


def render_stock_page(stock, auto_data):
    code = stock["code"]
    name = stock["name"]
    quote = auto_data.get("em_quote")
    build_time = now_bj().strftime("%Y-%m-%d %H:%M")

    quote_html = ""
    if quote:
        pct = quote["change_pct"] or 0
        cls = "up" if pct > 0 else "down" if pct < 0 else "flat"
        arrow = "▲" if pct > 0 else "▼" if pct < 0 else "—"
        quote_html = f'<span class="quote-price">{quote["price"]}</span> <span class="chip {cls}">{arrow} {pct:+.2f}%</span>'

    ind_rows = ""
    for ind in stock.get("indicators", []):
        freq_label = FREQ_LABEL.get(ind.get("freq", "event"), ind.get("freq", "-"))
        cell = render_indicator_cell(ind, auto_data)
        ind_rows += f"""
            <tr>
                <td class="type">{ind.get("type", "")}</td>
                <td class="name">{ind.get("name", "")}</td>
                <td class="why">{ind.get("why", "")}</td>
                <td>{freq_label}</td>
                <td class="threshold">{ind.get("threshold", "")}</td>
                <td class="scenario">{ind.get("scenario", "")}</td>
                <td class="data">{cell}</td>
            </tr>"""

    # 观察框架 / 复航推演等附加区块（可选，来自 stock JSON 的 sections）
    extra_sections = ""
    for sec in stock.get("sections", []):
        items_html = "".join(f"<li>{esc(it)}</li>" for it in sec.get("items", []))
        extra_sections += f"""
    <div class="section">
        <h2>{esc(sec.get("title", ""))}</h2>
        <ul class="notes">{items_html}</ul>
    </div>"""

    # 财报明细（em_quarterly 存在时）
    fin_section = ""
    q = auto_data.get("em_quarterly")
    if q:
        fin_rows = ""
        for item in reversed(q["series"]):
            fin_rows += (
                f'<tr><td>{item["year"]}Q{item["quarter"]}</td>'
                f'<td>{item["date"]}</td>'
                f'<td>{fmt_amount(item.get("rev_single"))}</td>'
                f'<td>{fmt_amount(item["single"])}</td>'
                f'<td>{fmt_amount(item["cum"])}</td></tr>'
            )
        fin_section = f"""
    <div class="section">
        <h2>财报明细（单季）</h2>
        <table class="fin-table">
            <thead><tr><th>季度</th><th>报告期</th><th>单季营收</th><th>单季净利</th><th>累计净利</th></tr></thead>
            <tbody>{fin_rows}</tbody>
        </table>
    </div>"""

    events = stock.get("events", [])
    if events:
        ev_items = "".join(
            f'<li><span class="ev-date">{e.get("date", "")}</span> {e.get("text", "")}</li>'
            for e in sorted(events, key=lambda x: x.get("date", ""), reverse=True)
        )
        events_html = f'<ul class="events">{ev_items}</ul>'
    else:
        events_html = '<p class="sub">暂无事件记录（可在 stocks/{0}.json 的 events 中追加）</p>'.format(code)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name}（{code}）数据跟踪</title>
<style>
:root {{ --bg: #f0f2f5; --card: #fff; --fg: #333; --muted: #888; --border: #eef2f7; --accent: #1a1a2e; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background: var(--bg); color: var(--fg); line-height: 1.7; padding: 20px; }}
.container {{ max-width: 1100px; margin: 0 auto; }}
.header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); color: #fff; padding: 28px 36px; border-radius: 12px; margin-bottom: 20px; }}
.header h1 {{ font-size: 26px; margin-bottom: 6px; }}
.header .meta {{ font-size: 14px; opacity: 0.95; }}
.header .quote-price {{ font-size: 22px; font-weight: 700; }}
.header .subtitle {{ font-size: 13px; opacity: 0.75; margin-top: 8px; }}
.chip {{ display: inline-block; padding: 0 9px; border-radius: 10px; font-size: 12.5px; font-weight: 700; line-height: 20px; margin-left: 5px; vertical-align: 1px; white-space: nowrap; }}
.chip.up {{ background: #fdeceb; color: #d63031; }}
.chip.down {{ background: #e6f7ee; color: #00994d; }}
.chip.flat {{ background: #f0f2f5; color: #666; }}
.up {{ color: #d63031; }}
.down {{ color: #00994d; }}
.flat {{ color: #666; }}
.section {{ background: var(--card); border-radius: 12px; padding: 22px 28px; margin-bottom: 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
.section h2 {{ font-size: 18px; color: var(--accent); margin-bottom: 14px; padding-bottom: 8px; border-bottom: 2px solid var(--border); }}
table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
th, td {{ padding: 9px 10px; text-align: center; border-bottom: 1px solid var(--border); vertical-align: top; }}
th {{ background: #f8f9fb; color: #555; font-weight: 600; font-size: 12.5px; }}
td.type {{ white-space: nowrap; color: #555; }}
td.name {{ text-align: left; font-weight: 600; }}
td.why {{ text-align: left; color: var(--muted); font-size: 12.5px; }}
td.data {{ text-align: left; min-width: 200px; }}
td.data .value {{ font-weight: 600; }}
td.data .sub {{ color: var(--muted); font-size: 12px; margin-top: 2px; }}
.warn {{ color: #e67e22; font-size: 12px; margin-top: 2px; }}
.fin-table td, .fin-table th {{ text-align: center; }}
.events {{ list-style: none; }}
.events li {{ padding: 8px 0; border-bottom: 1px dashed var(--border); }}
.ev-date {{ color: var(--muted); font-size: 12.5px; margin-right: 8px; }}
.notes {{ list-style: none; }}
.notes li {{ padding: 7px 0 7px 16px; border-bottom: 1px dashed var(--border); position: relative; font-size: 13.5px; }}
.notes li::before {{ content: "▸"; position: absolute; left: 0; color: #2980b9; }}
.footer {{ text-align: center; color: var(--muted); font-size: 12px; padding: 18px; }}
a {{ color: #2980b9; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>{name} <span style="font-size:0.6em;opacity:0.7">{code}</span></h1>
        <div class="meta">{quote_html}</div>
        <div class="subtitle">{stock.get("summary", "")}</div>
        <div class="subtitle">{stock.get("sensitivity_note", "")}</div>
    </div>

    <div class="section">
        <h2>指标与事件跟踪</h2>
        <table>
            <thead>
                <tr><th>类型</th><th>指标/事件</th><th>为什么重要</th><th>频率</th><th>触发阈值</th><th>影响情景</th><th>最新数据/状态</th></tr>
            </thead>
            <tbody>{ind_rows}
            </tbody>
        </table>
    </div>

    {extra_sections}

    {fin_section}

    <div class="section">
        <h2>事件记录</h2>
        {events_html}
    </div>

    <div class="footer">
        构建时间: {build_time}（北京时间） · 行情/财报: 东方财富 · 运价参考: 上海航运交易所 CTFI<br>
        <a href="index.html">← 返回跟踪列表</a>
    </div>
</div>
</body>
</html>"""


def render_index(stocks, themes=None):
    build_time = now_bj().strftime("%Y-%m-%d %H:%M")

    cards = ""
    for theme in (themes or []):
        cards += f"""
        <a class="card theme" href="{theme["id"]}.html">
            <h2>{theme["title"]}</h2>
            <p>{theme.get("summary", "")}</p>
            <p class="meta">{theme.get("meta", "")}</p>
        </a>"""

    for stock in stocks:
        ind_count = len(stock.get("indicators", []))
        auto_count = sum(1 for i in stock.get("indicators", []) if i.get("auto_ref"))
        cards += f"""
        <a class="card" href="{stock["code"]}.html">
            <h2>{stock["name"]} <span class="code">{stock["code"]}</span></h2>
            <p>{stock.get("summary", "")}</p>
            <p class="meta">跟踪 {ind_count} 项指标/事件 · {auto_count} 项自动抓取</p>
        </a>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>数据跟踪</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background: #f0f2f5; color: #333; line-height: 1.7; padding: 32px 20px; }}
.container {{ max-width: 800px; margin: 0 auto; }}
h1 {{ font-size: 26px; color: #1a1a2e; margin-bottom: 6px; }}
.desc {{ color: #888; font-size: 13px; margin-bottom: 22px; }}
.card {{ display: block; background: #fff; border-radius: 12px; padding: 22px 26px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); text-decoration: none; color: inherit; transition: transform 0.15s; }}
.card:hover {{ transform: translateY(-3px); box-shadow: 0 4px 16px rgba(0,0,0,0.1); }}
.card.theme {{ border-left: 4px solid #16a085; }}
.card h2 {{ font-size: 19px; color: #1a1a2e; margin-bottom: 6px; }}
.card .code {{ font-size: 13px; color: #888; font-weight: 400; }}
.card p {{ color: #666; font-size: 13.5px; }}
.card .meta {{ color: #999; font-size: 12.5px; margin-top: 6px; }}
.footer {{ text-align: center; color: #999; font-size: 12px; padding: 20px; }}
</style>
</head>
<body>
<div class="container">
    <h1>数据跟踪</h1>
    <p class="desc">个股关键指标与事件 + 行业周期主题跟踪 · 更新节奏由指标频率决定 · 构建: {build_time}（北京时间）</p>
    {cards}
    <div class="footer">数据来源: 东方财富、上海航运交易所、玄田数据（中国养猪网）、新浪财经、新猪派（免费公开数据）</div>
</div>
</body>
</html>"""


def main():
    os.makedirs(DOCS_DIR, exist_ok=True)
    stock_files = sorted(glob.glob(os.path.join(STOCKS_DIR, "*.json")))
    state = load_state()

    stocks = []
    for path in stock_files:
        with open(path, encoding="utf-8") as f:
            stock = json.load(f)
        print(f"[跟踪] {stock['name']}（{stock['code']}）")

        auto_data = {}
        print("  获取行情...")
        auto_data["em_quote"] = fetch_quote(stock["market"])
        auto_refs = {i.get("auto_ref") for i in stock.get("indicators", [])}
        if "em_quarterly" in auto_refs or "em_forecast" in auto_refs:
            print("  获取财报...")
            auto_data["em_quarterly"] = fetch_em_quarterly(stock["code"])
        if "em_forecast" in auto_refs:
            print("  获取机构盈利预测...")
            auto_data["em_forecast"] = fetch_em_forecast(stock["code"], quarterly=auto_data.get("em_quarterly"))
        if "sse_ctfi_ct1" in auto_refs:
            print("  获取上海航交所 CTFI...")
            ctfi = fetch_sse_ctfi_ct1()
            auto_data["sse_ctfi_ct1"] = ctfi
            auto_data["sse_ctfi_ct1_prev"] = record_ctfi_history(state, stock["code"], ctfi)

        html = render_stock_page(stock, auto_data)
        out_path = os.path.join(DOCS_DIR, f"{stock['code']}.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  已生成 {out_path}")
        stocks.append(stock)

    save_state(state)

    themes = []
    for path in sorted(glob.glob(os.path.join(THEMES_DIR, "*.json"))):
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        print(f"[主题] {cfg['title']}")
        themes.append(pigcycle.build_pig_cycle(cfg, DOCS_DIR))

    index_html = render_index(stocks, themes)
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)
    print(f"已生成 {os.path.join(DOCS_DIR, 'index.html')}")


if __name__ == "__main__":
    main()
