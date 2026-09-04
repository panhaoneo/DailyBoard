"""
数据获取模块 - 从免费API获取A股行情数据

数据源优先级（参考 a-stock-data 项目）:
1. 新浪财经 - 低风控，用于A股列表和实时行情（一体化）
2. 新浪财经 - 用于历史K线
3. 腾讯财经 - 不封IP，用于指数行情
4. 东方财富 - 有风控，仅备用
"""

import time
import json
import os
import requests
from datetime import datetime
from config import INDICES

# 年内高低数据缓存文件
YEARLY_EXTREMES_CACHE = "cache/yearly_extremes.json"


def load_yearly_extremes_cache():
    """加载年内高低数据缓存"""
    if os.path.exists(YEARLY_EXTREMES_CACHE):
        try:
            with open(YEARLY_EXTREMES_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_yearly_extremes_cache(cache):
    """保存年内高低数据缓存"""
    os.makedirs(os.path.dirname(YEARLY_EXTREMES_CACHE), exist_ok=True)
    with open(YEARLY_EXTREMES_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _safe_float(val, default=None):
    """安全转换为浮点数"""
    if val is None or val == "-" or val == "" or val == "null":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def fetch_all_stocks_eastmoney():
    """
    使用东方财富API获取全部A股实时行情（含年初至今涨跌幅）
    分页请求，每页100条，约53页，10-15秒完成
    返回: list[dict] 每只股票包含 code, name, price, change_pct, high, low, open, pre_close, ytd_change_pct
    """
    print("[1/4] 获取A股实时行情（东方财富，含年初至今涨跌幅）...")

    time.sleep(1)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://quote.eastmoney.com/",
    })

    all_stocks = []
    page = 1

    while True:
        url = (
            f"https://push2.eastmoney.com/api/qt/clist/get"
            f"?pn={page}&pz=100&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
            f"&fltt=2&invt=2&dect=1&wbp2u=|0|0|0|web"
            f"&fid=f3&fs=m:0+t:6+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2"
            f"&fields=f2,f3,f4,f6,f12,f13,f14,f15,f16,f17,f18,f25,f100"
        )

        diffs = None
        for attempt in range(3):
            try:
                resp = session.get(url, timeout=20)
                data = resp.json()
                diffs = data.get("data", {}).get("diff", [])
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(3)
                else:
                    print(f"    [!] 第{page}页获取失败（重试3次）：{e}")

        if not diffs:
            break

        for item in diffs:
            price = _safe_float(item.get("f2"))
            change_pct = _safe_float(item.get("f3"), 0)
            high = _safe_float(item.get("f15"), 0)
            low = _safe_float(item.get("f16"), 0)
            open_price = _safe_float(item.get("f17"), 0)
            pre_close = _safe_float(item.get("f18"), 0)
            ytd_change = _safe_float(item.get("f25"))

            if price is None or price <= 0:
                continue

            all_stocks.append({
                "code": str(item.get("f12", "")),
                "name": item.get("f14", ""),
                "price": price,
                "change_pct": change_pct,
                "change_amt": _safe_float(item.get("f4"), 0),
                "volume": 0,
                "amount": _safe_float(item.get("f6"), 0),
                "high": high,
                "low": low,
                "open": open_price,
                "pre_close": pre_close,
                "ytd_change_pct": ytd_change,
                "industry": item.get("f100", ""),
            })

        if len(diffs) < 100:
            break

        page += 1
        time.sleep(0.2)

    print(f"  共获取 {len(all_stocks)} 只 A 股\n")
    return all_stocks


def fetch_all_stocks_sina():
    """
    使用新浪财经API获取全部A股实时行情
    API: Market_Center.getHQNodeData
    返回: list[dict] 每只股票包含 code, name, price, change_pct, ...
    """
    print("[1/4] 获取A股实时行情（新浪财经）...")

    all_stocks = []
    page = 1
    page_size = 80  # 新浪每页最多80条

    while True:
        url = (
            f"http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            f"Market_Center.getHQNodeData?page={page}&num={page_size}"
            f"&sort=symbol&asc=1&node=hs_a&symbol=&_s_r_a=auto"
        )

        try:
            resp = requests.get(
                url,
                headers={"Referer": "https://finance.sina.com.cn"},
                timeout=15
            )
            resp.encoding = "utf-8"

            if not resp.text.strip():
                print(f"    [!] 第{page}页返回空，跳过")
                break

            data = json.loads(resp.text)

            if not data:
                break

            for item in data:
                symbol = item.get("symbol", "")
                code = item.get("code", "")
                name = item.get("name", "")
                trade = _safe_float(item.get("trade"))
                settlement = _safe_float(item.get("settlement"))  # 昨收
                changepercent = _safe_float(item.get("changepercent"), 0)
                pricechange = _safe_float(item.get("pricechange"), 0)
                open_price = _safe_float(item.get("open"), 0)
                high = _safe_float(item.get("high"), 0)
                low = _safe_float(item.get("low"), 0)
                volume = _safe_float(item.get("volume"), 0)
                amount = _safe_float(item.get("amount"), 0)

                if trade is None or trade <= 0 or settlement is None or settlement <= 0:
                    continue

                all_stocks.append({
                    "code": symbol,
                    "name": name,
                    "price": trade,
                    "change_pct": changepercent,
                    "change_amt": pricechange,
                    "volume": volume,
                    "amount": amount,
                    "high": high,
                    "low": low,
                    "open": open_price,
                    "pre_close": settlement,
                })

            print(f"    已获取 {len(all_stocks)} 只股票 (第{page}页)")
    
            if len(data) < page_size:
                break
    
            page += 1
            time.sleep(0.5)  # 限流防封
    
        except Exception as e:
            print(f"    [!] 第{page}页获取失败：{e}")
            break
    
    print(f"  共获取 {len(all_stocks)} 只 A 股\n")
    return all_stocks


