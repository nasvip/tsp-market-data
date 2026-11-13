"""映射与日期归一测试（不需要网络）。"""
import datetime as _dt
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
_pkg = types.ModuleType("market_data")
_pkg.__path__ = [str(ROOT)]
sys.modules.setdefault("market_data", _pkg)

from market_data import finance_mapper as mapper  # noqa: E402

# 取自 600519.SH 2026-09-30 的真实返回（精简到相关字段）
RAW_INCOME = [{
    "SECUCODE": "600519.SH",
    "REPORT_DATE": "2026-09-30 00:00:00",
    "NOTICE_DATE": "2026-10-31 00:00:00",
    "OPERATE_INCOME": 130970743649.04,
    "OPERATE_COST": 13645718932.9,
    "OPERATE_PROFIT": 88979846257.79,
    "SALE_EXPENSE": 4830628836.78,
    "MANAGE_EXPENSE": 5322622377.82,
    "RESEARCH_EXPENSE": 147652442.32,
    "FINANCE_EXPENSE": -366975810.84,
    "NONBUSINESS_INCOME": 47105398.34,
    "NONBUSINESS_EXPENSE": 9289684.5,
    "TOTAL_PROFIT": 89017661971.63,
    "INCOME_TAX": 22300518753.59,
    "NETPROFIT": 66717143218.04,
    "PARENT_NETPROFIT": 64467425981.95,
    "DEDUCT_PARENT_NETPROFIT": 64324824599.18,
    "BASIC_EPS": 51.53,
    "DILUTED_EPS": 51.53,
}]

RAW_BALANCE = [{
    "SECUCODE": "600519.SH",
    "REPORT_DATE": "2026-09-30 00:00:00",
    "NOTICE_DATE": "2026-10-31 00:00:00",
    "TOTAL_ASSETS": 318304891882.72,
    "TOTAL_CURRENT_ASSETS": 269646861755.67,
    "TOTAL_NONCURRENT_ASSETS": 48658030127.05,
    "MONETARYFUNDS": 49926813769.81,
    "ACCOUNTS_RECE": 364538360.24,
    "INVENTORY": 61390820964.46,
    "FIXED_ASSET": 21819359530.45,
    "INTANGIBLE_ASSET": 8522163065.22,
    "GOODWILL": None,
    "TOTAL_LIABILITIES": 37883274859.87,
    "TOTAL_CURRENT_LIAB": 37520507877.81,
    "TOTAL_NONCURRENT_LIAB": 362766982.06,
    "SHORT_LOAN": None,
    "LONG_LOAN": None,
    "ACCOUNTS_PAYABLE": 3027434194.1,
    "TOTAL_EQUITY": 280421617022.85,
    "TOTAL_PARENT_EQUITY": 271204740541.63,
    "UNASSIGN_RPOFIT": 219633762376.29,
    "MINORITY_EQUITY": 9216876481.22,
}]

RAW_MAIN = [
    {
        "SECUCODE": "600519.SH",
        "REPORT_DATE": "2026-09-30 00:00:00",
        "NOTICE_DATE": "2026-10-31 00:00:00",
        "EPSJB": 51.53, "EPSXS": 51.53, "BPS": 216.949629787912,
        "MGJYXJJE": 67.242794202432, "ROEJQ": 24.47, "ZZCJLL": 21.4476392899,
        "XSMLL": 89.581093798, "XSJLL": 50.9404935478, "ZCFZL": 11.9015685357,
        "TOTALOPERATEREVETZ": 1.817946648268, "PARENTNETPROFITTZ": -0.246524447439,
        "JYXJLYYSR": 0.641814938896, "CHZZL": 0.222209968587,
        "TOTAL_SHARE": 1250081601, "A_FREE_SHARE": 1250081601,
    },
    {
        "SECUCODE": "600519.SH",
        "REPORT_DATE": "2026-06-30 00:00:00",
        "NOTICE_DATE": "2026-08-15 00:00:00",
        "EPSJB": 34.1, "TOTAL_SHARE": 1250081601, "A_FREE_SHARE": 1250081601,
    },
]


def test_normalize_date():
    assert mapper.normalize_date("2026-09-30 00:00:00") == "2026-09-30"
    assert mapper.normalize_date("2026-06-30") == "2026-06-30"
    assert mapper.normalize_date(None) is None
    assert mapper.normalize_date("") is None
    assert mapper.normalize_date("2026/09/30") is None


def test_to_number():
    assert mapper.to_number(None) is None
    assert mapper.to_number("") is None
    assert mapper.to_number("-") is None
    assert mapper.to_number("1,234.5") == 1234.5
    assert mapper.to_number(3) == 3.0


