"""免费行情上游：腾讯（五档 / 当日分时）+ 新浪（1 分钟历史）。

只依赖标准库。腾讯返回 GBK，需按 gbk 解码。
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT_SEC = 15
MAX_RETRY = 3
# 腾讯批量接口一次 800 只稳定，留余量
QUOTE_BATCH = 400
MIN_INTERVAL_SEC = 0.02
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_last_call = [0.0]


class UpstreamError(RuntimeError):
    """上游请求失败。"""


def _throttle():
    elapsed = time.monotonic() - _last_call[0]
    if elapsed < MIN_INTERVAL_SEC:
        time.sleep(MIN_INTERVAL_SEC - elapsed)
    _last_call[0] = time.monotonic()


def _get(url, referer):
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Referer": referer})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        return resp.read()


def _get_with_retry(url, referer):
    last = None
    for attempt in range(MAX_RETRY):
        try:
            _throttle()
            return _get(url, referer)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(0.3 * (2 ** attempt))
    raise UpstreamError(f"请求失败: {last}")


def to_tencent_symbol(symbol):
    """600519.SH -> sh600519；000001.SZ -> sz000001。"""
    text = str(symbol or "").strip().upper()
    if "." not in text:
        return None
    code, _, suffix = text.rpartition(".")
    if len(code) != 6:
        return None
    if suffix == "SH":
        return "sh" + code
    if suffix == "SZ":
        return "sz" + code
    return None


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_depth(symbols):
    """批量五档。返回 {symbol: {bid_prices, bid_volumes, ask_prices, ask_volumes, timestamp}}。"""
    pairs = [(s, to_tencent_symbol(s)) for s in symbols]
    pairs = [(s, t) for s, t in pairs if t]
    out = {}
    for i in range(0, len(pairs), QUOTE_BATCH):
        chunk = pairs[i:i + QUOTE_BATCH]
        url = "https://qt.gtimg.cn/q=" + ",".join(t for _, t in chunk)
        raw = _get_with_retry(url, "https://gu.qq.com/")
        text = raw.decode("gbk", "replace")
        by_tencent = {}
        for line in text.split("\n"):
            if "=" not in line:
                continue
            head, _, body = line.partition("=")
            key = head.strip().replace("v_", "")
            fields = body.strip().strip(';').strip('"').split("~")
            if len(fields) < 40:
                continue
            by_tencent[key] = fields
        for symbol, tcode in chunk:
            fields = by_tencent.get(tcode)
            if not fields:
                continue
            bid_prices = [_num(fields[9 + 2 * k]) for k in range(5)]
            bid_volumes = [_num(fields[10 + 2 * k]) for k in range(5)]
            ask_prices = [_num(fields[19 + 2 * k]) for k in range(5)]
            ask_volumes = [_num(fields[20 + 2 * k]) for k in range(5)]
            if not any(p for p in bid_prices) and not any(p for p in ask_prices):
                continue
            out[symbol] = {
                "bid_prices": bid_prices,
                "bid_volumes": bid_volumes,
                "ask_prices": ask_prices,
                "ask_volumes": ask_volumes,
                "timestamp": _parse_tencent_time(fields[30]),
            }
    return out


def _parse_tencent_time(value):
    """'20261109111158' -> 毫秒时间戳（按北京时间墙钟解释）。"""
    import datetime as _dt

    text = str(value or "").strip()
    if len(text) != 14 or not text.isdigit():
        return None
    try:
        moment = _dt.datetime(
            int(text[0:4]), int(text[4:6]), int(text[6:8]),
            int(text[8:10]), int(text[10:12]), int(text[12:14]),
        )
    except ValueError:
        return None
    # 北京时间墙钟 -> epoch 毫秒
    return int(moment.replace(tzinfo=_dt.timezone(_dt.timedelta(hours=8))).timestamp() * 1000)


def fetch_depth_sina(symbols):
    """新浪批量五档（腾讯挂掉时的兜底）。返回结构与 fetch_depth 一致。"""
    pairs = [(s, to_tencent_symbol(s)) for s in symbols]
    pairs = [(s, t) for s, t in pairs if t]
    out = {}
    for i in range(0, len(pairs), QUOTE_BATCH):
        chunk = pairs[i:i + QUOTE_BATCH]
        url = "https://hq.sinajs.cn/list=" + ",".join(t for _, t in chunk)
        raw = _get_with_retry(url, "https://finance.sina.com.cn")
        text = raw.decode("gbk", "replace")
        by_code = {}
        for line in text.split("\n"):
            if '="' not in line:
                continue
            head, _, body = line.partition('="')
            code = head.strip().replace("var hq_str_", "")
            fields = body.strip().rstrip(";").rstrip('"').split(",")
            if len(fields) < 32:
                continue
            by_code[code] = fields
        for symbol, tcode in chunk:
            fields = by_code.get(tcode)
            if not fields:
                continue
            # 10~19 买一量/价 ... 买五量/价；20~29 卖一量/价 ... 卖五量/价
            bid_prices = [_num(fields[11 + 2 * k]) for k in range(5)]
            bid_volumes = [_shares_to_lots(fields[10 + 2 * k]) for k in range(5)]
            ask_prices = [_num(fields[21 + 2 * k]) for k in range(5)]
            ask_volumes = [_shares_to_lots(fields[20 + 2 * k]) for k in range(5)]
            if not any(bid_prices) and not any(ask_prices):
                continue
            out[symbol] = {
                "bid_prices": bid_prices,
                "bid_volumes": bid_volumes,
                "ask_prices": ask_prices,
                "ask_volumes": ask_volumes,
                "timestamp": _parse_sina_time(fields[30], fields[31]),
            }
    return out


def _shares_to_lots(value):
    """新浪盘口量是股，面板要手。"""
    number = _num(value)
    return None if number is None else number / 100


def _parse_sina_time(date_text, time_text):
    import datetime as _dt

    try:
        moment = _dt.datetime.strptime(f"{date_text} {time_text}", "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None
    return int(moment.replace(tzinfo=_dt.timezone(_dt.timedelta(hours=8))).timestamp() * 1000)


def fetch_minute_history(symbol, max_bars=1900):
    """新浪 1 分钟历史。实测 datalen 上限 1970（1971 返回 null），取 1900 留余量。"""
    tcode = to_tencent_symbol(symbol)
    if not tcode:
        return []
    query = urllib.parse.urlencode({"symbol": tcode, "scale": "1", "datalen": str(max_bars)})
    url = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?" + query
    raw = _get_with_retry(url, "https://finance.sina.com.cn")
    try:
        rows = json.loads(raw.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return []
    out = []
    for row in rows or []:
        dt = str(row.get("day") or "")
        close = _num(row.get("close"))
        if not dt or close is None:
            continue
        volume = _num(row.get("volume"))
        out.append({
            "datetime": dt,
            "open": _num(row.get("open")),
            "high": _num(row.get("high")),
            "low": _num(row.get("low")),
            "close": close,
            # 新浪成交量是股，面板要手
            "volume": volume / 100 if volume is not None else None,
            "amount": _num(row.get("amount")),
        })
    return out


def fetch_intraday(symbol):
    """腾讯 1 分钟K（当日）。返回 [{'datetime','open','high','low','close','volume','amount'}]。

    用 mkline 的 m1 而不是分时接口：分时只给每分钟一个价格，OHLC 会退化成一条线。
    该接口不提供成交额，amount 保持 None（面板按缺省处理）。
    """
    tcode = to_tencent_symbol(symbol)
    if not tcode:
        return []
    url = f"https://ifzq.gtimg.cn/appstock/app/kline/mkline?param={tcode},m1,,320"
    raw = _get_with_retry(url, "https://gu.qq.com/")
    try:
        payload = json.loads(raw.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return []
    node = (payload.get("data") or {}).get(tcode) or {}
    bars = node.get("m1") or []

    parsed = []
    for bar in bars:
        if len(bar) < 6:
            continue
        stamp = str(bar[0])
        if len(stamp) != 12 or not stamp.isdigit():
            continue
        moment = (f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]} "
                  f"{stamp[8:10]}:{stamp[10:12]}:00")
        parsed.append({
            "datetime": moment,
            "open": _num(bar[1]),
            "close": _num(bar[2]),
            "high": _num(bar[3]),
            "low": _num(bar[4]),
            "volume": _num(bar[5]),   # 手
            "amount": None,
        })

    if not parsed:
        return []
    # 只保留最新交易日（接口会给到前一天的尾部）
    latest_day = max(row["datetime"][:10] for row in parsed)
    return [row for row in parsed if row["datetime"].startswith(latest_day)]
