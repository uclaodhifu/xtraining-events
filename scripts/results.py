"""比完的 IFBB 职业赛，从 IFBB Pro League 官网比赛页抓各组前三名。

官网比赛页 https://www.ifbbpro.com/competition/<slug>/ 的 Results 里，每个组别一张表：
  MEN'S CLASSIC PHYSIQUE – OPEN
  # | NAME | COUNTRY | JUDGING | FINALS | TOTAL | PLACE
robots.txt 要求 Crawl-Delay: 10，所以每页之间等 10 秒。
抓到的成绩存在 data/results.json，抓齐了的比赛以后不再重复请求。
"""
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data/results.json"
UA = "XTrainingEventsBot/1.0 (personal fitness app; once a week)"
BJ = dt.timezone(dt.timedelta(hours=8))
LOOKBACK_DAYS = 45      # 只给最近 45 天比完的比赛找成绩
RETRY_DAYS = 21         # 比完 21 天内没出全的，每周再看一次

# 组别英文 → App 里用的中文（顺序要紧：先匹配长的）
DIVS = [
    ("WHEELCHAIR", "轮椅健美"), ("212", "212 健美"), ("CLASSIC PHYSIQUE", "古典健体"),
    ("WOMEN'S BODYBUILDING", "女子健美"), ("WOMENS BODYBUILDING", "女子健美"),
    ("WOMEN'S PHYSIQUE", "女子体格"), ("WOMENS PHYSIQUE", "女子体格"),
    ("MEN'S PHYSIQUE", "男子健体"), ("MENS PHYSIQUE", "男子健体"),
    ("BODYBUILDING", "男子健美"), ("FIGURE", "形体"), ("BIKINI", "比基尼"),
    ("WELLNESS", "健康身材"), ("FIT MODEL", "Fit Model"), ("FITNESS", "女子健身"),
]
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


class Tables(HTMLParser):
    """把页面里的表格拆成 [(表格前最近的标题, [[单元格文字...], ...]), ...]"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.rows, self.row, self.cell = [], None, None, None
        self.heading, self.htag, self.hbuf = "", None, []

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6") and self.rows is None:
            self.htag, self.hbuf = tag, []
        elif tag == "table":
            self.rows = []
        elif tag == "tr" and self.rows is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag == self.htag:
            t = " ".join("".join(self.hbuf).split())
            if t:
                self.heading = t
            self.htag = None
        elif tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if any(self.row):
                self.rows.append(self.row)
            self.row = None
        elif tag == "table" and self.rows is not None:
            self.tables.append((self.heading, self.rows))
            self.rows = None

    def handle_data(self, d):
        if self.cell is not None:
            self.cell.append(d)
        elif self.htag:
            self.hbuf.append(d)


def norm(s):
    return html.unescape(s).replace("’", "'").replace("‘", "'").upper()


def div_cn(title):
    t = norm(title)
    for k, v in DIVS:
        if k in t:
            return v
    return None


def parse_results(page):
    """返回 [{"d": 中文组别, "t": [第1, 第2, 第3]}]，只取公开组（OPEN），没有公开组才用别的。"""
    p = Tables()
    p.feed(page)
    found = {}  # 中文组别 -> (是否公开组, 名单)
    for heading, rows in p.tables:
        title, hdr_i = heading, None
        for i, r in enumerate(rows):
            up = [norm(c) for c in r]
            if "NAME" in up and "PLACE" in up:
                hdr_i = i
                break
            if len([c for c in r if c]) == 1:   # 只有一格的行就是组别标题
                title = [c for c in r if c][0]
        if hdr_i is None:
            continue
        up = [norm(c) for c in rows[hdr_i]]
        ni, pi = up.index("NAME"), up.index("PLACE")
        cn = div_cn(title)
        if not cn:
            continue
        podium = {}
        for r in rows[hdr_i + 1:]:
            if len(r) <= max(ni, pi):
                continue
            m = re.match(r"^(\d+)", r[pi])
            if m and 1 <= int(m.group(1)) <= 3 and r[ni]:
                podium.setdefault(int(m.group(1)), r[ni])
        if 1 not in podium:
            continue
        names = [podium[k] for k in sorted(podium)]
        is_open = "OPEN" in norm(title) or "MASTERS" not in norm(title)
        old = found.get(cn)
        if old is None or (is_open and not old[0]):
            found[cn] = (is_open, names)
    order = [v for _, v in DIVS]
    return [{"d": k, "t": found[k][1]} for k in sorted(found, key=order.index)]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"  打不开 {url}：{e}", file=sys.stderr)
        return None


def slugify(s):
    s = norm(s).lower().replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def candidates(e):
    """这场比赛在官网可能的比赛页地址"""
    out = []
    u = e.get("url") or ""
    if "/competition/" in u:
        out.append(u)
    names = list(e.get("ifbb") or [])
    if e.get("en"):
        names.append(f"{e['date'][:4]} {re.sub(r'[（(].*?[）)]', '', e['en'])}")
    for name in names:
        base = slugify(name)
        out += [f"https://www.ifbbpro.com/competition/{base}{s}/" for s in ("", "-2", "-3")]
    return list(dict.fromkeys(out))


def page_matches(page, e):
    """猜出来的地址要核对：页面里要有这场比赛的日期"""
    d = dt.date.fromisoformat(e["date"])
    keys = [d.isoformat(), f"{MONTHS[d.month - 1]} {d.day}", f"{MONTHS[d.month - 1][:3]} {d.day}"]
    return any(k in page for k in keys)


def add_results(events):
    cache = json.load(open(CACHE)) if CACHE.exists() else {}
    today = dt.datetime.now(BJ).date()
    first = True
    for e in events:
        if not e.get("date"):
            continue
        end = dt.date.fromisoformat(e.get("end") or e["date"])
        age = (today - end).days
        if e.get("res") and not e.get("resNote"):
            continue                       # 手动写好了的不动
        c = cache.get(e["id"])
        if c and c.get("res"):
            if not e.get("res") or len(c["res"]) > len(e["res"]):
                e["res"] = c["res"]
                e.pop("resNote", None)
            if c.get("done") or age > RETRY_DAYS:
                continue
        if age < 1 or age > LOOKBACK_DAYS:
            continue
        urls = candidates(e)
        if not urls:
            continue
        for u in urls:
            if not first:
                time.sleep(10)             # 官网要求每次请求间隔 10 秒
            first = False
            page = fetch(u)
            if not page:
                continue
            if u != e.get("url") and not page_matches(page, e):
                continue
            res = parse_results(page)
            print(f"  {e['name']}：{u} → {len(res)} 个组别有前三", file=sys.stderr)
            if res:
                cache[e["id"]] = {"url": u, "res": res, "checked": today.isoformat(),
                                  "done": age > 7}
                if not e.get("res") or len(res) >= len(e["res"]):
                    e["res"] = res
                    e.pop("resNote", None)
            break
    json.dump(cache, open(CACHE, "w"), ensure_ascii=False, indent=1)
    return events
