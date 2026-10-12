#!/usr/bin/env python3
"""跟踪卡 Markdown 解析器（纯标准库，无新依赖）。

卡片格式规范见 cards/DESIGN.md。解析宽松：缺失/未知区块不报错，
通过 warnings 反馈；调用方决定回退渲染。
"""
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
CARDS_DIR = os.path.join(ROOT, "cards")

CARD_STATUSES = {"逻辑强化中", "待验证", "已证伪"}
GATE_NAMES = {"增速", "量价齐升", "股价新高", "机构认可"}
KNOWN_SECTIONS = ("五问", "证伪", "指标字典", "事件", "复盘", "交易纪律")


def parse_front_matter(lines):
    """解析 --- 包裹的 key: value 行（仅顶格纯文本值）。"""
    meta = {}
    if not lines or lines[0].strip() != "---":
        return meta
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        m = re.match(r"^([A-Za-z_][\w]*)\s*:\s*(.*)$", ln.strip())
        if m:
            meta[m.group(1).strip()] = m.group(2).strip()
    return meta


def _split_sections(lines):
    """按 ## 标题切块，返回 [(title, [line, ...])]（保持顺序）。"""
    sections = []
    cur_title, cur_lines = None, []
    for ln in lines:
        m = re.match(r"^##\s+(.+)$", ln.strip())
        if m:
            if cur_title is not None:
                sections.append((cur_title, cur_lines))
            cur_title, cur_lines = m.group(1).strip(), []
        else:
            cur_lines.append(ln)
    if cur_title is not None:
        sections.append((cur_title, cur_lines))
    return sections


def parse_five_q(lines):
    """解析 `N. **标题**（YYYY-MM-DD）：正文`，正文可多行。"""
    qs, cur = [], None
    for ln in lines:
        m = re.match(
            r"^(\d+)\s*[.、]\s*\*\*(.+?)\*\*\s*[（(]?(\d{4}-\d{2}-\d{2})?[)）]?\s*[:：]?\s*(.*)$",
            ln.strip(),
        )
        if m:
            if cur:
                qs.append(cur)
            cur = {
                "no": int(m.group(1)),
                "title": m.group(2).strip(),
                "updated": m.group(3) or "",
                "body": [m.group(4)],
            }
        elif cur and ln.strip():
            cur["body"].append(ln.strip())
    if cur:
        qs.append(cur)
    return qs


def parse_checklist(lines):
    """解析 `- [ ]` / `- [x]` 清单。"""
    items = []
    for ln in lines:
        m = re.match(r"^[-*]\s+\[([ xX])\]\s*(.*)$", ln.strip())
        if m:
            items.append({"text": m.group(2).strip(), "triggered": m.group(1) in ("x", "X")})
    return items


def parse_table(lines):
    """解析指标字典表：指标|数据源|频率|最新值|历史值。"""
    rows = []
    header_seen = False
    for ln in lines:
        s = ln.strip()
        if not s.startswith("|") or not s.endswith("|"):
            continue
        if re.fullmatch(r"\|[\s:\-|]+\|", s):
            header_seen = True
            continue
        cells = [c.strip() for c in s[1:-1].split("|")]
        if not header_seen or len(cells) < 5:
            continue
        rows.append({
            "metric": cells[0],
            "source": cells[1],
            "freq": cells[2],
            "latest": cells[3],
            "history": cells[4],
        })
    return rows


def parse_events(lines):
    """解析 `- YYYY-MM-DD 【类型】内容`。"""
    events = []
    for ln in lines:
        m = re.match(
            r"^[-*]\s+(\d{4}-\d{2}-\d{2})\s*(?:[【\[（(]([^】\]）)]+)[】\]）)]\s*)?(.*)$",
            ln.strip(),
        )
        if m:
            events.append({
                "date": m.group(1),
                "type": (m.group(2) or "其他").strip(),
                "text": (m.group(3) or "").strip(),
            })
    return events


def parse_reviews(lines):
    """解析 `### YYYY-MM-DD` + 三条编号问答。"""
    reviews, cur = [], None
    for ln in lines:
        m = re.match(r"^###\s+(\d{4}-\d{2}-\d{2})", ln.strip())
        if m:
            if cur:
                reviews.append(cur)
            cur = {"date": m.group(1), "q1": "", "q2": "", "q3": ""}
            continue
        if cur is None:
            continue
        qm = re.match(r"^(\d+)\s*[.、]\s*(.*)$", ln.strip())
        if qm and qm.group(1) in ("1", "2", "3"):
            cur["q" + qm.group(1)] = qm.group(2).strip()
    if cur:
        reviews.append(cur)
    return reviews


def load_card(code):
    """加载 cards/{code}.md，返回 (card | None, warnings | None)。"""
    path = os.path.join(CARDS_DIR, f"{code}.md")
    if not os.path.exists(path):
        return None, None
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    warnings = []
    meta = parse_front_matter(lines)
    body = lines
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                body = lines[i + 1:]
                break

    gates = []
    for g in re.split(r"[,，、]", meta.get("gates", "")):
        g = g.strip()
        if g in GATE_NAMES:
            gates.append(g)
        elif g:
            warnings.append(f"未知门槛: {g}")
    status = meta.get("status", "")
    if status and status not in CARD_STATUSES:
        warnings.append(f"未知状态: {status}（可用: {' / '.join(sorted(CARD_STATUSES))}）")
        status = ""

    card = {
        "code": code,
        "status": status,
        "added": meta.get("added", ""),
        "reason": meta.get("reason", ""),
        "gates": gates,
        "five_q": [],
        "falsify": [],
        "metrics": [],
        "events": [],
        "reviews": [],
        "discipline": [],
    }
    for title, sec_lines in _split_sections(body):
        if "五问" in title:
            card["five_q"] = parse_five_q(sec_lines)
        elif "证伪" in title:
            card["falsify"] = parse_checklist(sec_lines)
        elif "指标字典" in title:
            card["metrics"] = parse_table(sec_lines)
        elif "事件" in title:
            card["events"] = parse_events(sec_lines)
        elif "复盘" in title:
            card["reviews"] = parse_reviews(sec_lines)
        elif "交易纪律" in title:
            card["discipline"] = [ln.strip() for ln in sec_lines if ln.strip()]
        else:
            warnings.append(f"忽略未知区块: {title}")
    return card, (warnings or None)
