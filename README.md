# xtraining-events

X Training App「赛事」页的数据源。每天自动抓取国内健美/健身赛事，生成 `public/events.json`，
由 Vercel 发布在 https://xtraining-events.vercel.app/events.json （App 直接读这个地址，换数据不用发新版）。

## 数据从哪来
- **国内赛事（自动）**：CBCIS 中国健美赛事信息系统 open.musclegame.cn 的公开接口 `/api/events`
  （网站在 llms.txt 里公开了这个接口，robots.txt 允许抓取）。每天 1 次，翻页间隔 1.5 秒，只取文字，不取海报图片。
- **手动维护**：`data/manual.json`，放全球职业赛，以及国内需要手写简介、开赛时间、前三名成绩的比赛。
  手动条目里的 `url` 如果是某场 musclegame 比赛的链接，就会顶替自动抓到的那一场（id 不变，用户追的赛不丢）。

## 怎么改
- 改某场比赛的简介/时间：把它复制到 `data/manual.json` 改，推送后会自动重新生成。
- 立刻更新一次：GitHub → Actions → 更新赛事 → Run workflow。
- 本地试：`python3 scripts/build.py`

## 定时任务
`.github/workflows/update.yml`：每天北京时间 6:17，在 Linux 机器上跑，约 1 分钟，有变化才提交。
抓到的少于 20 场会当作接口出问题，不覆盖旧数据。
