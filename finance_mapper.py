"""面板财务五表 ↔ 东方财富财报字段映射。

纯函数，不依赖 polars 与宿主，便于单测。
字段名均为 2026-11 实测确认（600519.SH），改上游只改本文件。
"""

# 东财报表名
REPORT_INCOME = "RPT_F10_FINANCE_GINCOME"
REPORT_BALANCE = "RPT_F10_FINANCE_GBALANCE"
REPORT_CASHFLOW = "RPT_F10_FINANCE_GCASHFLOW"
REPORT_MAIN = "RPT_F10_FINANCE_MAINFINADATA"  # 主要指标 + 股本

# 面板 table -> 东财报表名候选（按顺序尝试，取第一个有数据的）
# 一般企业用 G*，银行 B*，证券 S*，保险 I*；不同行业报表科目口径不同。
TABLE_REPORTS = {
    "metrics": (REPORT_MAIN,),
    "income": (
        REPORT_INCOME,
        "RPT_F10_FINANCE_BINCOME",
        "RPT_F10_FINANCE_SINCOME",
        "RPT_F10_FINANCE_IINCOME",
    ),
    "balance_sheet": (
        REPORT_BALANCE,
        "RPT_F10_FINANCE_BBALANCE",
        "RPT_F10_FINANCE_SBALANCE",
        "RPT_F10_FINANCE_IBALANCE",
    ),
    "cash_flow": (
        REPORT_CASHFLOW,
        "RPT_F10_FINANCE_BCASHFLOW",
        "RPT_F10_FINANCE_SCASHFLOW",
        "RPT_F10_FINANCE_ICASHFLOW",
    ),
    "shares": (REPORT_MAIN,),
}

# 面板 canonical 列（顺序即输出列序）
COLUMNS = {
    "income": [
        "revenue", "operating_cost", "operating_profit", "selling_expense",
        "admin_expense", "rd_expense", "financial_expense",
        "non_operating_income", "non_operating_expense", "total_profit",
        "income_tax", "net_income", "net_income_attributable",
        "net_income_deducted", "basic_eps", "diluted_eps",
    ],
    "balance_sheet": [
        "total_assets", "total_current_assets", "total_non_current_assets",
        "cash_and_equivalents", "accounts_receivable", "inventory",
        "fixed_assets", "intangible_assets", "goodwill", "total_liabilities",
        "total_current_liabilities", "total_non_current_liabilities",
        "short_term_borrowing", "long_term_borrowing", "accounts_payable",
        "total_equity", "equity_attributable", "retained_earnings",
        "minority_interest",
    ],
    "cash_flow": [
        "net_operating_cash_flow", "net_investing_cash_flow",
        "net_financing_cash_flow", "capex", "net_cash_change",
    ],
    "metrics": [
        "eps_basic", "eps_diluted", "bps", "ocfps", "roe", "roe_diluted",
        "roa", "gross_margin", "net_margin", "debt_to_asset_ratio",
        "revenue_yoy", "net_income_yoy", "operating_cash_to_revenue",
        "inventory_turnover",
    ],
    "shares": ["total_shares", "float_shares"],
}

# 面板列 -> 东财字段候选（按顺序取第一个非空）
# 空元组表示上游没有等价科目，保留 None 让面板显示「—」，不拿近似值顶替。
FIELD_MAP = {
    "income": {
        "revenue": ("OPERATE_INCOME", "TOTAL_OPERATE_INCOME"),
        "operating_cost": ("OPERATE_COST",),
        "operating_profit": ("OPERATE_PROFIT",),
        "selling_expense": ("SALE_EXPENSE",),
        "admin_expense": ("MANAGE_EXPENSE",),
        "rd_expense": ("RESEARCH_EXPENSE",),
        "financial_expense": ("FINANCE_EXPENSE",),
        "non_operating_income": ("NONBUSINESS_INCOME",),
        "non_operating_expense": ("NONBUSINESS_EXPENSE",),
        "total_profit": ("TOTAL_PROFIT",),
        "income_tax": ("INCOME_TAX",),
        "net_income": ("NETPROFIT",),
        "net_income_attributable": ("PARENT_NETPROFIT",),
        "net_income_deducted": ("DEDUCT_PARENT_NETPROFIT",),
        "basic_eps": ("BASIC_EPS",),
        "diluted_eps": ("DILUTED_EPS",),
    },
    "balance_sheet": {
        "total_assets": ("TOTAL_ASSETS",),
        "total_current_assets": ("TOTAL_CURRENT_ASSETS",),
        "total_non_current_assets": ("TOTAL_NONCURRENT_ASSETS",),
        "cash_and_equivalents": ("MONETARYFUNDS",),
        "accounts_receivable": ("ACCOUNTS_RECE",),
        "inventory": ("INVENTORY",),
        "fixed_assets": ("FIXED_ASSET",),
        "intangible_assets": ("INTANGIBLE_ASSET",),
        "goodwill": ("GOODWILL",),
        "total_liabilities": ("TOTAL_LIABILITIES",),
        "total_current_liabilities": ("TOTAL_CURRENT_LIAB",),
        "total_non_current_liabilities": ("TOTAL_NONCURRENT_LIAB",),
        "short_term_borrowing": ("SHORT_LOAN",),
        "long_term_borrowing": ("LONG_LOAN",),
        "accounts_payable": ("ACCOUNTS_PAYABLE",),
        "total_equity": ("TOTAL_EQUITY",),
        "equity_attributable": ("TOTAL_PARENT_EQUITY",),
        "retained_earnings": ("UNASSIGN_RPOFIT",),  # 东财原始字段名拼写如此
        "minority_interest": ("MINORITY_EQUITY",),
    },
    "cash_flow": {
        "net_operating_cash_flow": ("NETCASH_OPERATE",),
        "net_investing_cash_flow": ("NETCASH_INVEST",),
        "net_financing_cash_flow": ("NETCASH_FINANCE",),
        "capex": ("CONSTRUCT_LONG_ASSET",),  # 购建固定资产等支付的现金
        "net_cash_change": ("CCE_ADD",),
    },
    "metrics": {
        "eps_basic": ("EPSJB",),
        "eps_diluted": ("EPSXS",),
        "bps": ("BPS",),
        "ocfps": ("MGJYXJJE",),
        "roe": ("ROEJQ",),          # 加权净资产收益率，百分点
        "roe_diluted": (),          # 东财无摊薄 ROE 单列，留空
        "roa": ("ZZCJLL",),         # 总资产净利率
        "gross_margin": ("XSMLL",),
        "net_margin": ("XSJLL",),
        "debt_to_asset_ratio": ("ZCFZL",),
        "revenue_yoy": ("TOTALOPERATEREVETZ",),
        "net_income_yoy": ("PARENTNETPROFITTZ",),
        "operating_cash_to_revenue": ("JYXJLYYSR",),
        "inventory_turnover": ("CHZZL",),
    },
    "shares": {
        "total_shares": ("TOTAL_SHARE",),
        "float_shares": ("A_FREE_SHARE",),
    },
}


