"""vs-kline FastAPI 服务。

M1: lifespan + GET /history（HTTP 历史）+ StaticFiles。
M2: WebSocket /ws 实时转发（KlineBridge[futu线程] → Queue → broadcaster[asyncio] → registry 路由）。

uvicorn 必须 --workers 1（OpenQuoteContext 进程内单例，多 worker 割裂订阅）。
"""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from futu import OpenQuoteContext

from backend.futu_source import KlineBridge, fetch_history, fetch_rt5
from backend.registry import SubscriptionRegistry

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# OpenD 网关地址（扩展通过环境变量传入；独立运行时用默认值）
OPEND_HOST = os.getenv("VSKLINE_OPEND_HOST", "127.0.0.1")
OPEND_PORT = int(os.getenv("VSKLINE_OPEND_PORT", "11111"))


async def broadcaster(queue: asyncio.Queue, app: FastAPI):
    """asyncio 侧：从队列取推送，按 (code,k_type) 路由到订阅的 WS 连接。

    动态读取 app.state.registry（OpenD 连接完成后才创建）。
    """
    while True:
        item = await queue.get()
        registry = getattr(app.state, "registry", None)
        if not registry:
            continue
        conns = registry.subscribers(item["code"], item["k_type"])
        if not conns:
            continue
        msg = json.dumps(
            {
                "type": "update",
                "code": item["code"],
                "k_type": item["k_type"],
                "bar": item["bar"],
            }
        )
        await asyncio.gather(
            *[c.send_text(msg) for c in conns], return_exceptions=True
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue(maxsize=10000)

    # OpenD 连接状态：connecting → connected | failed
    app.state.opend_state = "connecting"
    app.state.opend_message = ""
    app.state.ctx = None
    app.state.opend_ok = False
    app.state.registry = None
    app.state.subscribed = set()

    async def connect_opend():
        """后台连接 OpenD，不阻塞 Uvicorn 启动。

        OpenQuoteContext 构造函数内部同步连接并重试，
        用 asyncio.to_thread 移出事件循环，避免阻塞 lifespan。
        futu-api 无限重试，加 60s 超时防永久卡住。
        """
        try:
            ctx = await asyncio.wait_for(
                asyncio.to_thread(OpenQuoteContext, OPEND_HOST, OPEND_PORT),
                timeout=60.0,
            )
            ctx.set_handler(KlineBridge(loop, queue))
            ret, gs = await asyncio.to_thread(ctx.get_global_state)
            if ret == 0 and gs.get("qot_logined"):
                app.state.ctx = ctx
                app.state.opend_ok = True
                app.state.opend_state = "connected"
                app.state.registry = SubscriptionRegistry(ctx)
                print("[vs-kline] OpenD connected, qot_logined=True", flush=True)
            else:
                app.state.opend_state = "failed"
                app.state.opend_message = (
                    f"OpenD 已连接但行情未登录 (qot_logined={gs.get('qot_logined')})"
                )
                print(f"[vs-kline] OpenD connected but qot_logined=False", flush=True)
        except asyncio.TimeoutError:
            app.state.opend_state = "failed"
            app.state.opend_message = (
                f"OpenD 连接超时（{OPEND_HOST}:{OPEND_PORT}）："
                f"请确认富途 OpenD 已启动并登录行情"
            )
            print(f"[vs-kline] OpenD connection timed out (60s)", flush=True)
        except Exception as e:
            app.state.opend_state = "failed"
            app.state.opend_message = f"OpenD 连接失败 ({OPEND_HOST}:{OPEND_PORT}): {e}"
            print(f"[vs-kline] OpenD connection failed: {e}", flush=True)

    task_connect = asyncio.create_task(connect_opend())
    task_broadcaster = asyncio.create_task(broadcaster(queue, app))
    try:
        yield
    finally:
        task_connect.cancel()
        task_broadcaster.cancel()
        ctx = getattr(app.state, "ctx", None)
        if ctx:
            try:
                await asyncio.to_thread(ctx.unsubscribe_all)
            except Exception:
                pass
            ctx.close()


app = FastAPI(title="vs-kline", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "opend": getattr(app.state, "opend_ok", False),
        "opend_state": getattr(app.state, "opend_state", "connecting"),
        "opend_message": getattr(app.state, "opend_message", ""),
    }


@app.get("/history")
def history(
    code: str = Query(...),
    k_type: str = Query("K_5M"),
    num: int = Query(300, ge=1, le=1000),
):
    ctx = app.state.ctx
    if ctx is None:
        state = getattr(app.state, "opend_state", "connecting")
        msg = getattr(app.state, "opend_message", "")
        if state == "connecting":
            raise HTTPException(503, "OpenD 正在连接中，请稍后重试")
        raise HTTPException(503, msg or "OpenD 不可用")
    try:
        bars, name, last_close = fetch_history(app.state.ctx, code, k_type, num, app.state.subscribed)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))
    return JSONResponse(
        {"code": code, "name": name, "k_type": k_type, "last_close": last_close, "count": len(bars), "bars": bars}
    )


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    ctx = app.state.ctx
    registry = app.state.registry
    if ctx is None:
        state = getattr(app.state, "opend_state", "connecting")
        msg = getattr(app.state, "opend_message", "")
        await websocket.send_text(
            json.dumps({"type": "error", "msg": msg or f"OpenD {state}"})
        )
        await websocket.close()
        return
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"type": "error", "msg": "invalid json"})
                )
                continue
            action = msg.get("action")
            code = msg.get("code")
            k_type = msg.get("k_type", "K_5M")
            if not code:
                await websocket.send_text(
                    json.dumps({"type": "error", "msg": "missing code"})
                )
                continue
            if action == "subscribe":
                try:
                    await registry.add(websocket, code, k_type)  # 首次订阅才真 subscribe
                    if k_type == "RT5":
                        series, name, last_close = fetch_rt5(ctx, code)  # 5 日分时叠加
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "history",
                                    "code": code,
                                    "name": name,
                                    "k_type": "RT5",
                                    "last_close": last_close,
                                    "series": series,
                                }
                            )
                        )
                    else:
                        bars, name, last_close = fetch_history(ctx, code, k_type, num=300)  # registry 已订阅
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "history",
                                    "code": code,
                                    "name": name,
                                    "k_type": k_type,
                                    "last_close": last_close,
                                    "bars": bars,
                                }
                            )
                        )
                except Exception as e:
                    await websocket.send_text(
                        json.dumps({"type": "error", "msg": str(e)})
                    )
            elif action == "unsubscribe":
                await registry.remove(websocket, code, k_type)
    except WebSocketDisconnect:
        pass
    finally:
        await registry.drop(websocket)


# 前端静态：独立调试用（项目根有 frontend/ 时挂载；扩展形态 extDir 无 frontend 则跳过）
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
