# -*- coding: utf-8 -*-
"""
学习通待办聚合器
读环境变量：CX_COOKIE（必填）、SC_KEY（Server酱微信推送）、TG_TOKEN / TG_CHAT（可选）
输出：out/index.html（手机网页清单）、out/todo.json
本地调试：python todo_chaoxing.py --debug   会额外保存 dbg_*.html 便于对正则
"""
import os
import re
import sys
import json
import requests
import datetime
import subprocess

COOKIE = os.environ.get("CX_COOKIE", "")
SC_KEY = os.environ.get("SC_KEY", "")
TG_TOKEN = os.environ.get("TG_TOKEN", "")
TG_CHAT = os.environ.get("TG_CHAT", "")
OUT = "out"
DEBUG = "--debug" in sys.argv

os.makedirs(OUT, exist_ok=True)

H = {
    "Cookie": COOKIE,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://mooc1.chaoxing.com/",
}

WORK = ("https://mooc1.chaoxing.com/mooc-ans/work/list"
        "?classId={classId}&courseId={courseId}&isdisplaytable=2&mooc2=1")
EXAM = ("https://mooc1.chaoxing.com/mooc-ans/exam-ans/exam/test/reVersionTestList"
        "?classId={classId}&courseId={courseId}")


def courses():
    """我的课程列表（含未结束的课）"""
    out = []
    try:
        r = requests.get(
            "https://mooc1-api.chaoxing.com/mycourse/backclazzdata?view=json&rss=1",
            headers=H, timeout=20)
        data = r.json()
    except Exception as e:
        print("[courses] fail:", e)
        return out

    for ch in data.get("channelList", []) or []:
        c = ch.get("content", {}) or {}
        arr = (c.get("course", {}) or {}).get("data", []) or []
        if not arr:
            continue
        cd = arr[0]
        cid, clid = cd.get("id"), c.get("id")
        if cid and clid:
            out.append({
                "courseId": cid,
                "classId": clid,
                "name": (cd.get("name") or "?").strip(),
            })
    return out


def parse(html, course, kind):
    """从列表页 HTML 里抠出条目；结构千人千面，这里做宽松匹配"""
    items = []
    for b in re.findall(r"<li[^>]*>(.*?)</li>", html, re.S):
        m = re.search(r'title="([^"]+)"', b)
        if not m:
            m = re.search(r"<p[^>]*>(.*?)</p>", b, re.S)
        if not m:
            m = re.search(r"<a[^>]*>(.*?)</a>", b, re.S)
        if not m:
            continue
        title = re.sub(r"<[^>]+>", "", m.group(1))
        title = re.sub(r"\s+", " ", title).strip()
        if len(title) < 2 or title in ("查看更多", "展开"):
            continue

        due_m = re.search(r"(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}(?:\s*\d{1,2}:\d{2})?)", b)
        due = due_m.group(1) if due_m else ""
        if not due:
            due_m = re.search(r"(\d{1,2}[-/.]\d{1,2}(?:\s*\d{1,2}:\d{2})?)\s*(?:截止|结束)", b)
            due = due_m.group(1) if due_m else ""

        if re.search(r"已完成|已交|已提交|已批阅", b):
            status = "已完成"
        elif re.search(r"未交|待做|未完成|去完成", b):
            status = "未完成"
        else:
            status = "未完成"

        items.append({
            "course": course,
            "kind": kind,
            "title": title,
            "due": due.strip(),
            "status": status,
        })
    return items