def normalize_date(value):
    """'2026-09-30 00:00:00' -> '2026-09-30'；无法识别时返回 None。"""
    if not value:
        return None
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return None


def to_number(value):
    """东财的 null / 空串 / '-' 一律归一为 None，其余转 float。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if text in ("", "-", "--", "null", "None"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def pick(row, candidates):
    """按候选顺序取第一个非空值。"""
    for name in candidates:
        if name in row and row[name] is not None:
            return to_number(row[name])
    return None


def recent_quarter_ends(count, today=None):
    """返回最近 count 个季度末（降序，含当期）。

    报告期固定是 03-31 / 06-30 / 09-30 / 12-31，不需要问上游。
    """
    import datetime as _dt

    today = today or _dt.date.today()
    month_end = {3: 31, 6: 30, 9: 30, 12: 31}
    year = today.year
    quarter = (today.month - 1) // 3 + 1
    # 当期季度末还没到，就从上一季算起（报告期只认已结束的季度）
    month = quarter * 3
    if (today.month, today.day) < (month, month_end[month]):
        quarter -= 1
        if quarter == 0:
            quarter, year = 4, year - 1

    ends = []
    for _ in range(count):
        month = quarter * 3
        ends.append(f"{year:04d}-{month:02d}-{month_end[month]:02d}")
        quarter -= 1
        if quarter == 0:
            quarter, year = 4, year - 1
    return ends


def source_fields(table):
    """该表用到的全部东财字段名（用于按模板存在的列裁剪请求）。"""
    names = {"SECUCODE", "REPORT_DATE", "NOTICE_DATE"}
    for candidates in FIELD_MAP[table].values():
        names.update(candidates)
    return names


def _merge_duplicates(items, table):
    """同一 (symbol, period_end) 多行时，保留非空列最多的那行。"""
    columns = COLUMNS[table]
    best = {}
    for item in items:
        key = (item["symbol"], item["period_end"])
        score = sum(1 for c in columns if item.get(c) is not None)
        current = best.get(key)
        if current is None or score > current[0]:
            best[key] = (score, item)
    return [entry[1] for entry in best.values()]


def to_rows(table, raw_rows, symbols=None, latest_only=False):
    """东财原始行 -> 面板标准长表行（list[dict]）。

    table: metrics/income/balance_sheet/cash_flow/shares
    symbols: 仅保留这些标的（None 表示全保留）
    latest_only: 每个标的最多保留最新一期
    """
    if table not in FIELD_MAP:
        raise ValueError(f"unknown financial table: {table}")

    wanted = None
    if symbols:
        wanted = {str(s).strip().upper() for s in symbols if str(s).strip()}

    mapping = FIELD_MAP[table]
    out = []
    for raw in raw_rows or []:
        symbol = str(raw.get("SECUCODE") or "").strip().upper()
        if not symbol:
            continue
        if wanted is not None and symbol not in wanted:
            continue
        period_end = normalize_date(raw.get("REPORT_DATE"))
        if not period_end:
            continue
        item = {
            "symbol": symbol,
            "period_end": period_end,
            "announce_date": normalize_date(raw.get("NOTICE_DATE")),
        }
        for column, candidates in mapping.items():
            item[column] = pick(raw, candidates) if candidates else None
        out.append(item)

    if latest_only:
        latest = {}
        for item in out:
            key = item["symbol"]
            if key not in latest or item["period_end"] > latest[key]["period_end"]:
                latest[key] = item
        out = list(latest.values())

    out = _merge_duplicates(out, table)
    out.sort(key=lambda x: (x["symbol"], x["period_end"]))
    return out


def column_order(table):
    """返回该表的输出列序。"""
    return ["symbol", "period_end", "announce_date"] + COLUMNS[table]
