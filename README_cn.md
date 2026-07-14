<p align="center">
  <img src="media/icon.png" width="140" alt="vs-kline logo">
</p>

<h1 align="center">VS-KLINE</h1>

<p align="center">在 VSCode 里看港股 / 美股实时 K 线的轻量看盘工具，富途 OpenD 数据源。</p>

<p align="center">
  <img src="https://img.shields.io/badge/VSCode-1.85%2B-007ACC?logo=visualstudiocode&logoColor=white" alt="VSCode">
  <img src="https://img.shields.io/badge/platform-macOS-lightgrey?logo=apple" alt="platform">
  <img src="https://img.shields.io/badge/version-0.2.1-green" alt="version">
  <img src="https://img.shields.io/badge/data-Futu%20OpenD-orange" alt="data source">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="license">
</p>

---

[English](README.md) | [中文](README_cn.md)

> 本中文版译自 [README.md](README.md)，内容以英文版为准。

## 功能特性

- **上下双面板**：同时盯两个标的（如一只港股 ETF + 一只美股）
- **实时 K 线 + 分时**：K 线（含成交量），或分时（价格线 / 均价线 / 成交量 + 昨收参考虚线）
- **多周期**：1 分 / 5 分 / 15 分 / 30 分 / 60 分 / 日，每面板独立切换
- **实时刷新**：WebSocket 增量推送，烛体原地刷新，无需手动重载
- **VSCode 内嵌**：一个 webview 面板，无需外部浏览器或后台守护进程

## 环境要求

- **VSCode 1.85+**
- **富途 OpenD** 本地运行（`127.0.0.1:11111`），行情已登录（`qot_logined=true`）
- **Python 3.11**，可 `import futu, fastapi, uvicorn`
  - macOS：venv 必须用 `--system-site-packages`——`pip install futu-api` 进普通 venv 会装坏（旧式 setup.py install）。系统 Python 的 futu-api 可用，venv 继承它：

    ```bash
    python3 -m venv --system-site-packages .venv
    .venv/bin/python -m pip install fastapi 'uvicorn[standard]' websockets
    ```

## 安装

### 从 GitHub Release 安装（推荐）

从 [Releases](https://github.com/xhqing/VS-KLINE/releases) 下载最新的 `.vsix`，然后：

```bash
code --install-extension vs-kline-0.2.1.vsix
```

或直接用 URL 安装：

```bash
code --install-extension https://github.com/xhqing/VS-KLINE/releases/download/v0.2.1/vs-kline-0.2.1.vsix
```

### 从源码开发

1. 克隆并装 JS 依赖：

    ```bash
    git clone https://github.com/xhqing/VS-KLINE.git
    cd VS-KLINE
    npm install
    ```

2. 构建：`npm run compile`
3. 按 `F5` 启动扩展开发宿主，命令面板运行 **vs-kline: Open**

### 打包 .vsix

```bash
npm run package    # 生成 vs-kline-<版本>.vsix
code --install-extension vs-kline-<版本>.vsix
```

### 从 Marketplace

（发布后在应用市场搜索 `vs-kline`）

## 配置

打开设置，过滤 `vs-kline`：

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `vs-kline.pythonPath` | `""` | 可 `import futu` 的 Python 解释器。空 = 自动探测（优先 `.venv/bin/python`） |
| `vs-kline.host` | `127.0.0.1` | 后端绑定地址 |
| `vs-kline.port` | `0` | 后端端口。`0` = 动态（推荐） |
| `vs-kline.defaultSymbols` | `{c1:HK.02800, k1:K_5M, c2:US.AAPL, k2:K_15M}` | 双面板默认标的。`k: RT` → 分时 |
| `vs-kline.opendHost` | `127.0.0.1` | 富途 OpenD 地址 |
| `vs-kline.opendPort` | `11111` | 富途 OpenD 端口 |
| `vs-kline.retainContextWhenHidden` | `true` | 隐藏面板时保留 webview（与 WS 连接） |
| `vs-kline.stopOnClose` | `true` | 关闭看盘面板时停止后端 |
| `vs-kline.autoRestart` | `false` | 后端崩溃时自动重启 |

## 命令

命令面板（`Cmd/Ctrl+Shift+P`）：

- **vs-kline: Open** —— 按需拉起后端并打开看盘面板
- **vs-kline: Start Backend** / **Stop Backend** / **Restart Backend**
- **vs-kline: Backend Status** —— 输出状态 / 端口 / pid 到 `vs-kline` 输出面板

## 架构

```
VSCode 扩展（TypeScript）
  activate → 注册命令（懒激活，on vs-kline.open）
  vs-kline.open
    → BackendManager.start()
        pythonFinder 解析 .venv/bin/python（校验 import futu）
        spawn: python -m uvicorn backend.server:app --port 0 --workers 1
        解析 "Uvicorn running on http://127.0.0.1:NNNN" 拿实际端口
        轮询 GET /health 直到 opend 就绪
    → WebviewPanel 加载 webview/index.html
        CSP connect-src 精确放 ws://127.0.0.1:NNNN http://127.0.0.1:NNNN
        注入 window.__VSKLINE_WS__ / __VSKLINE_DEFAULTS__
        lightweight-charts 经 asWebviewUri + nonce 加载
  deactivate / 关面板 → BackendManager.stop(): SIGTERM → SIGKILL

Python 后端（backend/，数据层不变）
  server.py: OpenD 地址从环境变量读
  futu_source.py / registry.py: 富途数据源 / 时区换算 / 订阅引用计数
```

数据层（富途数据源、时区换算、订阅引用计数、`history`/`update`/`error` 的 WS 协议）与 v0.1.0 完全一致——扩展只换了宿主（浏览器 → webview）与生命周期管理者（launchd → 扩展子进程）。

## 数据源

- **富途 OpenD**（`futu-api`，Python）—— 港股 / 美股 K 线 + 实时推送
- 支持代码：`HK.*`（港股，`Asia/Shanghai`）、`US.*`（美股，`America/New_York`）

## 已知限制

- **macOS 优先**：`--system-site-packages` venv 是 macOS 特性，Windows / Linux 未测
- **依赖 OpenD**：OpenD 未运行或未登录时，后端报 `opend=false`，图表无数据
- **.vsix 不含 Python 依赖**：Python 环境由用户自备（见「环境要求」）
- **动态端口**：后端每次启动自选空闲端口；`scripts/ws_client.py` 用端口参数调试

## 排查

- **「未找到可 import futu 的 Python」**：建 `--system-site-packages` venv（见「环境要求」）或配置 `vs-kline.pythonPath`
- **图表空 / 「OpenD 未登录」**：启动富途 OpenD 并确认登录，查 `vs-kline` 输出面板
- **端口被占用**：把 `vs-kline.port` 设为 `0`（动态）
- **日志**：`vs-kline: Backend Status` 或打开 `vs-kline` 输出面板

## 署名

若你使用、二次开发或再分发本项目，请署名原作者（**Huaqing Xu / xhqing**）并引用项目地址：<https://github.com/xhqing/VS-KLINE>。

## 许可证

[MIT](LICENSE)