def push(title, body):
    if SC_KEY:
        try:
            r = requests.post(f"https://sctapi.ftqq.com/{SC_KEY}.send",
                              data={"title": title[:32], "desp": body}, timeout=15)
            print("[push] serverchan", r.status_code)
        except Exception as e:
            print("[push] serverchan fail:", e)
    if TG_TOKEN and TG_CHAT:
        try:
            r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                              data={"chat_id": TG_CHAT, "text": body[:3900]}, timeout=15)
            print("[push] telegram", r.status_code)
        except Exception as e:
            print("[push] telegram fail:", e)


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def render(todo):
    if todo:
        li = "\n".join(
            f'<li><div class="hd"><b>{esc(x["course"])}</b>'
            f'<span class="k">{esc(x["kind"])}</span></div>'
            f'<div class="ti">{esc(x["title"])}</div>'
            f'<div class="d">⏰ {esc(x["due"]) if x["due"] else "未标注截止"}</div></li>'
            for x in todo)
    else:
        li = '<li class="ok">暂无待办 🎉</li>'

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#111111">
<title>学习通待办</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;padding:18px 14px 40px;background:#0f0f10;color:#ececec;
font:17px/1.55 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}}
h1{{font-size:20px;margin:0 0 2px}}
.sub{{color:#7b7b80;font-size:13px;margin-bottom:16px}}
ul{{list-style:none;padding:0;margin:0}}
li{{background:#1b1b1e;border-radius:14px;padding:14px 16px;margin:10px 0;
border-left:4px solid #c0392b}}
li.ok{{border-left-color:#2ecc71;text-align:center;color:#8fe3b0}}
.hd{{display:flex;align-items:center;gap:8px;font-size:14px;color:#a8a8ad;margin-bottom:4px}}
.k{{background:#c0392b;color:#fff;border-radius:6px;padding:1px 7px;font-size:12px}}
.ti{{font-size:17px;font-weight:600;word-break:break-all}}
.d{{color:#ff5fa2;font-size:14px;margin-top:6px}}
</style></head><body>
<h1>学习通待办 {len(todo)} 项</h1>
<div class="sub">{now} 更新</div>
<ul>
{li}
</ul>
</body></html>"""


def render_md(todo):
    """生成 todo.md —— Gitee 仓库页会直接渲染成网页，手机打开即看"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# 学习通待办",
        "",
        f"**{len(todo)} 项未完成** · {now} 自动更新",
        "",
    ]
    if todo:
        lines.append("| 截止 | 课程 | 类型 | 内容 |")
        lines.append("|---|---|---|---|")
        for x in todo:
            due = x["due"] or "—"
            title = x["title"].replace("|", "／")
            lines.append(f'| {due} | {x["course"]} | {x["kind"]} | {title} |')
    else:
        lines.append("暂无待办 🎉")
    lines += ["", "---", "<sub>由脚本自动生成，勿手改</sub>", ""]
    return "\n".join(lines)


def git_commit(paths, msg):
    """GIT_PUSH=1 时把结果提交回仓库；CI 里用"""
    if os.environ.get("GIT_PUSH") != "1":
        return
    # Gitee Go：用私人令牌带凭证推，避免权限报错
    tok = os.environ.get("GITEE_TOKEN")
    repo = os.environ.get("GITEE_REPO")   # 形如 someone/cx-todo
    if tok and repo:
        subprocess.run(["git", "remote", "set-url", "origin",
                        f"https://oauth2:{tok}@gitee.com/{repo}.git"],
                       capture_output=True, text=True)
    cmds = [
        ["git", "config", "user.email", "cx-todo@local"],
        ["git", "config", "user.name", "cx-todo-bot"],
        ["git", "add", *paths],
        ["git", "commit", "-m", msg],
        ["git", "push"],
    ]
    for c in cmds:
        r = subprocess.run(c, capture_output=True, text=True)
        print("[git]", " ".join(c[:2]), r.returncode,
              (r.stdout or "").strip()[-200:], (r.stderr or "").strip()[-200:])


def main():
    if not COOKIE:
        print("no CX_COOKIE")
        return

    cs = courses()
    print(f"[courses] {len(cs)} 门")
    if not cs:
        push("学习通待办：Cookie 失效",
             "课程列表拉取为空。去 i.chaoxing.com 重新复制 Cookie，更新 Secret：CX_COOKIE")
        return

    rows = []
    for c in cs:
        for kind, tpl in (("作业", WORK), ("考试", EXAM)):
            url = tpl.format(**c)
            try:
                r = requests.get(url, headers=H, timeout=25)
            except Exception as e:
                print("[skip]", c["name"], kind, e)
                continue
            if DEBUG:
                fn = f"dbg_{c['classId']}_{kind}.html"
                open(fn, "w", encoding="utf-8").write(r.text)
                print("[dbg]", fn, len(r.text))
            got = parse(r.text, c["name"], kind)
            print(f"[{kind}] {c['name']}: {len(got)}")
            rows += got

    # 去重（同一门课同一标题只留一条）
    seen, uniq = set(), []
    for x in rows:
        key = (x["course"], x["kind"], x["title"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(x)

    todo = [x for x in uniq if x["status"] == "未完成"]
    todo.sort(key=lambda x: x["due"] or "9999-99-99")

    open(f"{OUT}/index.html", "w", encoding="utf-8").write(render(todo))
    json.dump({"updated": datetime.datetime.now().isoformat(timespec="seconds"),
               "todo": todo, "all": uniq},
              open(f"{OUT}/todo.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # Gitee：清单写进仓库根的 todo.md，手机打开仓库页即见
    open("todo.md", "w", encoding="utf-8").write(render_md(todo))

    body = "\n".join(
        f'[{x["kind"]}] {x["course"]}：{x["title"]}（{x["due"] or "—"}）'
        for x in todo[:15])
    if len(todo) > 15:
        body += f"\n… 还有 {len(todo) - 15} 项"
    push(f"学习通待办 {len(todo)} 项", body or "今天没有待办，放心玩")
    git_commit(["todo.md"], f"更新待办 {datetime.date.today()}")
    print(f"[done] {len(todo)} todo")


if __name__ == "__main__":
    main()
