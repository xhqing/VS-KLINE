# legacy — 已弃用的部署件

本目录存放 vs-kline v0.1.0 时代的「launchd 常驻 + CLI」部署件。自 **v0.2.0** 起改为 VSCode 扩展形态，后端由扩展激活时 `spawn` 托管，这些件**已弃用**，仅作历史参考与独立后端调试备查。

## 内容

| 文件 | 原位置 | 作用 |
|---|---|---|
| `launchd/com.xhq.vs-kline.backend.plist` | `deploy/launchd/` | macOS launchd 配置模板（`RunAtLoad` + `KeepAlive` 开机自启） |
| `bin/vs-kline` | `bin/` | 服务管理 CLI（`start`/`stop`/`restart`/`update`/`status`），包装 `launchctl` |
| `scripts/install.sh` | `scripts/` | 安装脚本（生成 plist + symlink CLI 到 `~/.local/bin`） |

## 为何弃用

v0.2.0 改为 VSCode 扩展后：

- 后端由扩展激活时 `spawn`，无需 launchd 常驻
- `start`/`stop`/`restart`/`status` 由扩展命令（命令面板 `vs-kline:`）取代 CLI
- 安装即装 `.vsix`，无需 `install.sh`

## 仍可参考的场景

- 想脱离 VSCode、以后台常驻服务方式独立跑后端（用 launchd 托管 uvicorn）
- 调试后端：直接 `.venv/bin/python -m uvicorn backend.server:app --port 8765`，配合浏览器开 `frontend/`

> ⚠️ 这些脚本不再维护，路径与逻辑停留在 v0.1.0，按现状使用。
