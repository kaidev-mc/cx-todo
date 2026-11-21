# -*- coding: utf-8 -*-
"""
学习通待办聚合（Playwright 版）
环境变量：CX_COOKIE（必填）、SC_KEY（Server酱）、TG_TOKEN/TG_CHAT（可选）
         CX_LIMIT（只扫前 N 门课，调试用）
"""
import os
import re
import sys
import json
import datetime
import requests
import urllib3
from playwright.sync_api import sync_playwright

urllib3.disable_warnings()

COOKIE = os.environ.get("CX_COOKIE", "").strip()
SC_KEY = os.environ.get("SC_KEY", "").strip()
TG_TOKEN = os.environ.get("TG_TOKEN", "").strip()
TG_CHAT = os.environ.get("TG_CHAT", "").strip()
OUT = "out"
LIMIT = int(os.environ.get("CX_LIMIT", "999"))

os.makedirs(OUT, exist_ok=True)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36")
H = {"Cookie": COOKIE, "User-Agent": UA, "Referer": "https://i.chaoxing.com/"}

EXTRACT_JS = """
() => [...document.querySelectorAll('p.overHidden2')].map(p => {
  const box = p.closest('li') || p.parentElement;
  const st = box ? box.querySelector('p.status') : null;
  let s = st ? (st.textContent || '').replace(/\\s+/g, ' ').trim() : '';
  if (!s && box) {
    const t = (box.textContent || '').replace(/\\s+/g, ' ');
    if (/已完成|已批阅|Completed|Submitted|Graded/i.test(t)) s = '已完成';
    else if (/未完成|未交|待做|Not\\s*Started|Unsubmitted/i.test(t)) s = '未完成';
  }
  if (!s) s = '未知';
  return {t: (p.textContent || '').replace(/\\s+/g, ' ').trim(), s: s};
}).filter(x => x.t)
"""

UNDONE_PAT = re.compile(r"To be Submitted|Not\s*Started|Unsubmitted|未完成|未交|待做|待提交", re.I)
DONE_PAT = re.compile(r"已完成|已批阅|待批阅|Completed|Submitted|Graded|Marked", re.I)


def is_done(status):
    s = status or ""
    if UNDONE_PAT.search(s):
        return False
    return bool(DONE_PAT.search(s))


def cookie_list():
    out = []
    for kv in COOKIE.split(";"):
        kv = kv.strip()
        if not kv or "=" not in kv:
            continue
        n, v = kv.split("=", 1)
        out.append({"name": n.strip(), "value": v.strip(),
                    "domain": ".chaoxing.com", "path": "/"})
    return out


def fetch_courses():
    r = requests.get("https://mooc1-api.chaoxing.com/mycourse/backclazzdata?view=json&rss=1",
                     headers=H, timeout=25, verify=False)
    data = r.json()
    if not data.get("channelList"):
        return []
    out = []
    for ch in data["channelList"]:
        c = ch.get("content", {}) or {}
        arr = (c.get("course", {}) or {}).get("data", []) or []
        if not arr:
            continue
        cd = arr[0]
        if cd.get("id") and c.get("id"):
            out.append({
                "name": (cd.get("name") or "?").strip(),
                "classId": c["id"],
                "courseId": cd["id"],
                "cpi": c.get("cpi") or ch.get("cpi"),
            })
    return out


def course_url(c):
    return (f"https://mooc1.chaoxing.com/mooc-ans/visit/stucoursemiddle"
            f"?courseid={c['courseId']}&clazzid={c['classId']}&vc=1"
            f"&cpi={c['cpi']}&ismooc2=1&v=2")


def scan_course(page, c, kind_label):
    items = []
    a = page.query_selector(f'a[title="{kind_label}"]')
    if not a:
        return items
    try:
        a.click(timeout=8000)
    except Exception:
        return items

    for _ in range(24):
        for f in page.frames:
            u = f.url or ""
            if "work/list" not in u and "exam-list" not in u:
                continue
            try:
                if f.query_selector("p.overHidden2"):
                    return [{"course": c["name"], "kind": kind_label,
                             "title": r["t"], "status": r["s"] or "未知"}
                            for r in f.evaluate(EXTRACT_JS)]
            except Exception:
                pass
        page.wait_for_timeout(500)
    return items


def collect(courses):
    rows = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA)
        ctx.add_cookies(cookie_list())
        page = ctx.new_page()

        for i, c in enumerate(courses[:LIMIT], 1):
            try:
                page.goto(course_url(c), wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2500)
            except Exception as e:
                print(f"[{i}] {c['name']} open fail {str(e)[:50]}")
                continue
            got = []
            for label in ("作业", "考试"):
                try:
                    got += scan_course(page, c, label)
                except Exception as e:
                    print(f"[{i}] {c['name']} {label} err {str(e)[:50]}")
            print(f"[{i}/{len(courses)}] {c['name']}: {len(got)}")
            if got and i <= 20:
                print("    sample:", got[0])
            rows += got
        browser.close()
    return rows