def test_income_full_mapping():
    rows = mapper.to_rows("income", RAW_INCOME)
    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "600519.SH"
    assert row["period_end"] == "2026-09-30"
    assert row["announce_date"] == "2026-10-31"
    assert row["revenue"] == 130970743649.04
    assert row["net_income_attributable"] == 64467425981.95
    assert row["basic_eps"] == 51.53
    # 16 列全部有值
    missing = [c for c in mapper.COLUMNS["income"] if row[c] is None]
    assert missing == [], f"利润表缺列: {missing}"


def test_balance_sheet_null_stays_none():
    row = mapper.to_rows("balance_sheet", RAW_BALANCE)[0]
    # 茅台没有商誉与借款，null 必须保持 None，不能填 0
    assert row["goodwill"] is None
    assert row["short_term_borrowing"] is None
    assert row["long_term_borrowing"] is None
    assert row["total_current_assets"] == 269646861755.67
    assert row["total_current_liabilities"] == 37520507877.81
    assert row["equity_attributable"] == 271204740541.63
    assert row["retained_earnings"] == 219633762376.29
    filled = [c for c in mapper.COLUMNS["balance_sheet"] if row[c] is not None]
    assert len(filled) == 16  # 19 列里 3 列本就为空


def test_metrics_shares():
    metrics = mapper.to_rows("metrics", RAW_MAIN, latest_only=True)[0]
    assert metrics["roe"] == 24.47
    assert metrics["gross_margin"] == 89.581093798
    assert metrics["debt_to_asset_ratio"] == 11.9015685357
    assert metrics["roe_diluted"] is None  # 上游无此列，保持空

    shares = mapper.to_rows("shares", RAW_MAIN, latest_only=True)[0]
    assert shares["total_shares"] == 1250081601
    assert shares["float_shares"] == 1250081601


def test_latest_only_picks_newest():
    rows = mapper.to_rows("shares", RAW_MAIN, latest_only=False)
    assert len(rows) == 2
    rows = mapper.to_rows("shares", RAW_MAIN, latest_only=True)
    assert len(rows) == 1
    assert rows[0]["period_end"] == "2026-09-30"


def test_symbol_filter_and_sort():
    rows = mapper.to_rows("shares", RAW_MAIN, symbols=["600519.sh"])
    assert len(rows) == 2  # 大小写不敏感命中
    rows = mapper.to_rows("shares", RAW_MAIN, symbols=["000001.SZ"])
    assert rows == []


def test_column_order_shape():
    for table, cols in mapper.COLUMNS.items():
        order = mapper.column_order(table)
        assert order[:3] == ["symbol", "period_end", "announce_date"]
        assert order[3:] == cols


def test_recent_quarter_ends():
    ends = mapper.recent_quarter_ends(5, today=_dt.date(2026, 11, 9))
    assert ends == [
        "2026-09-30", "2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30",
    ]
    # 跨年边界
    ends = mapper.recent_quarter_ends(3, today=_dt.date(2026, 1, 15))
    assert ends == ["2025-12-31", "2025-09-30", "2025-06-30"]
    # 季度末当天仍算当期
    ends = mapper.recent_quarter_ends(1, today=_dt.date(2026, 3, 31))
    assert ends == ["2026-03-31"]


def test_source_fields_include_common():
    fields = mapper.source_fields("income")
    assert {"SECUCODE", "REPORT_DATE", "NOTICE_DATE", "OPERATE_INCOME"} <= fields
    assert "GOODWILL" not in fields  # 属于 balance_sheet


def test_merge_duplicates_prefers_full_row():
    rows = [
        {"SECUCODE": "600519.SH", "REPORT_DATE": "2026-09-30 00:00:00", "OPERATE_INCOME": 1.0},
        {
            "SECUCODE": "600519.SH", "REPORT_DATE": "2026-09-30 00:00:00",
            "OPERATE_INCOME": 2.0, "NETPROFIT": 3.0, "TOTAL_PROFIT": 4.0,
        },
    ]
    out = mapper.to_rows("income", rows)
    assert len(out) == 1
    assert out[0]["revenue"] == 2.0
    assert out[0]["net_income"] == 3.0


def test_table_reports_candidates():
    """三大报表都要有 一般企业/银行/证券/保险 四套模板候选。"""
    for table in ("income", "balance_sheet", "cash_flow"):
        names = mapper.TABLE_REPORTS[table]
        assert isinstance(names, tuple) and len(names) == 4, table
    for table in ("metrics", "shares"):
        assert len(mapper.TABLE_REPORTS[table]) == 1, table


def test_all_tables_cover_contract():
    """五张表的列必须覆盖面板文档列的每一列。"""
    expected = {
        "income": 16,
        "balance_sheet": 19,
        "cash_flow": 5,
        "metrics": 14,
        "shares": 2,
    }
    for table, count in expected.items():
        assert len(mapper.COLUMNS[table]) == count, table
        assert set(mapper.FIELD_MAP[table]) == set(mapper.COLUMNS[table]), table

