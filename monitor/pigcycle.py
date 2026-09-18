#!/usr/bin/env python3
"""
猪周期跟踪页面 - 数据抓取与渲染

数据源（均为免费公开数据，无需登录）:
- 玄田数据（中国养猪网）:
    - /data/getzhujiahitsdata 核心数据日频序列（外三元/内三元/土杂猪/玉米/豆粕，含当日，近一年）
    - /data/getmapdata        供应维度（仔猪价/猪粮比/生猪产能/屠宰量/二元母猪/白肉价）
- 新浪财经期货: 生猪/玉米/豆粕主力连续行情与日K线
- 新猪派（积牧数据）: 能繁母猪存栏（统计局季度数据摘要）、7KG仔猪周度价格
"""

import json
import os
import re
import time
from datetime import datetime
from html import escape as esc
from zoneinfo import ZoneInfo

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

XT_BASE = "https://xt.yangzhu.vip"

FREQ_LABEL = {
    "daily": "日",
    "weekly": "周",
    "monthly": "月",
    "quarterly": "季",
    "yearly": "年度",
    "event": "事件",
}


def now_bj():
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def _f(val, default=None):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


# ============================================================
# 数据抓取
# ============================================================

def _post_xt(path, data, retries=3):
    last_err = None
    for i in range(retries):
        try:
            resp = requests.post(f"{XT_BASE}{path}", data=data, headers=HEADERS, timeout=25)
            js = resp.json()
            if js.get("code") == 200:
                return js.get("data")
            last_err = js.get("msg")
        except Exception as e:
            last_err = e
        if i < retries - 1:
            time.sleep(2 * (i + 1))
    print(f"  [!] 玄田数据 {path} 获取失败: {last_err}")
    return None


def fetch_xt_hist(ptype):
    """核心数据日频序列 -> [(date, value)]，ptype: 1外三元 2内三元 3土杂猪 4玉米 5豆粕"""
    data = _post_xt("/data/getzhujiahitsdata", {"ptype": ptype, "areano": -1, "datetype": 0})
    out = []
    for row in (data or []):
        d = row.get("pricedate")
        val = None
        for k, v in row.items():
            if k != "pricedate" and val is None:
                val = _f(v)
        if d and val is not None:
            out.append((d, val))
    return out


def fetch_xt_map(ptype):
    """供应维度序列，ptype: 1二元母猪 2仔猪 3猪肉批发价 6白条肉 7生猪产能 11猪粮比 13屠宰量"""
    return _post_xt("/data/getmapdata", {"ptype": ptype, "areano": -1}) or []


def fetch_futures(symbols=("LH0", "C0", "M0")):
    """新浪期货主力连续行情 -> {symbol: {name, last, chg_pct}}"""
    url = "https://hq.sinajs.cn/list=" + ",".join(f"nf_{s}" for s in symbols)
    try:
        resp = requests.get(
            url,
            headers={**HEADERS, "Referer": "https://finance.sina.com.cn"},
            timeout=15,
        )
        text = resp.content.decode("gbk", errors="ignore")
    except Exception as e:
        print(f"  [!] 期货行情获取失败: {e}")
        return {}
    out = {}
    for m in re.finditer(r'hq_str_nf_(\w+)="([^"]*)"', text):
        sym, raw = m.group(1), m.group(2)
        f = raw.split(",")
        if len(f) < 18 or not f[0]:
            continue
        last = _f(f[8])
        prev = _f(f[10]) or _f(f[5])
        if last is None or not last:
            last = prev
        chg = round((last - prev) / prev * 100, 2) if (last and prev) else None
        out[sym] = {"name": f[16], "last": last, "chg_pct": chg, "date": f[17] if len(f) > 17 else ""}
    return out