def push(title, body):
    if SC_KEY:
        try:
            r = requests.post(f"https://sctapi.ftqq.com/{SC_KEY}.send",
                              data={"title": title[:32], "desp": body}, timeout=15)
            print("[push]", r.status_code)
        except Exception as e:
            print("[push] fail", e)


def render_md(todo, total):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = ["# 学习通待办", "",
             f"**{len(todo)} 项未完成**（共扫描 {total} 条） · {now} 自动更新", ""]
    if todo:
        lines.append("| 课程 | 类型 | 内容 |")
        lines.append("|---|---|---|")
        for x in todo:
            lines.append(f'| {x["course"]} | {x["kind"]} | {x["title"].replace("|", "／")} |')
    else:
        lines.append("暂无未完成项")
    lines += ["", "---", "<sub>脚本自动生成</sub>", ""]
    return "\n".join(lines)


def render_html(todo):
    groups = {}
    for x in todo:
        groups.setdefault(x["course"], []).append(x)
    ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    blocks = []
    for course, items in ordered:
        rows = "\n".join(
            f'<li><i class="dot"></i><span class="t">{x["title"]}</span>'
            f'<span class="k">{x["kind"]}</span></li>' for x in items)
        blocks.append(
            f'<section><h2>{course}<em>{len(items)}</em></h2><ul>{rows}</ul></section>')

    now = datetime.datetime.now().strftime("%m-%d %H:%M")
    body = "\n".join(blocks) or '<p class="empty">暂无待办</p>'
    return f"""<!doctype html><html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#111113">
<title>学习通待办</title>
<style>
*{{box-sizing:border-box;-webkit-tap-highlight-color:transparent}}
body{{margin:0;padding:16px 12px 48px;background:#111113;color:#e9e9ec;
font:15px/1.5 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}}
header{{padding:4px 6px 14px;display:flex;align-items:baseline;gap:8px}}
h1{{font-size:22px;margin:0;font-weight:700;letter-spacing:-.3px}}
header b{{color:#ff4d6d;font-size:22px}}
header span{{color:#6f6f78;font-size:12px;margin-left:auto}}
section{{background:#1b1b1f;border-radius:14px;margin:9px 0;overflow:hidden}}
h2{{font-size:14px;font-weight:600;color:#b9b9c2;margin:0;padding:11px 14px;
background:#212127;display:flex;align-items:center;gap:8px}}
h2 em{{margin-left:auto;font-style:normal;font-size:12px;color:#ff4d6d;
background:#2a2024;border-radius:20px;padding:1px 8px}}
ul{{list-style:none;margin:0;padding:0}}
li{{display:flex;align-items:flex-start;gap:9px;padding:12px 14px;border-top:1px solid #242429}}
li:first-child{{border-top:0}}
.dot{{flex:0 0 6px;width:6px;height:6px;border-radius:50%;background:#ff4d6d;margin-top:7px}}
.t{{flex:1;font-size:15px;line-height:1.45;word-break:break-word}}
.k{{flex:0 0 auto;font-size:11px;color:#8b8b95;border:1px solid #33333b;
border-radius:5px;padding:1px 5px;margin-top:2px}}
.empty{{text-align:center;color:#8fe3b0;padding:40px 0}}
footer{{text-align:center;color:#55555e;font-size:12px;padding-top:18px}}
</style></head><body>
<header><h1>待办 <b>{len(todo)}</b></h1><span>{now} 更新</span></header>
{body}
<footer>数据来自学习通 · 每天自动更新</footer>
</body></html>"""


def main():
    if not COOKIE:
        print("no CX_COOKIE")
        return
    courses = fetch_courses()
    print(f"[courses] {len(courses)}")
    if not courses:
        push("学习通待办：Cookie 失效", "去 i.chaoxing.com 重新登录并更新 Secret CX_COOKIE")
        return

    rows = collect(courses)

    seen, uniq = set(), []
    for x in rows:
        k = (x["course"], x["kind"], x["title"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(x)

    todo = [x for x in uniq if not is_done(x["status"])]
    todo.sort(key=lambda x: (x["course"], x["kind"], x["title"]))

    open("todo.md", "w", encoding="utf-8").write(render_md(todo, len(uniq)))
    open(f"{OUT}/index.html", "w", encoding="utf-8").write(render_html(todo))
    json.dump({"updated": datetime.datetime.now().isoformat(timespec="seconds"),
               "todo": todo, "all": uniq},
              open(f"{OUT}/todo.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    body = "\n".join(f'[{x["kind"]}] {x["course"]}：{x["title"]}' for x in todo[:15])
    if len(todo) > 15:
        body += f"\n... 还有 {len(todo) - 15} 项"
    push(f"学习通待办 {len(todo)} 项", body or "全部做完了")
    print(f"[done] {len(todo)} todo / {len(uniq)} total")


if __name__ == "__main__":
    main()
