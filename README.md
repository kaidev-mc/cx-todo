# 学习通待办聚合

每天定时抓一次「所有课程的作业 + 考试」，推到微信，并在仓库里生成一张 `todo.md` 清单。
手机打开仓库链接或微信消息就能看，不用开电脑，不用一个通知一个通知点。

支持两个平台，二选一即可：

| 平台 | 定时执行 | 手机看清单 | 备注 |
|---|---|---|---|
| Gitee | Gitee Go | 仓库页渲染 `todo.md` | 国内访问快，Pages 已下线改用 md |
| GitHub | GitHub Actions | gh-pages 网页 | 需要能访问 GitHub |

---

## 一、通用准备（两个平台都要）

### 1. 拿 Cookie
1. 浏览器打开 `https://i.chaoxing.com` 登录
2. F12 → **Network / 网络** → 刷新 → 点任意请求
3. **Request Headers** 里找 `Cookie:`，整行复制（很长，全要）

### 2. 拿微信推送 Key
`https://sct.ftqq.com` → 微信扫码 → 复制 **SendKey**（`SCT` 开头）。
只想看网页、不要推送：这步跳过，`SC_KEY` 不填即可。

---

## 二、Gitee 部署（推荐国内用）

### 1. 建仓库并推送
在 `https://gitee.com` 新建仓库（私有），然后本地执行：

```powershell
cd <本文件夹>
git remote add origin https://gitee.com/你的用户名/cx-todo.git
git push -u origin main
```

推送要密码时，填 Gitee 的 **私人令牌**（设置 → 私人令牌 → 生成，勾 `projects`）。

### 2. 开通 Gitee Go
仓库页 → 顶部 **Gitee Go** → 开通。免费额度：每仓库 200 分钟 + 每月 1000 分钟，
每天跑一分钟，一个月 30 分钟，够用很久。

### 3. 配流水线变量
Gitee Go 页面 → **变量管理**（或仓库 Settings → 流水线变量）添加：

| 变量名 | 值 | 说明 |
|---|---|---|
| `CX_COOKIE` | 第一步复制的 Cookie | 必填 |
| `SC_KEY` | SendKey | 可选，微信推送 |
| `GITEE_TOKEN` | 你的私人令牌 | 必填，用于回写 `todo.md` |
| `GITEE_REPO` | `用户名/cx-todo` | 必填 |
| `GIT_PUSH` | `1` | 已在 `.workflow/todo.yml` 里设好 |

> 变量记得勾选「加密」，避免 Cookie 明文可见。

### 4. 跑一次
Gitee Go → 流水线 **学习通待办** → **运行**。
成功后仓库根目录会多出 `todo.md`，手机打开
`https://gitee.com/你的用户名/cx-todo/blob/main/todo.md` 就是清单。
把这个链接加到手机浏览器书签或桌面快捷方式即可。

### 5. 定时
`.workflow/todo.yml` 里已写好北京时间 07:30：

```yaml
schedule:
  - cron: "0 30 7 * * ?"   # 秒 分 时 日 月 周（Quartz 六位）
```

改时间就改这行。**注意** Gitee Go 的 cron 是 6 位带秒，跟 GitHub 的 5 位不一样。

> 如果流水线报 YAML 字段不认识（Gitee Go 各版本 step 名有差异），
> 就用网页上的**可视化编排**：新建「执行 Shell 脚本」步骤，内容填
> `python3 -m pip install requests && python3 todo_chaoxing.py`，
> 触发器里加「定时触发」填同样的 cron，效果一样。

---

## 三、GitHub 部署

1. 建私有仓库，推送 `main` 分支
2. Settings → Secrets 加 `CX_COOKIE`、`SC_KEY`
3. Settings → Pages → Source 选 `gh-pages` 分支
4. Actions → **学习通待办** → Run workflow

跑通后网页地址 `https://用户名.github.io/cx-todo/`，手机「添加到主屏幕」当 App。
时间在 `.github/workflows/todo.yml` 的 `cron: '0 23 * * *'`（UTC，北京 07:00）。

---

## 四、日常

- 每天自动跑，什么都不用管
- Cookie 大概撑几周，过期会推一条「Cookie 失效」，回去换个 `CX_COOKIE` 就行
- 想手动看一次：Gitee Go 点「运行」/ GitHub 点 Run workflow

## 五、本地调试

```powershell
pip install requests
$env:CX_COOKIE="粘cookie"
python todo_chaoxing.py --debug
```

会生成 `todo.md`（成品）、`out\index.html`（网页版）、`dbg_*.html`（原始页面）。
清单为空或抓错条目时，把 `dbg_作业.html` 发出来，按你学校那套页面结构调 `parse()` 里的正则。
