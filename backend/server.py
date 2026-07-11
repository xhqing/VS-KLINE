"""vs-kline FastAPI 服务。

M1: lifespan + GET /history（HTTP 历史）+ StaticFiles。
M2: WebSocket /ws 实时转发（KlineBridge[futu线程] → Queue → broadcaster[asyncio] → registry 路由）。

uvicorn 必须 --workers 1（OpenQuoteContext 进程内单例，多 worker 割裂订阅）。
"""
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from futu import OpenQuoteContext

from backend.futu_source import KlineBridge, fetch_history
from backend.registry import SubscriptionRegistry

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


async def broadcaster(queue: asyncio.Queue, registry: SubscriptionRegistry):
    """asyncio 侧：从队列取推送，按 (code,k_type) 路由到订阅的 WS 连接。"""
    while True:
        item = await queue.get()
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
    ctx = OpenQuoteContext("127.0.0.1", 11111)
    ctx.set_handler(KlineBridge(loop, queue))  # futu 接收线程 → queue
    ret, gs = ctx.get_global_state()
    app.state.ctx = ctx
    app.state.opend_ok = ret == 0 and gs.get("qot_logined")
    app.state.registry = SubscriptionRegistry(ctx)
    app.state.subscribed = set()  # M1 /history HTTP 用（简版）；WS 走 registry
    print(f"[vs-kline] OpenD connected, qot_logined={app.state.opend_ok}", flush=True)
    task = asyncio.create_task(broadcaster(queue, app.state.registry))
    try:
        yield
    finally:
        task.cancel()
        try:
            ctx.unsubscribe_all()
        except Exception:
            pass
        ctx.close()


app = FastAPI(title="vs-kline", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "opend": getattr(app.state, "opend_ok", False)}


@app.get("/history")
def history(
    code: str = Query(...),
    k_type: str = Query("K_5M"),
    num: int = Query(300, ge=1, le=1000),
):
    if not getattr(app.state, "opend_ok", False):
        raise HTTPException(503, "OpenD not logined")
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


# 前端静态（M3 用；显式路由优先于 mount）
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
