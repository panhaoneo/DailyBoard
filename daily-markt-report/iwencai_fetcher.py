"""
问财选股数据获取模块 - 通过同花顺问财OpenAPI获取选股数据
使用 hithink-astock-selector 技能的接口方式（数据来源: 同花顺问财）
需要环境变量 IWENCAI_API_KEY，未配置时返回 None（由调用方回退其他数据源）
"""

import os
import secrets

import requests

API_URL = "https://openapi.iwencai.com/v1/query2data"


def _request(query, page=1, limit=100, call_type="normal"):
    """调用问财网关，返回JSON或None"""
    api_key = os.environ.get("IWENCAI_API_KEY")
    if not api_key:
        print("[问财] 未配置环境变量 IWENCAI_API_KEY")
        return None

    payload = {
        "query": query,
        "page": str(page),
        "limit": str(limit),
        "is_cache": "1",
        "expand_index": "true",
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Claw-Call-Type": call_type,
        "X-Claw-Skill-Id": "hithink-astock-selector",
        "X-Claw-Skill-Version": "1.0.0",
        "X-Claw-Plugin-Id": "none",
        "X-Claw-Plugin-Version": "none",
        "X-Claw-Trace-Id": secrets.token_hex(32),
    }

    resp = requests.post(API_URL, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _normalize_stocks(data):
    """将问财返回的datas规范化为标准股票dict列表"""
    result = []
    for item in data.get("datas", []):
        full_code = str(item.get("股票代码", ""))
        code = full_code.split(".")[0]
        if not code:
            continue
        result.append({
            "code": code,
            "name": str(item.get("股票简称", "")),
            "price": round(float(item.get("最新价", 0) or 0), 2),
            "change_pct": round(float(item.get("最新涨跌幅", 0) or 0), 2),
        })
    return result


def fetch_iwencai_hist_high(exclude_bj=True):
    """
    通过问财查询今日股价创历史新高的A股股票
    返回: list[dict] 每只股票包含 code, name, price, change_pct
    失败（未配置key/网络错误）时返回 None
    """
    print("[问财] 查询今日股价创历史新高的A股...")
    query = "今日股价创历史新高的A股股票有哪些"

    try:
        data = _request(query)
        if not data or not data.get("datas"):
            print("  [!] 问财返回空数据")
            return None

        code_count = int(data.get("code_count", 0) or 0)
        stocks = _normalize_stocks(data)

        # 分页拉取全部
        page = 2
        while len(stocks) < code_count and page <= 10:
            page_data = _request(query, page=page)
            if not page_data or not page_data.get("datas"):
                break
            stocks.extend(_normalize_stocks(page_data))
            page += 1

        # 排除北交所（报告范围: 沪交所+深交所）
        if exclude_bj:
            before = len(stocks)
            stocks = [
                s for s in stocks
                if not (s["code"].startswith("4")
                        or s["code"].startswith("8")
                        or s["code"].startswith("92"))
            ]
            if len(stocks) != before:
                print(f"  [问财] 排除北交所 {before - len(stocks)} 只")

        print(f"  获取到 {len(stocks)} 只创历史新高股票 (问财code_count={code_count})")
        return stocks
    except Exception as e:
        print(f"  [!] 问财查询失败: {e}")
        return None


if __name__ == "__main__":
    result = fetch_iwencai_hist_high()
    if result:
        for s in result:
            print(f"{s['code']} {s['name']} {s['price']} {s['change_pct']:+.2f}%")
    else:
        print("无数据")
