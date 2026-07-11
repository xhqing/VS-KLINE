# vs-kline

在 VSCode 里看港股 / 美股实时 K 线的轻量看盘工具。

## 架构

```
富途 OpenD（实时 K 线推送）
      ↓
FastAPI 后端（WebSocket 转发）
      ↓
lightweight-charts 前端（series.update 增量刷新）
```

- 页面上下分屏，同时盯两个标的
- 通过 VSCode 内置 Simple Browser 打开 `localhost`
- launchd 托管，开机自启后台常驻，日常「打开 VSCode 就有图」

## 目录结构

```
vs-kline/
├── backend/           # FastAPI 服务 + 富途数据源
├── frontend/          # lightweight-charts 页面（上下分屏）
│   ├── js/
│   └── css/
└── deploy/launchd/    # macOS launchd plist（开机自启）
```

## 开发计划

1. 验证富途 OpenD 分钟 K 线实时推送回调字段
2. FastAPI + WebSocket 转发
3. lightweight-charts 上下分屏页面（两标的 + 周期切换）
4. launchd 常驻自启

## 数据源

- **富途 OpenD**（`futu-api`）— 港股 / 美股 K 线 + 实时推送（主力）
- **老虎 SDK**（`tigeropen`）— 备用 / 交叉验证

## 环境搭建

⚠️ **venv 必须用 `--system-site-packages`**：`pip install futu-api` 到 venv 会被 setup.py install 方式**装坏**（import 卡死，不报错；系统 python 的 futu 正常，pandas 都是 3.0.x 排除其嫌疑）。系统的 futu-api（用户 site）已验证可用，venv 继承它，只把 fastapi/uvicorn/websockets 装进 venv：

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install fastapi 'uvicorn[standard]' websockets
```

启动（`--system-site-packages` venv 下 `bin/uvicorn` 脚本不生成，用 `python -m uvicorn`）：

```bash
.venv/bin/python -m uvicorn backend.server:app --app-dir . --host 127.0.0.1 --port 8765 --workers 1
```

- Python 3.11（系统 homebrew；futu-api + pandas 3.0.x 在用户 site）
- 富途 OpenD 本地网关运行中（`127.0.0.1:11111`，`qot_logined=True`）
