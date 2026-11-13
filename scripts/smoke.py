"""真实接口冒烟：四个数据集各打一发。"""
import pathlib
import sys
import time
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
pkg = types.ModuleType("market_data")
pkg.__path__ = [str(ROOT)]
sys.modules.setdefault("market_data", pkg)

from market_data.provider import Provider  # noqa: E402

CODES = ["600519.SH", "000001.SZ", "600030.SH"]


def main():
    p = Provider()

    t0 = time.monotonic()
    depth = p.get_depth_batch(CODES)
    print(f"[depth5] {len(depth)} 只, {time.monotonic()-t0:.2f}s")
    for k, v in depth.items():
        print(f"   {k} 买1={v['bid_prices'][0]}x{v['bid_volumes'][0]} "
              f"卖1={v['ask_prices'][0]}x{v['ask_volumes'][0]}")

    t0 = time.monotonic()
    frame = p.get_minute(["600519.SH"], None, None)
    print(f"\n[minute] rows={frame.height} {time.monotonic()-t0:.2f}s")
    if frame.height:
        print("   最早:", frame.row(0, named=True)["datetime"])
        print("   最新:", frame.row(frame.height - 1, named=True)["datetime"])

    t0 = time.monotonic()
    intra = p.get_intraday_batch(["600519.SH"], count=400)
    print(f"\n[full_minute] rows={intra.height} {time.monotonic()-t0:.2f}s")
    if intra.height:
        print("   首:", intra.row(0, named=True))
        print("   末:", intra.row(intra.height - 1, named=True))

    for table in ("income", "balance_sheet", "cash_flow", "metrics", "shares"):
        t0 = time.monotonic()
        fin = p.get_financials(table, CODES, latest_only=True)
        print(f"\n[financial/{table}] rows={fin.height} cols={fin.width} "
              f"{time.monotonic()-t0:.2f}s")


if __name__ == "__main__":
    main()
