<p align="center">
  <img src="media/icon.png" width="140" alt="vs-kline logo">
</p>

<h1 align="center">VS-KLINE</h1>

<p align="center">Lightweight HK/US stock real-time K-line charting inside VSCode, powered by Futu OpenD.</p>

<p align="center">
  <img src="https://img.shields.io/badge/VSCode-1.85%2B-007ACC?logo=visualstudiocode&logoColor=white" alt="VSCode">
  <img src="https://img.shields.io/badge/platform-macOS-lightgrey?logo=apple" alt="platform">
  <img src="https://img.shields.io/badge/version-0.2.0-green" alt="version">
  <img src="https://img.shields.io/badge/data-Futu%20OpenD-orange" alt="data source">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="license">
</p>

---

[English](README.md) | [中文](README_cn.md)

## Features

- **Two stacked panels** — watch two symbols side by side (e.g. an HK ETF and a US stock)
- **Real-time K-line + intraday** — candlestick with volume, or intraday price/average/volume with a previous-close reference line
- **Multiple periods** — 1m / 5m / 15m / 30m / 60m / day; switchable per panel
- **Live updates** — incremental bar refresh over WebSocket, no manual reload
- **Runs inside VSCode** — a webview panel; no external browser or background daemon to install

## Requirements

- **VSCode 1.85+**
- **Futu OpenD** running locally (`127.0.0.1:11111`) with the quote session logged in (`qot_logined=true`)
- **Python 3.11** that can `import futu, fastapi, uvicorn`
  - On macOS, create the venv with `--system-site-packages`, because `pip install futu-api` into a plain venv breaks (it uses legacy `setup.py install`). The system Python's `futu-api` works; the venv inherits it:

    ```bash
    python3 -m venv --system-site-packages .venv
    .venv/bin/python -m pip install fastapi 'uvicorn[standard]' websockets
    ```

## Install

### From source (development)

1. Clone and install JS deps:

    ```bash
    git clone https://github.com/xhqing/VS-KLINE.git
    cd VS-KLINE
    npm install
    ```

2. Build: `npm run compile`
3. Press `F5` to launch an Extension Development Host, then run **vs-kline: Open** from the command palette.

### Package a .vsix

```bash
npm run package    # produces vs-kline-<version>.vsix
code --install-extension vs-kline-<version>.vsix
```

### From Marketplace

(Search `vs-kline` once published.)

## Configuration

Open Settings and filter by `vs-kline`:

| Setting | Default | Description |
|---|---|---|
| `vs-kline.pythonPath` | `""` | Python interpreter that can `import futu`. Empty = auto-detect (prefers `.venv/bin/python`). |
| `vs-kline.host` | `127.0.0.1` | Host the backend binds to. |
| `vs-kline.port` | `0` | Backend port. `0` = dynamic (recommended). |
| `vs-kline.defaultSymbols` | `{c1:HK.02800, k1:K_5M, c2:US.AAPL, k2:K_15M}` | Default symbols for the two panels. `k: RT` → intraday. |
| `vs-kline.opendHost` | `127.0.0.1` | Futu OpenD host. |
| `vs-kline.opendPort` | `11111` | Futu OpenD port. |
| `vs-kline.retainContextWhenHidden` | `true` | Keep the webview (and its WS) alive when the panel is hidden. |
| `vs-kline.stopOnClose` | `true` | Stop the backend when the chart panel is closed. |
| `vs-kline.autoRestart` | `false` | Auto-restart the backend on crash. |

## Commands

Run from the command palette (`Cmd/Ctrl+Shift+P`):

- **vs-kline: Open** — start the backend (if needed) and open the chart panel
- **vs-kline: Start Backend** / **Stop Backend** / **Restart Backend**
- **vs-kline: Backend Status** — print state/port/pid to the `vs-kline` output channel

## Architecture

```
VSCode extension (TypeScript)
  activate → registers commands (lazy, on vs-kline.open)
  vs-kline.open
    → BackendManager.start()
        pythonFinder resolves .venv/bin/python (verifies import futu)
        spawn: python -m uvicorn backend.server:app --port 0 --workers 1
        parse "Uvicorn running on http://127.0.0.1:NNNN" → actual port
        poll GET /health until opend ready
    → WebviewPanel loads webview/index.html
        CSP connect-src: ws://127.0.0.1:NNNN http://127.0.0.1:NNNN (exact port)
        injects window.__VSKLINE_WS__ / __VSKLINE_DEFAULTS__
        lightweight-charts loaded via asWebviewUri + nonce
  deactivate / close panel → BackendManager.stop(): SIGTERM → SIGKILL

Python backend (backend/, data layer unchanged)
  server.py: OpenD host/port read from env vars
  futu_source.py / registry.py: Futu source, timezone, subscription refcount
```

The data layer (Futu source, timezone conversion, subscription refcounting, the `history`/`update`/`error` WS protocol) is unchanged from v0.1.0 — the extension only swaps the host (browser → webview) and the lifecycle owner (launchd → extension subprocess).

## Data Source

- **Futu OpenD** (`futu-api`, Python) — HK/US K-line + real-time push
- Supported codes: `HK.*` (Hong Kong, `Asia/Shanghai`), `US.*` (US, `America/New_York`)

## Known Limitations

- **macOS first** — the `--system-site-packages` venv trick is macOS-specific; Windows/Linux are untested.
- **OpenD required** — if OpenD isn't running or isn't logged in, the backend reports `opend=false` and charts won't load.
- **The .vsix does not bundle Python deps** — you provide the Python environment (see Requirements).
- **Dynamic port** — the backend picks a free port on each start; `scripts/ws_client.py` takes the port as an arg for debugging.

## Troubleshooting

- **"未找到可 import futu 的 Python"** — create a `--system-site-packages` venv (see Requirements) or set `vs-kline.pythonPath`.
- **Charts empty / "OpenD 未登录"** — start Futu OpenD and confirm the login; check the `vs-kline` output channel.
- **Port in use** — set `vs-kline.port` to `0` (dynamic).
- **Logs** — run **vs-kline: Backend Status**, or open the `vs-kline` output channel.

## Attribution

If you use, fork, or redistribute this project, please credit the original author (**Huaqing Xu / xhqing**) and link back to the project: <https://github.com/xhqing/VS-KLINE>.

## License

[MIT](LICENSE)
