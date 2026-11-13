"""TSP 数据源插件：行情 + 财务（腾讯 / 新浪 / 东方财富）。

一个插件接管四个数据集：
- depth5       五档盘口     腾讯批量（新浪兜底）
- minute       分钟K        新浪 1 分钟
- full_minute  全量分钟     腾讯 m1 当期K（新浪兜底）
- financial    财务五表     东方财富 F10

全部为公开接口，不需要 API Key。
"""
import datetime as _dt
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import polars as pl

try:  # 宿主提供；本地单测没有 app 包时退化为内置异常
    from app.data_providers.base import ProviderRequestError
except ImportError:  # pragma: no cover - 仅在宿主外运行
    class ProviderRequestError(RuntimeError):  # type: ignore[no-redef]
        """宿主 ProviderRequestError 的本地替身。"""

from .finance_client import (
    EastMoneyError,
    fetch_period,
    fetch_symbol as fetch_finance_symbol,
    template_fields,
)
from .finance_mapper import (
    COLUMNS,
    TABLE_REPORTS,
    column_order,
    recent_quarter_ends,
    source_fields,
    to_rows,
)
from .quote_client import (
    UpstreamError,
    fetch_depth,
    fetch_depth_sina,
    fetch_intraday,
    fetch_minute_history,
    to_tencent_symbol,
)

PLUGIN_NAME = "market_data"

# ---- 行情 ----
# 新浪 1 分钟上限 1970 根（实测），1900 根约 8 个交易日
MINUTE_HISTORY_DAYS = 7
# 逐只拉取时的并发数，兼顾速度与上游限流
WORKERS = 16
# 单次 iter_minute 输出帧的标的上限
FRAME_SYMBOLS = 200
MINUTE_COLUMNS = ["symbol", "datetime", "open", "high", "low", "close", "volume", "amount"]

# ---- 财务 ----
# 超过这个标的数就走「按报告期批量」，否则逐只取
BATCH_THRESHOLD = 50
# 首次同步回溯多少个季度（3 年）；之后每轮只补最新期
HISTORY_QUARTERS = 12
# 最新期最多往回试几个季度（不同行业的披露节奏略有差异）
LATEST_PROBE_QUARTERS = 3


def _normalize_symbol(symbol):
    """'600519.sh ' -> '600519.SH'；无法识别返回 None。"""
    if not symbol:
        return None
    text = str(symbol).strip().upper()
    if "." not in text:
        return None
    code, _, suffix = text.rpartition(".")
    if not code or not suffix:
        return None
    return f"{code}.{suffix}"


