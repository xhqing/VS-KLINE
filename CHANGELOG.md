# 变更记录

本项目变更记录遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-07-11

首个可用版本。在 VSCode Simple Browser 里看港股 / 美股实时 K 线 + 分时走势的轻量看盘工具，
富途 OpenD 数据源，launchd 常驻 + `vs-kline` CLI 管理。

### Added

- **K 线**：富途 OpenD 历史 K 线（`request_history_kline` 日级 + `get_cur_kline` 分钟级）+ 实时推送（`CurKlineHandlerBase`）。支持港股 / 美股，周期 1m / 3m / 5m / 15m / 30m / 60m / 日（+ 周 / 月 / 季 / 年可扩展）
- **分时图**：`get_rt_data` 当日分时走势——价格线 + 均价线 + 成交量柱 + 昨收参考虚线（周期下拉选「分时」）
- **双图上下分屏**：两个面板各盯一个标的，URL 参数 `?c1=HK.02800&k1=K_5M&c2=US.AAPL&k2=K_15M` 初始化；每面板独立周期切换（下拉 onchange 自动换图）
- **中文名称**：面板标题显示「代码 中文名 · 周期」（如「HK.02800 盈富基金 · K_5M」）
- **WebSocket 实时转发**：futu 接收线程 `on_recv_rsp` → `call_soon_threadsafe` 投 `asyncio.Queue` → broadcaster 按 `(code, k_type)` 路由 → 前端 `series.update` 增量刷新；订阅引用计数复用唯一一条 futu 订阅
- **时区换算**：富途 `time_key`（市场本地 naive）→ UTC 秒，港股 `Asia/Shanghai`、美股 `America/New_York`（`zoneinfo` 自动处理夏令时），历史与实时共用同一函数保证在途 K 线 time 对齐
- **launchd 常驻**：`com.xhq.vs-kline.backend` 开机自启（`RunAtLoad`）+ 异常退出自动重启（`KeepAlive`），日志输出到 `~/Library/Logs/vs-kline/`
- **`vs-kline` CLI**：`start` / `stop` / `restart` / `status` / `--version`，包装 `launchctl` + health 探测
- **前端**：lightweight-charts v5 本地 vendor（离线、避 CSP / 外网依赖）、断线指数退避重连、顶栏连接状态点
- **幂等订阅**：分钟级 `get_cur_kline` 与分时 `get_rt_data` 均需先 subscribe（实测），后端自动幂等处理

### 已知限制

- **实时推送待盘中验证**：K 线实时 `update`（`KlineBridge` → broadcaster 路由）代码就绪，但盘外无推送，未运行时验证（`on_recv_rsp` 的 `row.k_type` 字符串格式、持续 fire 留盘中确认）
- **分时实时未接推送**：分时当前靠 `get_rt_data` 拉全天历史，盘中需刷新页面更新；实时分时推送（`RTDataHandlerBridge`）未实现（前端 `update` 分支已预留）
- **CLI 全局命令**：`/usr/local/bin/vs-kline` symlink 需 `sudo` 手动建立（见 README），未装时用 `bin/vs-kline` 全路径

### 环境要求

- Python 3.11（venv 用 `--system-site-packages` 继承系统的 futu-api / pandas，详见 README——`pip install futu-api` 到 venv 会被 setup.py install 装坏）
- 富途 OpenD 本地网关运行中（`127.0.0.1:11111`，`qot_logined=True`）
