"""富途 OpenD 数据源。

历史 K 线 + 时区换算 + 幂等订阅 + 实时推送桥接。

字段依据 M0/M1 实测（见 FUTU_KLINE_PUSH.md）：
  - get_cur_kline(code, num, ktype) → (ret, df)，df 12 列【无 k_type】
  - ⚠️ 分钟级 get_cur_kline 必须先 subscribe；K_DAY 走 request_history_kline 无需订阅
  - 实时推送 CurKlineHandlerBase.on_recv_rsp → (ret, df) 二元组，df 13 列含 k_type；跑在 futu 独立子线程
  - time_key 市场本地 naive：HK=Asia/Shanghai、US=America/New_York
  - KLType 与 SubType 同名（M0 实测）
"""
import datetime as _dt
from datetime import datetime
from zoneinfo import ZoneInfo

from futu import CurKlineHandlerBase, KLType, RET_OK, SubType

# code 前缀 → 市场时区（M0 实测确认）
TZ_BY_MARKET = {
    "HK.": ZoneInfo("Asia/Shanghai"),
    "US.": ZoneInfo("America/New_York"),
}
UTC = ZoneInfo("UTC")

# 前端可用的周期。KLType 与 SubType 同名（M0 实测），共用一份 key。
_KTYPES = ["K_1M", "K_5M", "K_15M", "K_30M", "K_60M", "K_DAY"]
_KLTYPE = {k: getattr(KLType, k) for k in _KTYPES}
_KLSUBTYPE = {k: getattr(SubType, k) for k in _KTYPES}
SUPPORTED_KTYPES = list(_KTYPES)


def time_key_to_epoch(code: str, time_key: str) -> int:
    """futu time_key（市场本地 naive 字符串）→ UTC 秒。lightweight-charts 要求 UTC 秒。"""
    tz = next((v for k, v in TZ_BY_MARKET.items() if code.startswith(k)), UTC)
    dt = datetime.strptime(time_key, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
    return int(dt.timestamp())


def ensure_subscribed(ctx, subscribed: set, code: str, k_type: str) -> None:
    """幂等订阅（M1 简版：只增不减；WS 场景用 registry 替换）。

    分钟级 get_cur_kline 前必须 subscribe（M1 实测）。K_DAY 无需订阅，调用方不走这里。
    """
    key = (code, k_type)
    if key in subscribed:
        return
    ret, err = ctx.subscribe([code], [_KLSUBTYPE[k_type]], is_first_push=False)
    if ret != RET_OK:
        raise RuntimeError(f"subscribe({code},{k_type}) failed: {err}")
    subscribed.add(key)


def fetch_history(ctx, code: str, k_type: str, num: int = 300, subscribed: set = None):
    """拉历史 K 线 / 分时 → (bars, name, last_close)。time 为 UTC 秒。

    k_type=="RT"：分时图，走 fetch_rt（subscribe RT_DATA + get_rt_data）；
    K_DAY：request_history_kline（无需订阅）；分钟级：get_cur_kline（需先 subscribe）。
    """
    if k_type == "RT":
        return fetch_rt(ctx, code, subscribed)

    kl = _KLTYPE.get(k_type)
    if kl is None:
        raise ValueError(f"unsupported k_type: {k_type}; supported: {SUPPORTED_KTYPES + ['RT']}")

    if k_type == "K_DAY":
        end = (_dt.datetime.now() + _dt.timedelta(days=1)).strftime("%Y-%m-%d")
        start = (_dt.datetime.now() - _dt.timedelta(days=num * 2 + 5)).strftime("%Y-%m-%d")
        ret, df, _page = ctx.request_history_kline(
            code, start=start, end=end, ktype=kl, max_count=num
        )
    else:
        if subscribed is not None:  # M1 HTTP 场景：自动幂等订阅
            ensure_subscribed(ctx, subscribed, code, k_type)
        # WS 场景传 None：registry.add 已订阅
        ret, df = ctx.get_cur_kline(code, num, ktype=kl)

    if ret != RET_OK:
        raise RuntimeError(f"fetch_history({code},{k_type}) failed: {df}")

    name = str(df["name"].iloc[0]) if len(df) > 0 and "name" in df.columns else ""
    bars = []
    for row in df.itertuples(index=False):
        bars.append(
            {
                "time": time_key_to_epoch(code, row.time_key),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": int(row.volume),
            }
        )
    return bars, name, 0.0


def ensure_subscribed_rt(ctx, subscribed: set, code: str) -> None:
    """幂等订阅分时 RT_DATA（get_rt_data 前必须订阅，实测）。WS 场景由 registry 处理。"""
    key = ("__RT__", code)
    if key in subscribed:
        return
    ret, err = ctx.subscribe([code], [SubType.RT_DATA], is_first_push=False)
    if ret != RET_OK:
        raise RuntimeError(f"subscribe RT_DATA({code}) failed: {err}")
    subscribed.add(key)


def fetch_rt(ctx, code: str, subscribed: set = None):
    """拉分时数据 → (bars, name, last_close)。bars: [{time, price, avg_price, volume}]。

    get_rt_data 必须先 subscribe RT_DATA（实测）。盘外返回最近交易日全天分时。
    time 字段格式同 K 线 time_key（市场本地 naive），复用 time_key_to_epoch。
    """
    if subscribed is not None:
        ensure_subscribed_rt(ctx, subscribed, code)
    ret, df = ctx.get_rt_data(code)
    if ret != RET_OK:
        raise RuntimeError(f"get_rt_data({code}) failed: {df}")

    last_close = float(df["last_close"].iloc[0]) if len(df) > 0 else 0.0
    name = str(df["name"].iloc[0]) if len(df) > 0 and "name" in df.columns else ""
    bars = []
    for row in df.itertuples(index=False):
        bars.append(
            {
                "time": time_key_to_epoch(code, row.time),
                "price": float(row.cur_price),
                "avg_price": float(row.avg_price),
                "volume": int(row.volume),
            }
        )
    return bars, name, last_close


class KlineBridge(CurKlineHandlerBase):
    """futu 接收线程 → asyncio.Queue。无状态，只拆行投递，绝不阻塞。

    on_recv_rsp 跑在 futu 独立子线程（源码 quote_response_handler.py:137 注释），
    用 loop.call_soon_threadsafe 跨线程投到 asyncio 队列。
    """

    def __init__(self, loop, queue):
        super().__init__()
        self._loop = loop
        self._queue = queue

    def on_recv_rsp(self, rsp_pb):
        ret, df = super().on_recv_rsp(rsp_pb)  # 二元组 (ret, DataFrame)，推送 13 列含 k_type
        if ret != RET_OK:
            return ret, df
        for row in df.itertuples(index=False):
            item = {
                "code": row.code,
                "k_type": row.k_type,  # ⏳ 推送 k_type 列格式盘中验证（推断 "K_5M" 字符串）
                "bar": {
                    "time": time_key_to_epoch(row.code, row.time_key),
                    "open": float(row.open),
                    "high": float(row.high),
                    "low": float(row.low),
                    "close": float(row.close),
                    "volume": int(row.volume),
                },
            }
            self._loop.call_soon_threadsafe(self._queue.put_nowait, item)
        return ret, df