def _parse_dt(value):
    """接受 datetime / date / 'YYYY-MM-DD HH:MM:SS' / 'YYYY-MM-DD'。"""
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, _dt.date):
        return _dt.datetime(value.year, value.month, value.day)
    text = str(value).strip().replace("T", " ")[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _rows_to_frame(rows):
    if not rows:
        return pl.DataFrame(schema={
            c: (pl.Utf8 if c in ("symbol", "datetime") else pl.Float64) for c in MINUTE_COLUMNS
        })
    return pl.from_dicts(
        [{c: row.get(c) for c in MINUTE_COLUMNS} for row in rows],
        schema={
            "symbol": pl.Utf8,
            "datetime": pl.Datetime,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "amount": pl.Float64,
        },
        strict=False,
    )


def _minute_rows(symbol, start, end):
    try:
        bars = fetch_minute_history(symbol)
    except UpstreamError as exc:
        raise ProviderRequestError(f"分钟K拉取失败（{symbol}）: {exc}") from exc
    out = []
    for bar in bars:
        moment = _parse_dt(bar["datetime"])
        if moment is None:
            continue
        if start is not None and moment < start:
            continue
        if end is not None and moment > end:
            continue
        out.append({**bar, "symbol": symbol, "datetime": moment})
    return out


def _build_finance_frame(table, items):
    """list[dict] -> polars DataFrame，列序与类型固定。"""
    order = column_order(table)
    schema = {"symbol": pl.Utf8, "period_end": pl.Utf8, "announce_date": pl.Utf8}
    for name in COLUMNS[table]:
        schema[name] = pl.Float64
    if not items:
        return pl.DataFrame(schema=schema)
    rows = [{name: item.get(name) for name in order} for item in items]
    return pl.from_dicts(rows, schema=schema, strict=False)


class Provider:
    name = PLUGIN_NAME
    # 面板读取这个属性判断分钟源深度，据此收窄分时与回测区间
    minute_history_days = MINUTE_HISTORY_DAYS

    def __init__(self):
        self.config = SimpleNamespace(datasets={
            "depth5": {}, "minute": {}, "full_minute": {}, "financial": {},
        })

    def close(self):
        """无长连接，无需释放。"""

    # ================= 五档 =================
    def get_depth_batch(self, symbols):
        codes = [s for s in (symbols or []) if to_tencent_symbol(s)]
        if not codes:
            return {}
        data = {}
        primary_error = None
        try:
            data = fetch_depth(codes)
        except UpstreamError as exc:
            primary_error = exc
        # 腾讯缺的或整体失败，用新浪兜底
        missing = [c for c in codes if c not in data]
        if missing:
            try:
                data.update(fetch_depth_sina(missing))
            except UpstreamError as exc:
                if not data:
                    raise ProviderRequestError(
                        f"五档拉取失败（腾讯: {primary_error}；新浪: {exc}）"
                    ) from exc
        return data

    # ================= 分钟K =================
    def get_minute(self, symbols, start_time, end_time, asset_type="stock",
                   on_chunk_done=None, freq="1m"):
        start = _parse_dt(start_time)
        end = _parse_dt(end_time)
        codes = [s for s in (symbols or []) if to_tencent_symbol(s)]
        rows = []
        for index, symbol in enumerate(codes, 1):
            rows.extend(_minute_rows(symbol, start, end))
            if on_chunk_done:
                on_chunk_done(index, len(codes))
        return _rows_to_frame(rows)

    def iter_minute(self, symbols, start_time, end_time, asset_type="stock",
                    freq="1m", on_chunk_done=None):
        start = _parse_dt(start_time)
        end = _parse_dt(end_time)
        codes = [s for s in (symbols or []) if to_tencent_symbol(s)]
        total = len(codes)
        done = 0
        for i in range(0, total, FRAME_SYMBOLS):
            frame_codes = codes[i:i + FRAME_SYMBOLS]
            rows = []
            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                for part in pool.map(lambda s: _minute_rows(s, start, end), frame_codes):
                    rows.extend(part)
                    done += 1
            if on_chunk_done:
                on_chunk_done(done, total)
            yield _rows_to_frame(rows)

    # ================= 全量分钟 =================
    def get_intraday_batch(self, symbols, count=300, asset_type="stock"):
        codes = [s for s in (symbols or []) if to_tencent_symbol(s)]
        if not codes:
            return _rows_to_frame([])

        def one(symbol):
            try:
                bars = fetch_intraday(symbol)
            except UpstreamError:
                bars = []
            if not bars:
                # 腾讯 m1 不可用时退回新浪 1 分钟，只取当日
                try:
                    history = fetch_minute_history(symbol)
                except UpstreamError:
                    return []
                if not history:
                    return []
                latest = max(row["datetime"][:10] for row in history)
                bars = [row for row in history if row["datetime"].startswith(latest)]
            return [{**bar, "symbol": symbol, "datetime": _parse_dt(bar["datetime"])}
                    for bar in bars[-count:]]

        rows = []
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for part in pool.map(one, codes):
                rows.extend(part)
        return _rows_to_frame(rows)

    # ================= 财务 =================
    def get_financials(self, table, symbols, latest_only=False):
        """按 table 返回面板标准财务长表。

        table: metrics / income / balance_sheet / cash_flow / shares
        """
        if table not in TABLE_REPORTS:
            raise ProviderRequestError(f"不支持的数据表: {table}")

        codes = [code for code in (_normalize_symbol(s) for s in (symbols or [])) if code]
        if not codes:
            return _build_finance_frame(table, [])

        if len(codes) < BATCH_THRESHOLD:
            raw_rows = self._fetch_finance_per_symbol(table, codes)
        else:
            # 全市场走批量；批量里没出现的标的（新股/停牌/未披露）不在本轮补，
            # 面板 _merge_report_history 会保留其既有历史，下轮自然补齐。
            raw_rows = self._fetch_finance_by_period(table, latest_only)

        items = to_rows(table, raw_rows, symbols=codes, latest_only=latest_only)
        return _build_finance_frame(table, items)

    def _fetch_finance_by_period(self, table, latest_only):
        rows = []
        periods = (
            recent_quarter_ends(LATEST_PROBE_QUARTERS)
            if latest_only
            else recent_quarter_ends(HISTORY_QUARTERS)
        )
        for report_name in TABLE_REPORTS[table]:
            available = template_fields(report_name, periods[0])
            if available:
                columns = sorted(source_fields(table) & available)
            else:
                columns = None  # 探测不到就整表取，语义仍正确只是慢
            for period in periods:
                try:
                    chunk = fetch_period(report_name, period, columns)
                except EastMoneyError as exc:
                    raise ProviderRequestError(
                        f"财务数据拉取失败（{report_name} {period}）: {exc}"
                    ) from exc
                if chunk:
                    rows.extend(chunk)
                    if latest_only:
                        break  # 最新一期拿到就够，不再往前翻
        return rows

    def _fetch_finance_per_symbol(self, table, codes):
        rows = []
        for code in codes:
            for report_name in TABLE_REPORTS[table]:
                try:
                    chunk = fetch_finance_symbol(report_name, code)
                except EastMoneyError as exc:
                    raise ProviderRequestError(f"财务数据拉取失败（{code}）: {exc}") from exc
                if chunk:
                    rows.extend(chunk)
                    break  # 命中该行业模板即止
        return rows

    # ================= 试拉 =================
    def test_dataset(self, dataset, symbols=None):
        if dataset in ("depth5", "minute", "full_minute"):
            return self._test_quote(dataset, symbols)
        if dataset == "financial":
            return self._test_finance(dataset, symbols)
        return {
            "provider": self.name, "dataset": dataset, "rows": 0,
            "columns": [], "preview": [],
            "error": f"本插件不提供 {dataset} 数据集",
        }

    def _test_quote(self, dataset, symbols):
        code = (symbols or ["600519.SH"])[0]
        try:
            if dataset == "depth5":
                data = fetch_depth([code])
                rows = len(data)
                preview = [{code: data.get(code)}] if data else []
                columns = ["bid_prices", "bid_volumes", "ask_prices", "ask_volumes", "timestamp"]
            elif dataset == "minute":
                items = fetch_minute_history(code)
                rows = len(items)
                preview = items[-3:]
                columns = MINUTE_COLUMNS
            else:
                items = fetch_intraday(code)
                rows = len(items)
                preview = items[-3:]
                columns = MINUTE_COLUMNS
        except UpstreamError as exc:
            return {"provider": self.name, "dataset": dataset, "rows": 0,
                    "columns": [], "preview": [], "error": f"上游不可用: {exc}"}
        return {"provider": self.name, "dataset": dataset, "rows": rows,
                "columns": columns, "preview": preview}

    def _test_finance(self, dataset, symbols):
        code = _normalize_symbol((symbols or ["600519.SH"])[0]) or "600519.SH"
        try:
            raw = fetch_finance_symbol(TABLE_REPORTS["income"][0], code)
            items = to_rows("income", raw, symbols=[code], latest_only=True)
        except EastMoneyError as exc:
            return {"provider": self.name, "dataset": dataset, "rows": 0,
                    "columns": [], "preview": [], "error": f"东财接口不可用: {exc}"}
        return {"provider": self.name, "dataset": dataset, "rows": len(items),
                "columns": column_order("income"), "preview": items[:3]}
