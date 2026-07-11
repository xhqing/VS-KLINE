#!/usr/bin/env python3
"""富途 OpenD K 线实时推送探针（M0）。

解答 4 个 futu-api 源码答不了的待测项：
  1. 实时推送盘中是否持续 fire（on_recv_rsp 触发次数）
  2. time_key 字符串格式与时区（HK 北京 / US 美东）
  3. 美股 K 线权限（subscribe ret=0 即有权限）
  4. 盘外 is_first_push=True 是否给一帧

用法: python3 probe_kline_push.py [CODE] [K_TYPE]
默认: python3 probe_kline_push.py HK.02800 K_5M

已源码核实（futu-api v10.08，quote_response_handler.py:108-152）：
  - handler 基类 CurKlineHandlerBase（l 小写）
  - 回调 on_recv_rsp(self, rsp_pb) → (ret_code, DataFrame) 二元组
  - 推送在独立子线程，绝不在回调里阻塞
  - DataFrame 列: code/name/time_key/open/close/high/low/volume/turnover/k_type/last_close/pe_ratio/turnover_rate
"""
import sys
import time
import signal
from futu import OpenQuoteContext, CurKlineHandlerBase, SubType, KLType, RET_OK


class Probe(CurKlineHandlerBase):
    """统计推送次数并打印回调结构。"""
    fire = 0

    def on_recv_rsp(self, rsp_pb):
        ret, df = super().on_recv_rsp(rsp_pb)  # 二元组，已核实
        Probe.fire += 1
        print(f">>> on_recv_rsp #{Probe.fire} ret={ret}")
        if ret == RET_OK:
            print("    columns:", list(df.columns))
            print("    k_type unique:", df['k_type'].unique().tolist())
            print("    code unique:", df['code'].unique().tolist())
            print(df[['code', 'time_key', 'k_type', 'open', 'high', 'low', 'close', 'volume']].to_string(index=False))
        return ret, df


def main():
    # macOS 无 timeout 命令，用 SIGALRM 做硬超时防 WebSocket/等待挂起
    signal.signal(signal.SIGALRM, lambda *_: (print(">>> 硬超时退出"), sys.exit(0)))

    code = sys.argv[1] if len(sys.argv) > 1 else 'HK.02800'
    kt = sys.argv[2] if len(sys.argv) > 2 else 'K_5M'

    ctx = OpenQuoteContext('127.0.0.1', 11111)
    try:
        # ① 登录态
        print("=== global_state ===")
        print(ctx.get_global_state())

        # ② 静态枚举（盘外安全，不触发推送）
        print("\n=== 枚举（盘外可安全读取）===")
        print("SubType.K_*:", [m for m in dir(SubType) if m.startswith('K_')])
        print("KLType.K_* :", [m for m in dir(KLType) if m.startswith('K_')])

        # ③ 权限：subscribe ret=0 即有权限（休市可测）
        print(f"\n=== subscribe({code}, {kt}) ===")
        ret, err = ctx.subscribe([code], [getattr(SubType, kt)], is_first_push=True)
        print(f"ret={ret} err={err}  ({'有权限' if ret == RET_OK else '无权限/错误'})")

        # ④ 同步快照（盘外可拿，含当前未走完那根；验证 time_key 格式与时区）
        print(f"\n=== get_cur_kline({code}, 10, {kt}) ===")
        r2, df2 = ctx.get_cur_kline(code, 10, ktype=getattr(KLType, kt))
        print("ret=", r2)
        if r2 == RET_OK:
            print("    columns:", list(df2.columns))
            print(df2.to_string(index=False))

        # ⑤ 触发推送（盘外靠 is_first_push 首帧；盘中持续实时）
        ctx.set_handler(Probe())
        print("\n>>> 等 20s 收推送（盘外可能 0~1 次；盘中持续）…")
        signal.alarm(30)
        time.sleep(20)
        print(f">>> 共触发 {Probe.fire} 次 on_recv_rsp")
    finally:
        ctx.close()


if __name__ == '__main__':
    main()
