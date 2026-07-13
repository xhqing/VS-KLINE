"""订阅注册表：(code,k_type) → set[WebSocket]，引用计数复用唯一 futu 订阅。

多 WS 连接订阅同标时，futu 侧首个订阅才真 subscribe，最后退出才 unsubscribe。
handler 内不碰连接，路由全在 asyncio 侧（broadcaster）。

k_type == "K_DAY" 不走 subscribe（日级 request_history_kline 无需订阅）。
"""
import asyncio

from futu import SubType

# k_type 字符串 → SubType（M0 实测 KLType 与 SubType 同名）
_KTYPES = ["K_1M", "K_5M", "K_15M", "K_30M", "K_60M", "K_DAY"]
_KLSUBTYPE = {k: getattr(SubType, k) for k in _KTYPES}
_KLSUBTYPE["RT"] = SubType.RT_DATA  # 分时图（非 KLType，单独映射）
_KLSUBTYPE["RT5"] = SubType.K_1M  # 5 日分时叠加（复用 1 分钟 K 线订阅）


class SubscriptionRegistry:
    def __init__(self, ctx):
        self._ctx = ctx
        self._map: dict[tuple[str, str], set] = {}  # (code,k_type) -> set[WebSocket]
        self._lock = asyncio.Lock()

    async def add(self, conn, code: str, k_type: str) -> None:
        """注册连接；首个订阅才真 ctx.subscribe。"""
        key = (code, k_type)
        async with self._lock:
            first = key not in self._map or len(self._map[key]) == 0
            self._map.setdefault(key, set()).add(conn)
        if first and k_type != "K_DAY":
            ret, err = await asyncio.to_thread(
                self._ctx.subscribe, [code], [_KLSUBTYPE[k_type]], False
            )  # is_first_push=False（M2 自己拉 history，不靠首帧）
            if ret != 0:
                async with self._lock:
                    self._map.get(key, set()).discard(conn)
                raise RuntimeError(f"subscribe({code},{k_type}) failed: {err}")

    async def remove(self, conn, code: str, k_type: str) -> None:
        """注销连接；最后一个退出才真 ctx.unsubscribe。"""
        key = (code, k_type)
        async with self._lock:
            conns = self._map.get(key)
            if not conns:
                return
            conns.discard(conn)
            empty = len(conns) == 0
            if empty:
                self._map.pop(key, None)
        if empty and k_type != "K_DAY":
            try:
                await asyncio.to_thread(
                    self._ctx.unsubscribe, [code], [_KLSUBTYPE[k_type]]
                )
            except Exception as e:
                print(f"[registry] unsubscribe({code},{k_type}) err: {e}", flush=True)

    def subscribers(self, code: str, k_type: str):
        """broadcaster 查收件人（无锁，volatile 读可接受）。"""
        return list(self._map.get((code, k_type), ()))

    async def drop(self, conn) -> None:
        """WS 断开时清该连接所有订阅。"""
        keys = [k for k, s in self._map.items() if conn in s]
        for k in keys:
            await self.remove(conn, *k)
