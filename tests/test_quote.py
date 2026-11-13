"""不联网的解析测试：构造上游原始返回，验证字段落位与单位换算。"""
import json
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
pkg = types.ModuleType("market_data")
pkg.__path__ = [str(ROOT)]
sys.modules.setdefault("market_data", pkg)
sys.path.insert(0, str(ROOT))

from market_data import provider, quote_client as client  # noqa: E402


def _tencent_line(symbol_code):
    """构造一条腾讯行情串（41 个字段，索引与真实返回一致）。"""
    fields = [""] * 41
    fields[0] = "1"
    fields[1] = "测试股"
    fields[2] = symbol_code[-6:]
    fields[3] = "10.50"
    fields[4] = "10.00"
    fields[5] = "10.10"
    for k in range(5):  # 买一~买五
        fields[9 + 2 * k] = f"{10.49 - 0.01 * k:.2f}"
        fields[10 + 2 * k] = str(100 + k)
    for k in range(5):  # 卖一~卖五
        fields[19 + 2 * k] = f"{10.51 + 0.01 * k:.2f}"
        fields[20 + 2 * k] = str(200 + k)
    fields[30] = "20261109111158"
    return f'v_{symbol_code}="' + "~".join(fields) + '";\n'


def _with_stub(fn):
    """替换 client._get_with_retry 后执行 fn，结束后还原。"""
    original = client._get_with_retry
    try:
        return fn()
    finally:
        client._get_with_retry = original


def test_symbol_mapping():
    assert client.to_tencent_symbol("600519.SH") == "sh600519"
    assert client.to_tencent_symbol("000001.SZ") == "sz000001"
    assert client.to_tencent_symbol("600519.sh") == "sh600519"
    assert client.to_tencent_symbol("600519") is None
    assert client.to_tencent_symbol("BTCUSDT") is None


def test_parse_dt():
    import datetime as dt

    assert provider._parse_dt("2026-11-09 09:34:00") == dt.datetime(2026, 11, 9, 9, 34)
    assert provider._parse_dt("2026-11-09") == dt.datetime(2026, 11, 9)
    assert provider._parse_dt(dt.date(2026, 11, 9)) == dt.datetime(2026, 11, 9)
    assert provider._parse_dt(None) is None
    assert provider._parse_dt("") is None


def test_depth_parsing():
    def run():
        client._get_with_retry = lambda url, ref: _tencent_line("sh600519").encode("gbk")
        return client.fetch_depth(["600519.SH", "BADCODE"])

    data = _with_stub(run)
    assert set(data) == {"600519.SH"}
    row = data["600519.SH"]
    assert row["bid_prices"][0] == 10.49
    assert row["bid_prices"][4] == 10.45
    assert row["bid_volumes"][0] == 100
    assert row["ask_prices"][0] == 10.51
    assert row["ask_volumes"][4] == 204
    assert isinstance(row["timestamp"], int)


def test_minute_history_units():
    payload = json.dumps([
        {"day": "2026-11-09 09:34:00", "open": "1442.95", "high": "1448.8",
         "low": "1441.52", "close": "1447.87", "volume": "21000", "amount": "30358343.0"},
    ]).encode()

    def run():
        client._get_with_retry = lambda url, ref: payload
        return client.fetch_minute_history("600519.SH")

    rows = _with_stub(run)
    assert len(rows) == 1
    row = rows[0]
    assert row["datetime"] == "2026-11-09 09:34:00"
    assert row["close"] == 1447.87
    assert row["volume"] == 210.0          # 股 -> 手
    assert row["amount"] == 30358343.0     # 元


