# BTC 每15分钟自动监控（Coinbase BTC-USD）

本项目包括：GitHub Actions 后台采集、GitHub Pages 网页、持久化 `data.json`、历史曲线、相隔约15分钟涨跌幅统计、CSV 导出。

## 数据定义

- 数据源：`https://api.exchange.coinbase.com/products/BTC-USD/ticker`，`price` 是 Coinbase Exchange 的 **最新一笔成交价**（美元），并非全球交易所均价，也不代表买入成交价。
- 采集时间 `time` 为后台程序实际获取价格的 UTC 时间；`trade_time` 是 Coinbase 返回的最近一笔成交时间。
- 每小时 UTC 02、17、32、47 分计划运行（每15分钟），GitHub Actions 可能排队延迟或漏运行。
- 与前一条记录的间隔在 **10–20分钟** 才计算“15分钟涨跌”；其他情况展示空白，避免误导。
- 7天、30天、24小时趋势；24小时变化要求24小时前15分钟范围内有记录。
- 未运行时没有数据；不会自动补记此前所有时间点。

## 部署步骤（无需自己的服务器）

1. 登录 GitHub，新建 **Public** repository（例如 `bitcoin-15m-tracker`）。
2. 将本 ZIP **解压**，把包含 `.github/workflows/btc-15min.yml` 的全部文件和文件夹上传到新仓库根目录（注意隐藏的 `.github` 文件夹也要上传）。
3. 仓库 **Settings → Actions → General → Workflow permissions**，选择 **Read and write permissions** 并保存；组织策略可能另有限制。
4. 仓库 **Settings → Pages → Build and deployment → Source**，选择 **GitHub Actions**。
5. 进入 **Actions → BTC 15-minute monitor → Run workflow**，第一次手动运行。成功后，Actions 的部署步骤会给出 Pages URL，网页显示第一条实际采集记录。
6. 之后 GitHub Actions 按计划自动运行，关闭网页仍然保存新记录；访问 Pages URL 可查看统计及导出 CSV。

如果仓库 Pages 首次部署提示 `Resource not accessible by integration`，先检查 Pages 是否启用、Settings → Actions 的运行权限及是否允许 Actions 发布 Pages。若 `git push` 报权限拒绝，检查 Workflow permissions 是否为读写。

## 限制与安全

- GitHub **定时任务不保证秒级准时**，可能延迟、漏跑，且 public repository **连续60天无活动**时定时任务可能被自动停用（根据 GitHub 的定义，定时 workflow 自己的提交是否足以保持活跃不应作为保证）。因此不能保证真正零中断运行。对不允许漏采样的需求，应换成全天在线的 VPS/专业调度服务。
- 默认只保留最多 35,040 条采样（约365天）。数据是公开仓库数据，不能用于存储秘密。
- `data.json` 会作为提交持续增长 Git 历史，长时间运行后可归档/清理。
- 采样只供观察，不构成投资建议；采样上涨频率不能直接当作未来涨幅概率。

本地单纯双击 `index.html` 可能因为浏览器 `file://` 安全策略无法读取 `data.json`。可运行 `python -m http.server 8000` 再打开 `http://localhost:8000`，或按上述步骤部署到 GitHub Pages。
