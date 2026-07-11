"""WS 测试客户端。用法: python3 scripts/ws_client.py [CODE] [K_TYPE]

连 /ws，发 subscribe，打印收到的 history/update 消息。
盘外：收 1 条 history 后 5s 无 update 超时退出（无实时推送）。
盘中：收 history 后持续收 update。
"""
import asyncio
import json
import sys

from websockets.asyncio.client import connect


async def main():
    code = sys.argv[1] if len(sys.argv) > 1 else "HK.02800"
    kt = sys.argv[2] if len(sys.argv) > 2 else "K_5M"
    async with connect("ws://127.0.0.1:8765/ws") as ws:
        print(f"connected, subscribing {code} {kt}")
        await ws.send(json.dumps({"action": "subscribe", "code": code, "k_type": kt}))
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                tail = "..." if len(raw) > 300 else ""
                print("<<<", raw[:300] + tail)
        except asyncio.TimeoutError:
            print("(5s 无更多消息，退出)")
        except Exception as e:  # noqa: BLE001
            print(f"(异常退出: {type(e).__name__}: {e})")


if __name__ == "__main__":
    asyncio.run(main())