def fetch_futures_kline(symbol="LH0", n=40):
    """新浪期货日K线收盘 -> [(date, close)]"""
    url = (
        "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_a=/"
        f"InnerFuturesNewService.getDailyKLine?symbol={symbol}"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        m = re.search(r"=\((\[.*\])\);?", resp.text, re.S)
        rows = json.loads(m.group(1))
        out = [(r["d"], _f(r["c"])) for r in rows if r.get("d") and _f(r["c"]) is not None]
        return out[-n:]
    except Exception as e:
        print(f"  [!] 期货K线获取失败({symbol}): {e}")
        return []


def _sina_text_to_rows(html):
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


def _pct_with_sign(segment, keyword):
    """从文本片段中解析 环比/同比 百分比（带符号）"""
    m = re.search(keyword + r"[^%]{0,25}?([\d.]+)%", segment)
    if not m:
        return None
    val = float(m.group(1))
    seg = segment[m.start():m.end()]
    if re.search(r"减|降|跌|下滑|回落", seg):
        val = -val
    return val


def fetch_xinmunet_sow():
    """
    新猪派·积牧数据「全国能繁母猪存栏量」页面 -> 最新一期统计局/农业农村部数据
    {"period": "2026年二季度末", "value": 3780.0, "yoy": -6.5, "mom": -3.1, "published": "2026-07-16"}
    """
    url = "https://www.xinmunet.com/lab/%E5%85%A8%E5%9B%BD%E8%83%BD%E7%B9%81%E6%AF%8D%E7%8C%AA%E5%AD%98%E6%A0%8F%E9%87%8F"
    try:
        html = requests.get(url, headers=HEADERS, timeout=25).text
    except Exception as e:
        print(f"  [!] 新猪派能繁母猪页面获取失败: {e}")
        return None
    text = _sina_text_to_rows(html)
    m = re.search(r"(20\d{2}年[^，。；]{0,12}?)全国能繁母猪存栏量为([\d.]+)万头([^。]{0,140})", text)
    if not m:
        return None
    tail = m.group(3)
    pub = re.search(r"(20\d{2}-\d{2}-\d{2})", text[m.end():m.end() + 300])
    return {
        "period": m.group(1),
        "value": float(m.group(2)),
        "yoy": _pct_with_sign(tail, "同比"),
        "mom": _pct_with_sign(tail, "环比"),
        "published": pub.group(1) if pub else None,
    }


def fetch_xinmunet_piglet():
    """新猪派「7KG仔猪周度价格」-> {"week": 37, "value": 145, "chg_pct": -0.68, "range": "9月7日-9月13日"}"""
    lab_url = "https://www.xinmunet.com/lab/%E4%BB%94%E7%8C%AA%E4%BB%B7%E6%A0%BC"
    try:
        html = requests.get(lab_url, headers=HEADERS, timeout=25).text
    except Exception as e:
        print(f"  [!] 新猪派仔猪页面获取失败: {e}")
        return None
    art_url, week = None, None
    for tag in re.finditer(r'<a[^>]*href="(https://www\.xinmunet\.com/2026/\d+\.html)"[^>]*>(.*?)</a>', html, re.S):
        mm = re.search(r"第(\d+)周全国7KG仔猪", tag.group(2))
        if mm:
            art_url, week = tag.group(1), int(mm.group(1))
            break
    if not art_url:
        return None
    try:
        art = requests.get(art_url, headers=HEADERS, timeout=25).text
    except Exception as e:
        print(f"  [!] 新猪派仔猪文章获取失败: {e}")
        return None
    text = _sina_text_to_rows(art)
    m2 = re.search(r"全国7KG仔猪均价为([\d.]+)元/头([^。]{0,60})", text)
    if not m2:
        return None
    rng = re.search(r"第\d+周[（(]([^）)]+)[）)]", text)
    seg = m2.group(2)
    chg = None
    if "持平" in seg:
        chg = 0.0
    else:
        m3 = re.search(r"环比[^。]{0,16}?([\d.]+)%", seg)
        if m3:
            matched = seg[m3.start():m3.end()]
            chg = float(m3.group(1)) * (-1 if re.search(r"降|跌|下滑|回落", matched) else 1)
    return {"week": week, "value": float(m2.group(1)), "chg_pct": chg, "range": rng.group(1) if rng else ""}


# ============================================================
# SVG 图表（静态，无 JS 依赖）
# ============================================================

def svg_line(series, width=660, height=200, refs=None, unit="", fmt="{:.2f}", force_min=None):
    """
    series: [{"name": s, "color": c, "points": [(label, value)]}]
    refs:   [(value, label, color)] 参考线
    """
    all_pts = [p for s in series for p in s["points"]]
    if not all_pts:
        return '<p class="sub">数据获取失败</p>'
    vals = [v for _, v in all_pts]
    lo, hi = min(vals), max(vals)
    for rv, _, _ in (refs or []):
        lo, hi = min(lo, rv), max(hi, rv)
    if force_min is not None:
        lo = force_min
    if hi - lo < 1e-9:
        hi = lo + 1
    span = hi - lo
    lo -= span * 0.10
    hi += span * 0.10
    n = max(len(s["points"]) for s in series)
    pl, pr, pt, pb = 56, 16, 16, 26

    def X(i):
        return pl + (width - pl - pr) * (i / (n - 1) if n > 1 else 0.5)

    def Y(v):
        return pt + (height - pt - pb) * (1 - (v - lo) / (hi - lo))

    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" preserveAspectRatio="xMidYMid meet" role="img">']
    for k in range(3):
        v = lo + (hi - lo) * k / 2
        y = Y(v)
        parts.append(f'<line x1="{pl}" y1="{y:.1f}" x2="{width - pr}" y2="{y:.1f}" stroke="#eef2f7" stroke-width="1"/>')
        parts.append(f'<text x="{pl - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="10" fill="#999">{fmt.format(v)}</text>')
    for rv, label, color in (refs or []):
        if lo < rv < hi:
            y = Y(rv)
            parts.append(f'<line x1="{pl}" y1="{y:.1f}" x2="{width - pr}" y2="{y:.1f}" stroke="{color}" stroke-width="1" stroke-dasharray="5 4" opacity="0.75"/>')
            parts.append(f'<text x="{width - pr - 4}" y="{y - 4:.1f}" text-anchor="end" font-size="10" fill="{color}">{label}</text>')
    for s in series:
        pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, (_, v) in enumerate(s["points"]))
        parts.append(f'<polyline fill="none" stroke="{s["color"]}" stroke-width="1.8" points="{pts}"/>')
        lx, ly = X(len(s["points"]) - 1), Y(s["points"][-1][1])
        parts.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.6" fill="{s["color"]}"/>')
        anchor = "end" if lx > width * 0.7 else "start"
        dx = -5 if anchor == "end" else 5
        parts.append(f'<text x="{lx + dx:.1f}" y="{ly - 6:.1f}" text-anchor="{anchor}" font-size="10.5" font-weight="600" fill="{s["color"]}">{fmt.format(s["points"][-1][1])}{unit}</text>')
    for i in (0, n // 2, n - 1):
        si = min(i, len(series[0]["points"]) - 1)
        lbl = series[0]["points"][si][0]
        parts.append(f'<text x="{X(i):.1f}" y="{height - 8}" text-anchor="middle" font-size="10" fill="#999">{lbl}</text>')
    parts.append("</svg>")
    legend = "".join(
        f'<span class="lg"><i style="background:{s["color"]}"></i>{s["name"]}</span>' for s in series
    )
    return f'<div class="chart-legend">{legend}</div>' + "".join(parts)


# ============================================================
# 自动数据汇总 / 信号评估
# ============================================================

def collect_auto_data(cfg):
    print("  获取玄田数据（日频价格）...")
    xt = {
        "out": fetch_xt_hist(1),    # 外三元
        "inn": fetch_xt_hist(2),    # 内三元
        "soil": fetch_xt_hist(3),   # 土杂猪
        "corn": fetch_xt_hist(4),   # 玉米
        "bean": fetch_xt_hist(5),   # 豆粕
    }
    print("  获取玄田数据（供应维度）...")
    m = {
        "sow_price": fetch_xt_map(1),   # 二元母猪
        "piglet": fetch_xt_map(2),      # 仔猪
        "wholesale": fetch_xt_map(3),   # 猪肉批发价
        "baotiao": fetch_xt_map(6),     # 白条肉周价
        "capacity": fetch_xt_map(7),    # 生猪产能
        "ratio": fetch_xt_map(11),      # 猪粮比（官方周度）
        "slaughter": fetch_xt_map(13),  # 屠宰量
    }
    print("  获取期货行情与K线...")
    fut = fetch_futures()
    fut_k = fetch_futures_kline("LH0", 40)
    print("  获取新猪派数据（能繁母猪/仔猪周价）...")
    sow = fetch_xinmunet_sow()
    piglet = fetch_xinmunet_piglet()

    # 计算猪粮比（日频）: 外三元(元/公斤) / 玉米(元/公斤)
    corn_map = dict(xt["corn"])
    ratio_calc = []
    for d, v in xt["out"]:
        c = corn_map.get(d)
        if c:
            ratio_calc.append((d, round(v / (c / 1000), 2)))

    return {
        "xt": xt, "map": m, "fut": fut, "fut_kline": fut_k,
        "sow": sow, "piglet": piglet, "ratio_calc": ratio_calc,
    }


def _last_n(series, n):
    return series[-n:] if series else []


def _chg_over(series, days_val=None, points=None):
    """返回 (现值, 变化%) 与 N 个点/天之前的对比"""
    if not series or len(series) < 2:
        return None
    cur = series[-1][1]
    if points is not None:
        base = series[-1 - points][1] if len(series) > points else series[0][1]
    else:
        base = series[0][1]
    if not base:
        return None
    return round((cur - base) / base * 100, 2)


def _quarter_series(capacity):
    """玄田生猪产能中 季度末 记录 -> [(label, 能繁, 存栏, 出栏)]"""
    out = []
    for row in capacity:
        if len(row) >= 5 and "季度" in str(row[0]):
            vals = [_f(x) for x in row[1:5]]
            out.append((row[0], vals))
    return out


def eval_signals(cfg, ctx):
    """评估拐点确认信号清单 -> [(text, status, note)]；status: True/False/None(人工)"""
    xt, m = ctx["xt"], ctx["map"]
    ratio_calc, piglet_w = ctx["ratio_calc"], ctx["piglet"]
    sow = ctx["sow"]

    results = []
    for sig in cfg.get("signals", []):
        key = sig.get("auto_key")
        status, note = None, sig.get("note", "")

        if key == "sow_trend":
            qs = _quarter_series(m["capacity"])
            seq = [(label, v[0]) for label, v in qs if v[0]]
            if sow:
                seq.append((sow["period"], sow["value"]))
            if len(seq) >= 3:
                deltas = [(seq[i][1] - seq[i - 1][1]) for i in range(1, len(seq))]
                status = all(d < 0 for d in deltas[-2:])
                pair_notes = [
                    f"{seq[i - 1][0]}→{seq[i][0]}: {deltas[i - 1]:+.0f} 万头"
                    for i in range(len(seq) - 1, max(0, len(seq) - 3), -1)
                ]
                note = "最近两段: " + "；".join(pair_notes) + "（自动初判，跨期需人工核对）"
            elif sow:
                status = (sow.get("mom") or 0) < 0
                note = f'{sow["period"]} 环比 {sow["mom"]:+.1f}%' if sow.get("mom") is not None else ""
        elif key == "hog_stock_trend":
            qs = _quarter_series(m["capacity"])
            seq = [(label, v[2]) for label, v in qs if v[2]]
            if len(seq) >= 2:
                d = seq[-1][1] - seq[-2][1]
                status = d < 0
                note = f'{seq[-1][0]} {seq[-1][1]:,.0f} 万头（较上季 {"-" if d < 0 else "+"}{abs(d):,.0f}）'
        elif key == "ratio_above_6":
            if ratio_calc:
                cur = ratio_calc[-1][1]
                status = cur >= 6
                note = f"计算猪粮比 {cur:.2f}:1（{ratio_calc[-1][0]}）"
        elif key == "piglet_rebound":
            series = m["piglet"]
            if series and len(series) >= 2:
                last, prev = series[-1][1], series[-2][1]
                status = last > prev
                note = f"官方周度仔猪价 {prev}→{last} 元/公斤（{series[-2][0]}→{series[-1][0]}）"
            if piglet_w:
                if piglet_w.get("chg_pct") is None:
                    chg_txt = "—"
                elif piglet_w["chg_pct"] == 0:
                    chg_txt = "持平"
                else:
                    chg_txt = f'{piglet_w["chg_pct"]:+.2f}%'
                note = (note + "；" if note else "") + f'新猪派第{piglet_w["week"]}周 7KG仔猪 {piglet_w["value"]:.0f}元/头，环比{chg_txt}'
        else:
            st = sig.get("status")
            status = {"pass": True, "fail": False}.get(st)
            note = sig.get("note", "")

        results.append({"text": sig["text"], "status": status, "note": note})
    return results


def build_indicator_cells(ctx):
    """框架表中各指标的「最新数据」渲染片段（HTML）"""
    xt, m = ctx["xt"], ctx["map"]
    fut, sow = ctx["fut"], ctx["sow"]
    ratio_calc, piglet_w = ctx["ratio_calc"], ctx["piglet"]
    out = {}

    def sub(t):
        return f'<div class="sub">{t}</div>'

    def val(t):
        return f'<div class="value">{t}</div>'

    # 能繁母猪存栏
    caps = []
    if sow:
        mom = f'，环比 {sow["mom"]:+.1f}%' if sow.get("mom") is not None else ""
        yo = f'，同比 {sow["yoy"]:+.1f}%' if sow.get("yoy") is not None else ""
        caps.append(val(f'{sow["value"]:,.0f} 万头') + sub(f'{sow["period"]}（统计局，{sow.get("published", "-")}）{mom}{yo}'))
    qs = _quarter_series(m["capacity"])
    if qs:
        qlabel, qv = qs[-1]
        caps.append(sub(f'玄田记录: {qlabel} {qv[0]:,.0f} 万头'))
    if not caps:
        caps.append(sub("获取失败"))
    out["sow"] = "".join(caps)

    # 能繁环比
    if sow and sow.get("mom") is not None:
        warn = ' <span class="warn">去化中</span>' if sow["mom"] < 0 else ' <span class="warn">环比转正</span>'
        out["sow_mom"] = val(f'{sow["mom"]:+.1f}%') + sub(f'{sow["period"]}{warn}')
    else:
        out["sow_mom"] = sub("获取失败")

    # 生猪存栏 / 出栏
    if qs:
        qlabel, qv = qs[-1]
        out["hog_stock"] = val(f'{qv[2]:,.0f} 万头') + sub(f'{qlabel}（玄田）')
        out["hog_slaughter"] = val(f'{qv[3]:,.0f} 万头') + sub(f'{qlabel}（玄田）')
    else:
        out["hog_stock"] = out["hog_slaughter"] = sub("获取失败")

    # 屠宰量
    sl = m["slaughter"]
    if sl:
        rows = [r for r in sl if len(r) >= 2][-3:]
        latest = rows[-1] if rows else None
        if latest:
            out["slaughter"] = val(f'{_f(latest[1]):,.0f} 万头') + sub(" · ".join(f"{r[0]}: {_f(r[1]):,.0f}" for r in rows))
        else:
            out["slaughter"] = sub("获取失败")
    else:
        out["slaughter"] = sub("获取失败")

    # 猪价
    out_series = xt["out"]
    if out_series:
        cur = out_series[-1]
        w = _chg_over(out_series, points=7)
        out["hog_price"] = val(f"{cur[1]:.2f} 元/公斤") + sub(f'{cur[0]}（外三元）' + (f' · 近7日 {w:+.2f}%' if w is not None else ""))
    else:
        out["hog_price"] = sub("获取失败")

    # 仔猪
    parts = []
    if piglet_w:
        chg = ""
        if piglet_w.get("chg_pct") is not None:
            chg = "持平" if piglet_w["chg_pct"] == 0 else f'环比 {piglet_w["chg_pct"]:+.2f}%'
        parts.append(val(f'{piglet_w["value"]:.0f} 元/头') + sub(f'7KG · 第{piglet_w["week"]}周（{piglet_w.get("range", "")}）{chg}'))
    pz = m["piglet"]
    if pz:
        parts.append(sub(f'官方周度: {pz[-1][1]} 元/公斤（{pz[-1][0]}）'))
    out["piglet"] = "".join(parts) if parts else sub("获取失败")

    # 二元母猪
    sp = m["sow_price"]
    if sp:
        rows = [r for r in sp if len(r) >= 2][-2:]
        out["sow_price"] = val(f'{_f(rows[-1][1]):.2f} 元/公斤') + sub(rows[-1][0])
    else:
        out["sow_price"] = sub("获取失败")

    # 期货
    lh = fut.get("LH0")
    if lh and lh.get("last"):
        chg = f'{lh["chg_pct"]:+.2f}%' if lh.get("chg_pct") is not None else "-"
        cls = "up" if (lh.get("chg_pct") or 0) > 0 else "down" if (lh.get("chg_pct") or 0) < 0 else "flat"
        out["futures"] = val(f'{lh["last"]:,.0f} 元/吨 <span class="{cls}">{chg}</span>') + sub(f'LH主连 · {lh.get("date", "")}')
    else:
        out["futures"] = sub("获取失败")

    # 猪粮比（计算 + 官方周度）
    parts = []
    if ratio_calc:
        cur = ratio_calc[-1]
        flag = "一级预警区（低于5:1）" if cur[1] < 5 else "二级预警区（低于6:1）" if cur[1] < 6 else "盈亏平衡线上"
        parts.append(val(f"{cur[1]:.2f} : 1") + sub(f'{cur[0]} 计算值 · {flag}'))
    off = m["ratio"]
    if off:
        parts.append(sub(f'官方周度: {off[-1][1]}（{off[-1][0]}）'))
    out["ratio"] = "".join(parts) if parts else sub("获取失败")

    # 饲料成本
    parts = []
    if xt["corn"]:
        c = xt["corn"][-1]
        parts.append(val(f'{c[1]:,.0f} 元/吨') + sub(f'玉米 · {c[0]}'))
    if xt["bean"]:
        b = xt["bean"][-1]
        parts.append(sub(f'豆粕 {b[1]:,.0f} 元/吨 · {b[0]}'))
    fut_c, fut_m = fut.get("C0"), fut.get("M0")
    if fut_c and fut_m:
        parts.append(sub(f'期货: 玉米 {fut_c["last"]:,.0f} / 豆粕 {fut_m["last"]:,.0f}'))
    out["feed"] = "".join(parts) if parts else sub("获取失败")

    # 猪肉批发价
    ws = m["wholesale"]
    if ws and len(ws[-1]) >= 3:
        latest = ws[-1]
        prev = ws[-2] if len(ws) > 1 else latest
        d = _f(latest[2]) - _f(prev[2])
        out["wholesale"] = val(f'{_f(latest[2]):.2f} 元/公斤') + sub(f'{latest[0]} · 较前值 {"+" if d >= 0 else ""}{d:.2f}')
    else:
        out["wholesale"] = sub("获取失败")

    # 白条肉（周）
    bt = m["baotiao"]
    if bt:
        r = bt[-1]
        chg = ""
        if len(r) >= 4:
            chg = f' · 环比 {_f(r[2]):+.1f}% · 同比 {_f(r[3]):+.1f}%'
        out["baotiao"] = val(f'{_f(r[1]):.2f} 元/公斤') + sub(f"{r[0]}{chg}")
    else:
        out["baotiao"] = sub("获取失败")

    return out


# ============================================================
# 页面渲染
# ============================================================

CSS = """
:root { --bg: #f0f2f5; --card: #fff; --fg: #333; --muted: #888; --border: #eef2f7; --accent: #1a1a2e; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background: var(--bg); color: var(--fg); line-height: 1.7; padding: 20px; }
.container { max-width: 1100px; margin: 0 auto; }
.header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); color: #fff; padding: 28px 36px; border-radius: 12px; margin-bottom: 20px; }
.header h1 { font-size: 26px; margin-bottom: 6px; }
.header .subtitle { font-size: 13px; opacity: 0.8; margin-top: 6px; }
.header .badge { display: inline-block; background: rgba(255,255,255,0.14); border: 1px solid rgba(255,255,255,0.25); border-radius: 20px; padding: 2px 12px; font-size: 12.5px; margin-right: 8px; margin-top: 8px; }
.section { background: var(--card); border-radius: 12px; padding: 22px 28px; margin-bottom: 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.section h2 { font-size: 18px; color: var(--accent); margin-bottom: 14px; padding-bottom: 8px; border-bottom: 2px solid var(--border); }
.section h3 { font-size: 15px; color: #444; margin: 18px 0 8px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(168px, 1fr)); gap: 12px; }
.kcard { background: #fafbfc; border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; }
.kcard .label { font-size: 12.5px; color: var(--muted); }
.kcard .value { font-size: 19px; font-weight: 700; margin: 2px 0; }
.kcard .sub { font-size: 12px; color: var(--muted); }
.kcard .warn { color: #e67e22; }
.up { color: #d63031; }
.down { color: #00a854; }
.flat { color: #888; }
table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
th, td { padding: 8px 10px; text-align: center; border-bottom: 1px solid var(--border); vertical-align: top; }
th { background: #f8f9fb; color: #555; font-weight: 600; font-size: 12.5px; }
td.left { text-align: left; }
td.name { text-align: left; font-weight: 600; white-space: nowrap; }
.group-row td { background: #f4f7fb; text-align: left; font-weight: 700; color: #35506e; }
td .value { font-weight: 600; }
td .sub, .sub { color: var(--muted); font-size: 12px; margin-top: 2px; }
.warn { color: #e67e22; }
.chart-box { border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; margin-bottom: 14px; }
.chart-title { font-size: 13.5px; font-weight: 600; color: #444; margin-bottom: 6px; }
.chart-legend { font-size: 12px; color: #666; margin-bottom: 4px; }
.chart-legend .lg { margin-right: 14px; }
.chart-legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; vertical-align: -1px; }
.sig { list-style: none; }
.sig li { padding: 7px 0; border-bottom: 1px dashed var(--border); display: flex; gap: 10px; align-items: baseline; }
.sig .mark { font-weight: 700; min-width: 22px; }
.sig .pass { color: #00a854; }
.sig .fail { color: #d63031; }
.sig .manual { color: #b7950b; }
.sig .note { color: var(--muted); font-size: 12.5px; }
.events { list-style: none; }
.events li { padding: 8px 0; border-bottom: 1px dashed var(--border); }
.ev-date { color: var(--muted); font-size: 12.5px; margin-right: 8px; }
.footer { text-align: center; color: var(--muted); font-size: 12px; padding: 18px; }
a { color: #2980b9; text-decoration: none; }
a:hover { text-decoration: underline; }
"""


def render_page(cfg, ctx, cells, signals):
    build_time = now_bj().strftime("%Y-%m-%d %H:%M")
    xt, m, fut = ctx["xt"], ctx["map"], ctx["fut"]
    ratio_calc, piglet_w, sow = ctx["ratio_calc"], ctx["piglet"], ctx["sow"]

    # ---- 核心卡片 ----
    cards = []

    def card(label, value, sub, warn=False):
        cls = ' class="warn"' if warn else ""
        cards.append(f'<div class="kcard"><div class="label">{label}</div><div class="value">{value}</div><div class="sub"{cls}>{sub}</div></div>')

    if xt["out"]:
        cur = xt["out"][-1]
        w = _chg_over(xt["out"], points=7)
        card("生猪（外三元）", f"{cur[1]:.2f}", f'元/公斤 · {cur[0]} · 近7日 {w:+.2f}%' if w is not None else f"元/公斤 · {cur[0]}")
    if ratio_calc:
        cur = ratio_calc[-1]
        warn = cur[1] < 6
        flag = "一级预警" if cur[1] < 5 else "二级预警" if cur[1] < 6 else "平衡线上"
        card("猪粮比（计算）", f"{cur[1]:.2f}:1", f"{cur[0]} · {flag}", warn)
    if piglet_w:
        chg = "" if piglet_w.get("chg_pct") is None else (" 持平" if piglet_w["chg_pct"] == 0 else f' {piglet_w["chg_pct"]:+.2f}%')
        card("7KG仔猪", f'{piglet_w["value"]:.0f}', f'元/头 · 第{piglet_w["week"]}周{chg}')
    elif m["piglet"]:
        p = m["piglet"][-1]
        card("仔猪价", f"{p[1]}", f'元/公斤 · {p[0]}')
    if sow:
        mom = f'环比 {sow["mom"]:+.1f}%' if sow.get("mom") is not None else ""
        card("能繁母猪存栏", f'{sow["value"]:,.0f}', f'万头 · {sow["period"]} {mom}', warn=bool(sow.get("mom") and sow["mom"] > 0))
    lh = fut.get("LH0")
    if lh and lh.get("last"):
        chg = f'{lh["chg_pct"]:+.2f}%' if lh.get("chg_pct") is not None else ""
        cls = "up" if (lh.get("chg_pct") or 0) > 0 else "down" if (lh.get("chg_pct") or 0) < 0 else "flat"
        card("生猪期货主连", f'{lh["last"]:,.0f}', f'元/吨 <span class="{cls}">{chg}</span> · {lh.get("date", "")}')
    if xt["corn"]:
        card("玉米（现货）", f'{xt["corn"][-1][1]:,.0f}', f'元/吨 · {xt["corn"][-1][0]}')
    if xt["bean"]:
        card("豆粕（现货）", f'{xt["bean"][-1][1]:,.0f}', f'元/吨 · {xt["bean"][-1][0]}')
    if m["slaughter"]:
        r = m["slaughter"][-1]
        card("定点屠宰量", f'{_f(r[1]):,.0f}', f'万头 · {r[0]}')

    # ---- 图表 ----
    charts = []
    def chart(title, series, refs=None, unit="", fmt="{:.2f}", force_min=None):
        charts.append(
            f'<div class="chart-box"><div class="chart-title">{title}</div>'
            + svg_line(series, refs=refs, unit=unit, fmt=fmt, force_min=force_min)
            + "</div>"
        )

    def days_series(data, n=30):
        return [(d[5:], v) for d, v in _last_n(data, n)]

    s_out = [{"name": "外三元", "color": "#d63031", "points": days_series(xt["out"])}]
    if xt["inn"]:
        s_out.append({"name": "内三元", "color": "#e67e22", "points": days_series(xt["inn"])})
    chart("生猪价格（近30天，元/公斤）", s_out)

    if ratio_calc:
        chart(
            "猪粮比（计算值，近30天）",
            [{"name": "猪粮比", "color": "#8e44ad", "points": days_series(ratio_calc)}],
            refs=[(5, "一级预警 5:1", "#d63031"), (6, "二级预警 / 盈亏线 6:1", "#e67e22")],
            fmt="{:.1f}",
        )

    s_feed = []
    if xt["corn"]:
        s_feed.append({"name": "玉米", "color": "#2980b9", "points": days_series(xt["corn"])})
    if xt["bean"]:
        s_feed.append({"name": "豆粕", "color": "#27ae60", "points": days_series(xt["bean"])})
    if s_feed:
        chart("饲料原料（近30天，元/吨）", s_feed, fmt="{:,.0f}")

    if ctx["fut_kline"]:
        chart(
            "生猪期货主连收盘（近40个交易日，元/吨）",
            [{"name": "LH主连", "color": "#c0392b", "points": [(d[5:], v) for d, v in ctx["fut_kline"]]}],
            fmt="{:,.0f}",
        )

    if m["piglet"]:
        pts = [(r[0][5:], _f(r[1])) for r in m["piglet"][-8:] if len(r) >= 2]
        chart("仔猪价格（官方周度，近8周，元/公斤）", [{"name": "仔猪", "color": "#16a085", "points": pts}])

    # ---- 框架表 ----
    rows_html = ""
    last_group = None
    for ind in cfg["indicators"]:
        if ind.get("group") != last_group:
            last_group = ind["group"]
            rows_html += f'<tr class="group-row"><td colspan="6">{last_group}</td></tr>'
        freq = FREQ_LABEL.get(ind.get("freq", ""), ind.get("freq", ""))
        auto = ind.get("auto_key")
        cell_html = None
        if auto and auto in cells:
            cell_html = cells[auto]
        elif ind.get("manual_value"):
            mv = esc(str(ind["manual_value"]))
            mu = ind.get("manual_updated", "")
            cell_html = f'<div class="value">{mv}</div><div class="sub">填报: {mu}（人工跟踪）</div>'
        else:
            cell_html = '<div class="sub">人工跟踪</div>'
        rows_html += f"""
            <tr>
                <td class="name">{esc(ind.get("name", ""))}</td>
                <td class="left">{esc(ind.get("why", ""))}</td>
                <td>{esc(ind.get("lead", "—"))}</td>
                <td>{freq}</td>
                <td class="left">{esc(ind.get("threshold", ""))}</td>
                <td class="left">{cell_html}</td>
            </tr>"""

    # ---- 信号清单 ----
    sig_html = ""
    for s in signals:
        if s["status"] is True:
            mark, cls = "✓", "pass"
        elif s["status"] is False:
            mark, cls = "✗", "fail"
        else:
            mark, cls = "◇", "manual"
        note = f'<span class="note">{esc(s["note"])}</span>' if s["note"] else ""
        sig_html += f'<li><span class="mark {cls}">{mark}</span><span>{esc(s["text"])}</span>{note}</li>'

    # ---- 事件 ----
    events = cfg.get("events", [])
    if events:
        ev_items = "".join(
            f'<li><span class="ev-date">{esc(e.get("date", ""))}</span> {esc(e.get("text", ""))}</li>'
            for e in sorted(events, key=lambda x: x.get("date", ""), reverse=True)
        )
        events_html = f'<ul class="events">{ev_items}</ul>'
    else:
        events_html = '<p class="sub">暂无事件记录（可在 themes/pig_cycle.json 的 events 中追加）</p>'

    # ---- 可更新性说明 ----
    data_rows = [
        ("生猪/玉米/豆粕现货（日）", "玄田数据（中国养猪网）", f'最新 {xt["out"][-1][0] if xt["out"] else "—"}'),
        ("生猪期货行情与K线（日）", "新浪财经（大商所行情）", f'最新 {ctx["fut_kline"][-1][0] if ctx["fut_kline"] else "—"}'),
        ("仔猪周价（周）", "新猪派 7KG仔猪周报 + 玄田官方周度", f'第{piglet_w["week"]}周' if piglet_w else "—"),
        ("能繁母猪存栏（季）", "新猪派（统计局/农业农村部摘要）", sow["period"] if sow else "—"),
        ("屠宰量（月）", "玄田数据", m["slaughter"][-1][0] if m["slaughter"] else "—"),
    ]
    data_rows_html = "".join(f"<tr><td class='left'>{a}</td><td class='left'>{b}</td><td>{c}</td></tr>" for a, b, c in data_rows)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{cfg["title"]} · 数据跟踪</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>{cfg["title"]}</h1>
        <div>
            <span class="badge">能繁母猪存栏 → 生猪存栏 → 猪价 三变量框架</span>
            <span class="badge">上行缩短 · 磨底拉长（新范式）</span>
            <span class="badge">构建 {build_time}（北京时间）</span>
        </div>
        <div class="subtitle">{cfg.get("summary", "")}</div>
    </div>

    <div class="section">
        <h2>核心指标</h2>
        <div class="cards">{"".join(cards)}</div>
    </div>

    <div class="section">
        <h2>近一个月数据</h2>
        {"".join(charts)}
    </div>

    <div class="section">
        <h2>跟踪框架与最新数据</h2>
        <table>
            <thead><tr><th>指标</th><th>为什么重要</th><th>领先性</th><th>频率</th><th>阈值/参考</th><th>最新数据</th></tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
    </div>

    <div class="section">
        <h2>拐点确认信号清单</h2>
        <p class="sub" style="margin-bottom:8px">周期反转需多重信号共振验证；✓ 自动满足 / ✗ 未满足 / ◇ 人工跟踪</p>
        <ul class="sig">{sig_html}</ul>
    </div>

    <div class="section">
        <h2>事件记录</h2>
        {events_html}
    </div>

    <div class="section">
        <h2>数据来源与更新频率</h2>
        <table>
            <thead><tr><th>数据</th><th>来源</th><th>已更新至</th></tr></thead>
            <tbody>{data_rows_html}</tbody>
        </table>
        <p class="sub" style="margin-top:10px">本页由 GitHub Action 每日构建（北京时间约 10:00），官方低频数据（季度/月度）发布后自动跟进。猪粮比为「外三元现货价 ÷ 玉米现货价」计算值（元/公斤 ÷ 元/公斤）。</p>
    </div>

    <div class="footer">
        数据来源: 玄田数据（中国养猪网）、新浪财经、新猪派（积牧数据）· 均为免费公开数据<br>
        <a href="index.html">← 返回跟踪列表</a>
    </div>
</div>
</body>
</html>"""


def build_pig_cycle(cfg, docs_dir):
    """构建猪周期页面，返回索引卡片所需信息"""
    ctx = collect_auto_data(cfg)
    cells = build_indicator_cells(ctx)
    signals = eval_signals(cfg, ctx)
    html = render_page(cfg, ctx, cells, signals)
    out_path = os.path.join(docs_dir, f'{cfg["id"]}.html')
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  已生成 {out_path}")

    auto_count = sum(1 for i in cfg.get("indicators", []) if i.get("auto_key"))
    return {
        "id": cfg["id"],
        "title": cfg["title"],
        "summary": cfg.get("summary", ""),
        "meta": f'跟踪 {len(cfg.get("indicators", []))} 项指标 · {auto_count} 项自动抓取 · 每日更新',
    }
