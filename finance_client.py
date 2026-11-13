"""东方财富公开财报接口客户端：限速、重试、进程内缓存。

只依赖标准库，便于在宿主外单测。
接口：https://datacenter.eastmoney.com/securities/api/data/v1/get

两种取数模式：
- ``fetch_symbol``  逐只取单只股票全历史（标的少时用）
- ``fetch_period``  按报告期批量取全市场（标的多时用，快两个数量级）
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://datacenter.eastmoney.com/securities/api/data/v1/get"

# 东财对匿名调用有软限流，保守取 4 req/s
MIN_INTERVAL_SEC = 0.25
MAX_RETRY = 3
TIMEOUT_SEC = 25
CACHE_TTL_SEC = 900

# 单页上限 500（更大值会被服务端截断）
PAGE_SIZE = 500
MAX_PAGES = 60

# 东财用 null / 9201 表示"该标的不在这套行业模板下"
EMPTY_CODE = 9201

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://emweb.securities.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
}

# {cache_key: (fetched_at, value)}
_CACHE = {}
_last_call = [0.0]


class EastMoneyError(RuntimeError):
    """东财请求失败（网络、限流、结构变化）。"""


def _throttle():
    elapsed = time.monotonic() - _last_call[0]
    if elapsed < MIN_INTERVAL_SEC:
        time.sleep(MIN_INTERVAL_SEC - elapsed)
    _last_call[0] = time.monotonic()


def _cached(key):
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL_SEC:
        return hit[1]
    return None


def _store(key, value):
    _CACHE[key] = (time.monotonic(), value)
    return value


def _build_url(**query):
    return BASE_URL + "?" + urllib.parse.urlencode(
        {k: v for k, v in query.items() if v is not None}
    )


def _request(url):
    """单次 GET，返回 (rows, pages)。空数据返回 ([], 0)。"""
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        payload = json.loads(resp.read().decode("utf-8", "replace"))

    code = payload.get("code")
    if code == EMPTY_CODE:
        return [], 0
    if code not in (0, None):
        raise EastMoneyError(f"接口返回 code={code} msg={payload.get('message')}")

    result = payload.get("result") or {}
    rows = result.get("data") or []
    pages = int(result.get("pages") or 0)
    return rows, pages


def _request_with_retry(url):
    last_error = None
    for attempt in range(MAX_RETRY):
        try:
            _throttle()
            return _request(url)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, EastMoneyError) as exc:
            last_error = exc
            time.sleep(0.6 * (2 ** attempt))
    raise EastMoneyError(f"东财请求失败: {last_error}")


def fetch_symbol(report_name, secu_code):
    """单只股票某张表的全历史行（东财原始结构）。"""
    key = ("symbol", report_name, secu_code)
    cached = _cached(key)
    if cached is not None:
        return cached

    url = _build_url(
        reportName=report_name,
        columns="ALL",
        pageNumber="1",
        pageSize="200",
        sortColumns="REPORT_DATE",
        sortTypes="-1",
        filter=f'(SECUCODE="{secu_code}")',
    )
    rows, _ = _request_with_retry(url)
    return _store(key, rows)


def template_fields(report_name, period):
    """探测某套报表模板实际有哪些字段（列名不存在的列会让接口报 9501）。

    必须带 filter，否则东财按「重查询」返回 9701 服务器繁忙。
    """
    key = ("fields", report_name)
    cached = _cached(key)
    if cached is not None:
        return cached

    url = _build_url(
        reportName=report_name,
        columns="ALL",
        pageNumber="1",
        pageSize="1",
        sortColumns="SECURITY_CODE",
        sortTypes="1",
        filter=f"(REPORT_DATE='{period}')",
    )
    rows, _ = _request_with_retry(url)
    if not rows:
        return frozenset()  # 空结果不缓存，换个报告期还能再探
    return _store(key, frozenset(rows[0].keys()))


def fetch_period(report_name, period, columns):
    """按报告期批量取全市场。columns 为 None 时取全部列。

    columns 里带该模板不存在的字段会让接口报 9501，调用方需先用
    ``template_fields`` 探测后裁剪。
    """
    key = ("period", report_name, period, tuple(columns) if columns else None)
    cached = _cached(key)
    if cached is not None:
        return cached

    rows = []
    page = 1
    pages = 1
    while page <= pages and page <= MAX_PAGES:
        url = _build_url(
            reportName=report_name,
            columns=",".join(columns) if columns else "ALL",
            pageNumber=str(page),
            pageSize=str(PAGE_SIZE),
            # 同一报告期内 REPORT_DATE 全相同，必须按代码排序分页才稳定
            sortColumns="SECURITY_CODE",
            sortTypes="1",
            filter=f"(REPORT_DATE='{period}')",
        )
        chunk, total_pages = _request_with_retry(url)
        rows.extend(chunk)
        pages = total_pages or 1
        page += 1

    return _store(key, rows)


def clear_cache():
    _CACHE.clear()