def test_intraday_ohlc_and_latest_day():
    payload = json.dumps({"data": {"sh600519": {"m1": [
        ["202611111500", "1400.00", "1401.00", "1402.00", "1399.00", "120.00", {}, "0.08"],
        ["202611120930", "1395.13", "1395.50", "1396.00", "1394.00", "257.00", {}, "0.16"],
        ["202611121500", "1404.00", "1410.27", "1410.27", "1404.00", "1982.00", {}, "1.59"],
    ]}}}).encode()

    def run():
        client._get_with_retry = lambda url, ref: payload
        return client.fetch_intraday("600519.SH")

    rows = _with_stub(run)
    # 只保留最新交易日
    assert [r["datetime"] for r in rows] == [
        "2026-11-12 09:30:00", "2026-11-12 15:00:00",
    ]
    first = rows[0]
    assert first["open"] == 1395.13
    assert first["close"] == 1395.50
    assert first["high"] == 1396.00
    assert first["low"] == 1394.00
    assert first["volume"] == 257.0      # 手
    assert first["amount"] is None       # 接口不提供成交额


def test_provider_declares_three_datasets():
    p = provider.Provider()
    assert set(p.config.datasets) == {"depth5", "minute", "full_minute", "financial"}
    assert p.name == "market_data"
    assert p.minute_history_days == 7


def test_sina_depth_fallback_parsing():
    fields = [""] * 34
    fields[0] = "测试股"
    fields[1], fields[2], fields[3] = "10.00", "9.90", "10.10"
    fields[8], fields[9] = "100000", "1000000"
    for k in range(5):   # 买一~买五（量是股）
        fields[10 + 2 * k] = str((100 + k) * 100)
        fields[11 + 2 * k] = f"{10.09 - 0.01 * k:.2f}"
    for k in range(5):   # 卖一~卖五
        fields[20 + 2 * k] = str((200 + k) * 100)
        fields[21 + 2 * k] = f"{10.11 + 0.01 * k:.2f}"
    fields[30], fields[31] = "2026-11-13", "14:34:05"
    line = 'var hq_str_sh600519="' + ",".join(fields) + '";\n'

    def run():
        client._get_with_retry = lambda url, ref: line.encode("gbk")
        return client.fetch_depth_sina(["600519.SH"])

    data = _with_stub(run)
    row = data["600519.SH"]
    assert row["bid_prices"][0] == 10.09
    assert row["bid_prices"][4] == 10.05
    assert row["bid_volumes"][0] == 100.0     # 股 -> 手
    assert row["ask_prices"][0] == 10.11
    assert row["ask_volumes"][4] == 204.0
    assert isinstance(row["timestamp"], int)


def test_depth_falls_back_to_sina():
    """腾讯失败时，五档应自动切新浪。"""
    import json as _json

    p = provider.Provider()

    sina = [""] * 34
    sina[0] = "测试股"
    for k in range(5):
        sina[10 + 2 * k] = "10000"
        sina[11 + 2 * k] = f"{10.09 - 0.01 * k:.2f}"
        sina[20 + 2 * k] = "20000"
        sina[21 + 2 * k] = f"{10.11 + 0.01 * k:.2f}"
    sina[30], sina[31] = "2026-11-13", "14:34:05"
    line = 'var hq_str_sh600519="' + ",".join(sina) + '";'

    def failing_tencent(url, ref):
        raise client.UpstreamError("腾讯挂了")

    def ok_sina(url, ref):
        return line.encode("gbk")

    original = client._get_with_retry
    try:
        # 第一次调用（腾讯）抛错，第二次（新浪）返回数据
        calls = {"n": 0}

        def dispatch(url, ref):
            calls["n"] += 1
            if "gtimg" in url:
                raise client.UpstreamError("腾讯挂了")
            return line.encode("gbk")

        client._get_with_retry = dispatch
        data = p.get_depth_batch(["600519.SH"])
    finally:
        client._get_with_retry = original

    assert "600519.SH" in data
    assert data["600519.SH"]["bid_prices"][0] == 10.09


def test_manifest_name_matches_provider():
    text = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
    assert "name: market_data" in text
    assert "datasets: [depth5, minute, full_minute, financial]" in text