def fetch_stock_yearly_kline_sina(sina_code, datalen=250):
    """
    使用新浪历史K线接口获取股票日K线数据
    datalen: 获取的K线条数（默认250天覆盖全年）
    返回: list[dict] 日K线数据，用于计算年内最高/最低
    """
    url = (
        f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        f"CN_MarketData.getKLineData?symbol={sina_code}&scale=240&ma=no&datalen={datalen}"
    )

    try:
        resp = requests.get(url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=10)
        resp.encoding = "utf-8"
        text = resp.text.strip()

        if not text or text == "null":
            return []

        data = json.loads(text)

        result = []
        for item in data:
            date_str = item.get("day", "")
            if not date_str:
                continue

            # 只保留今年的数据
            year = int(date_str[:4])
            from datetime import datetime
            current_year = datetime.now().year
            if year != current_year:
                continue

            result.append({
                "date": date_str[:10],
                "open": _safe_float(item.get("open"), 0),
                "close": _safe_float(item.get("close"), 0),
                "high": _safe_float(item.get("high"), 0),
                "low": _safe_float(item.get("low"), 0),
                "volume": _safe_float(item.get("volume"), 0),
            })

        return result
    except Exception as e:
        return []


def fetch_all_stock_yearly_data(stocks, cache=None):
    """
    批量获取所有股票的今年日K线数据，计算年内最高/最低
    支持增量更新：当天已更新的股票直接使用缓存，只获取未更新的股票
    返回: 更新后的stocks列表，每个股票添加 year_high, year_low 字段
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # 加载缓存
    if cache is None:
        cache = load_yearly_extremes_cache()
    
    # 分类：已缓存（今天）和未缓存
    cached_codes = set()
    uncached_stocks = []
    
    for stock in stocks:
        code = stock["code"]
        cached = cache.get(code)
        # 缓存有效条件：日期是今天 且 包含klines
        if cached and cached.get("date") == today_str and cached.get("klines"):
            stock["year_high"] = cached["year_high"]
            stock["year_low"] = cached["year_low"]
            stock["klines"] = [
                {"date": d, "close": c} for d, c in cached["klines"].items()
            ]
            cached_codes.add(code)
        else:
            uncached_stocks.append(stock)
    
    cached_count = len(cached_codes)
    if cached_count > 0:
        print(f"[获取年内高低数据] 缓存命中 {cached_count} 只，还需获取 {len(uncached_stocks)} 只...")
    else:
        print(f"[获取年内高低数据] 共 {len(stocks)} 只股票...")
    
    # 只获取未缓存的股票
    processed = 0
    for stock in uncached_stocks:
        code = stock["code"]
        # 将代码转换为新浪K线代码格式
        if code.startswith("sh") or code.startswith("sz"):
            sina_code = code
        elif code.startswith("6") or code.startswith("9"):
            sina_code = f"sh{code}"
        else:
            sina_code = f"sz{code}"

        # 计算需要获取的K线天数
        # 如果有缓存但不是今天的，获取从缓存日期到现在的天数
        cached = cache.get(code)
        if cached and cached.get("date"):
            try:
                cache_date = datetime.strptime(cached["date"], "%Y-%m-%d")
                days_diff = (datetime.now() - cache_date).days
                datalen = min(days_diff + 5, 250)  # 加5天缓冲，最多250天
            except Exception:
                datalen = 250
        else:
            datalen = 250  # 首次获取，获取全年数据

        klines = fetch_stock_yearly_kline_sina(sina_code, datalen=datalen)

        if klines:
            # 计算年内最高/最低
            new_high = max(k["high"] for k in klines)
            new_low = min(k["low"] for k in klines if k["low"] > 0)
            
            # 如果有缓存，与缓存值合并
            if cached and cached.get("year_high"):
                year_high = max(cached["year_high"], new_high)
                year_low = min(cached["year_low"], new_low) if cached.get("year_low") and new_low > 0 else new_low
            else:
                year_high = new_high
                year_low = new_low

            stock["year_high"] = year_high
            stock["year_low"] = year_low
            stock["klines"] = klines  # 保存K线数据用于计算期间涨幅
            
            # 更新缓存（包含K线收盘价用于期间计算）
            kline_cache = {k["date"]: k["close"] for k in klines}
            cache[code] = {
                "year_high": year_high,
                "year_low": year_low,
                "date": today_str,
                "klines": kline_cache,
            }
        else:
            # 如果没有K线数据，使用当天最高/最低作为近似
            stock["year_high"] = stock.get("high", 0)
            stock["year_low"] = stock.get("low", 0)
            cache[code] = {
                "year_high": stock.get("high", 0),
                "year_low": stock.get("low", 0),
                "date": today_str,
            }

        processed += 1
        if processed % 100 == 0:
            print(f"  已处理 {processed}/{len(uncached_stocks)} 只股票")

        time.sleep(0.05)  # 限流

    # 保存缓存
    save_yearly_extremes_cache(cache)
    
    print(f"  年内高低数据获取完成\n")
    return stocks


def fetch_index_quotes_tencent():
    """
    使用腾讯财经API获取指数实时行情
    """
    print("[3/4] 获取指数行情...")
    indices_data = []

    for secid, name, sina_code in INDICES:
        url = f"http://qt.gtimg.cn/q={sina_code}"

        try:
            resp = requests.get(url, timeout=10)
            resp.encoding = "gbk"
            text = resp.text.strip()

            if "=" not in text:
                continue

            data_part = text.split("=", 1)[1].strip().strip('"').strip(";")
            if not data_part:
                continue

            fields = data_part.split("~")
            if len(fields) < 45:
                continue

            name_field = fields[2]
            current = _safe_float(fields[3])
            pre_close = _safe_float(fields[4])

            if current is None or current <= 0 or pre_close is None or pre_close <= 0:
                continue

            change_pct = _safe_float(fields[44], 0)

            indices_data.append({
                "code": sina_code[2:],
                "secid": secid,
                "name": name_field if name_field else name,
                "price": current,
                "change_pct": change_pct,
                "sina_code": sina_code,
            })
        except Exception as e:
            print(f"  [!] 获取指数 {name} 失败: {e}")

        time.sleep(0.2)

    print(f"  共获取 {len(indices_data)} 个指数\n")
    return indices_data


def fetch_index_kline_sina(sina_code, days=60):
    """
    使用新浪历史K线接口获取指数历史数据
    """
    url = (
        f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        f"CN_MarketData.getKLineData?symbol={sina_code}&scale=240&ma=no&datalen={days}"
    )

    try:
        resp = requests.get(url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=10)
        resp.encoding = "utf-8"
        text = resp.text.strip()

        data = json.loads(text)

        result = []
        for item in data:
            date_str = item.get("day", "")
            if not date_str:
                continue

            result.append({
                "date": date_str[:10],
                "open": _safe_float(item.get("open"), 0),
                "close": _safe_float(item.get("close"), 0),
                "high": _safe_float(item.get("high"), 0),
                "low": _safe_float(item.get("low"), 0),
                "volume": _safe_float(item.get("volume"), 0),
            })

        return result
    except Exception as e:
        print(f"    [!] 获取 {sina_code} K线失败: {e}")
        return []


def fetch_all_index_histories(days=250):
    """批量获取所有指数的历史K线数据（默认250天覆盖全年）"""
    print(f"[4/4] 获取指数历史K线数据（最近{days}天）...")
    histories = {}

    for secid, name, sina_code in INDICES:
        print(f"  获取 {name} ({sina_code})...")
        klines = fetch_index_kline_sina(sina_code, days=days)
        if klines:
            histories[name] = klines
            print(f"    获取到 {len(klines)} 条记录")
        time.sleep(0.3)

    print(f"  共获取 {len(histories)} 个指数历史数据\n")
    return histories


def fetch_market_data():
    """一次性获取所有市场数据"""
    stocks = fetch_all_stocks_eastmoney()
    if len(stocks) < 3000:
        print(f"[!] 东方财富仅获取 {len(stocks)} 只，等待10秒后重试...")
        time.sleep(10)
        stocks = fetch_all_stocks_eastmoney()
    if len(stocks) < 1000:
        print(f"[!] 东方财富数据不完整（{len(stocks)}只），回退新浪财经API...")
        stocks = fetch_all_stocks_sina()

    stocks = fetch_all_stock_yearly_data(stocks)  # 获取今年日K线，用于计算年内新低
    indices = fetch_index_quotes_tencent()
    histories = fetch_all_index_histories(days=250)

    return {
        "stocks": stocks,
        "indices": indices,
        "histories": histories,
    }
