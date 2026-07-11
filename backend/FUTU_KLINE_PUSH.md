# 富途 OpenD K 线接口实测（M0 产出）

供 vs-kline 后端实现依赖。**盘外实测日期 2026-07-11 周六**（`market_hk=CLOSED`、`market_us=AFTER_HOURS_END`），OpenD v10.8.6808 + futu-api v10.08，`qot_logined=True`。实时推送 fire 那项盘外无法验，标 ⏳ 留盘中。

## 1. 枚举（KLType / SubType，实测一致）

```
K_1M  K_3M  K_5M  K_10M  K_15M  K_30M  K_60M
K_120M  K_180M  K_240M
K_DAY  K_WEEK  K_MON  K_QUARTER  K_YEAR
```

- 历史 K 线用 `KLType.K_5M` 等；订阅推送用 `SubType.K_5M` 等。**两套枚举同名但别混**。
- 比预期更全：含 K_120M/K_180M/K_240M/K_QUARTER/K_YEAR。

## 2. 权限（实测 ret=0 即有权限，休市可测）

| 标的 | subscribe ret | 结论 |
|---|---|---|
| `HK.02800`（盈富基金）K_5M | 0 | ✅ 港股 K 线有权限 |
| `US.AAPL`（苹果）K_5M | 0 | ✅ 美股 K 线有权限 |

→ 港股、美股 K 线订阅与历史都免费可用（moomoo 海外账户）。

## 3. get_cur_kline（同步快照，初始填充用）— 实测结构

签名：`ctx.get_cur_kline(code, num, ktype=KLType.K_5M)` → `(ret, df)` 二元组。

**返回 12 列（无 k_type！）**：
```
['code', 'name', 'time_key', 'open', 'close', 'high', 'low',
 'volume', 'turnover', 'pe_ratio', 'turnover_rate', 'last_close']
```

⚠️ **与实时推送的 13 列不同**：推送多一个 `k_type` 列（见 §5）。`get_cur_kline` 的 ktype 是入参，结果省略 `k_type` 列。后端拉历史时**不能按推送列名取 `k_type`**，要自己用入参的 k_type 标注。

⚠️ **分钟级 get_cur_kline 必须先 subscribe**（M1 实测，重要坑）：直接调 `get_cur_kline(code, num, KLType.K_5M)` 报「请求获取实时K线接口前，请先订阅KL_5Min数据」。必须先 `ctx.subscribe([code],[SubType.K_5M], is_first_push=False)` 再 get_cur_kline。**K_DAY 走 `request_history_kline` 无此要求**。后端 `fetch_history` 已对分钟级做幂等订阅（M1 简版 `app.state.subscribed` 集合只增不减，M2 用 registry 引用计数 unsubscribe 替换）。

实测样本（HK.02800 K_5M，盘外返回上周五收盘前最后 10 根）：
```
code     name     time_key             open   close  high   low    volume     turnover
HK.02800 盈富基金 2026-07-10 15:55:00  24.60  24.62  24.62  24.58 31699000   779884400
HK.02800 盈富基金 2026-07-10 16:00:00  24.62  24.62  24.66  24.62 27731500   683051300
```

- 盘外：返回最近 N 根历史，**不含**当前在途 K 线（无在途）。
- 盘中：最后一根会是当前未走完那根（待盘中确认，但符合接口语义）。
- ETF（HK.02800）的 `pe_ratio`/`turnover_rate` 为 0（ETF 无此指标）；AAPL 盘外快照也是 0（可能仅实时推送/snapshot 填）。K 线只用 OHLCV，不受影响。

## 4. time_key 时区换算（关键，实测确认）

`time_key` 是 **市场本地 naive 字符串**，格式 `YYYY-MM-DD HH:MM:SS`：

| 市场 | time_key 时区 | 证据（实测最后一根 16:00） | zoneinfo key |
|---|---|---|---|
| 港股 `HK.*` | 北京时间 / HKT（UTC+8） | 16:00 = 港股收盘 | `Asia/Shanghai` |
| 美股 `US.*` | 美东 ET（夏 UTC-4 / 冬 UTC-5） | 16:00 = 美股收盘 | `America/New_York` |

**港股与美股的 time_key 数值可能相同（如都 16:00），但时区不同**——转 UTC 必须按 code 前缀选时区，否则时间错位。

后端 `time_key_to_epoch(code, time_key)` 实现：
```python
from zoneinfo import ZoneInfo
from datetime import datetime
TZ_BY_MARKET = {'HK.': ZoneInfo('Asia/Shanghai'), 'US.': ZoneInfo('America/New_York')}

def time_key_to_epoch(code, time_key):
    tz = next((v for k, v in TZ_BY_MARKET.items() if code.startswith(k)), ZoneInfo('UTC'))
    dt = datetime.strptime(time_key, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
    return int(dt.timestamp())   # UTC 秒，lightweight-charts 要求
```
`America/New_York` 的 zoneinfo 自动处理夏令时切换，无需手动判断。

## 5. 实时推送 CurKlineHandlerBase（源码核实 + ⏳ 盘外未运行时验证）

源码（`futu/quote/quote_response_handler.py:108-152`）核实，盘外未触发运行时验证：

- handler 基类 **`CurKlineHandlerBase`**（`Kline` 小写 l）
- 回调 **`on_recv_rsp(self, rsp_pb)`** → 二元组 `(ret_code, DataFrame)`；**跑在独立子线程**
- 推送 DataFrame **13 列**（比 get_cur_kline 多 `k_type`）：
  ```
  code/name/time_key/open/close/high/low/volume/turnover/k_type/last_close/pe_ratio/turnover_rate
  ```
- ⏳ 盘外 `is_first_push=True` 0 次触发；盘中持续 fire 留周一（港股 09:30-12:00/13:00-16:00 HKT、美股 21:30-04:00 北京夏令时）验证。

## 6. 对后端实现的影响（固化决策）

1. **拉历史**：`get_cur_kline(code, 300, KLType.K_5M)` 拿最近 N 根填充日内图；返回**无 k_type 列**，后端自己用入参 k_type 标注。日级用 `request_history_kline(code, start, end, KLType.K_DAY, max_count)`。
2. **时区**：历史与实时**必须共用同一个 `time_key_to_epoch(code, time_key)`**（§4），否则在途那根 K 线 time 对不上 → `series.update` 退化成新增。
3. **实时桥接**：`on_recv_rsp` 在 futu 子线程，用 `loop.call_soon_threadsafe(queue.put_nowait, item)` 投到 asyncio，回调内绝不阻塞。
4. **推送列取值**：实时推送有 `k_type` 列可做多标的/多周期路由；快照没有，靠入参。
5. **衔接**：`get_cur_kline` 盘中最后一根的 time_key == 第一条实时推送的 time_key（同一根在途 K 线），前端 `series.update` 对相同 time 原地更新，无需 dedupe。

## 7. 待盘中验证（M0 收尾，周一盘中补）

- [ ] `subscribe(K_5M) is_first_push=False` 盘中持续 fire，`on_recv_rsp` 返回 DataFrame 列与 §5 一致
- [ ] `get_cur_kline` 盘中最后一根为当前未走完那根（time_key == 实时首推 time_key）
- [ ] 美股盘中（21:30 后）实时推送正常（盘外只能验权限与快照）
