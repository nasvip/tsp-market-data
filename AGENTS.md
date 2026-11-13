# AGENTS.md — tsp-market-data

Tick Stock Panel 的**合并版**数据源插件：一个包接管 `depth5` / `minute` / `full_minute` / `financial` 四项。

## 这是什么

合并自两个独立插件（`tsp-free-quote` 行情 + `tsp-financial-plugin` 财务）。
上游分别是腾讯/新浪（行情）与东方财富（财报），都是公开接口、不需要 Key。

## 目录

```
plugin.yaml       清单：datasets 四项
provider.py       门面：Provider 统管四组方法 + test_dataset 分发
quote_client.py   腾讯/新浪行情（五档、分钟、当日 m1）
finance_client.py 东财财报（按报告期批量 + 单只兜底）
finance_mapper.py 东财字段 → 面板五表字段映射
tests/            行情解析 + 财务映射，均不联网
```

## 契约要点

- `get_depth_batch(symbols)` → `{symbol: {bid_prices, bid_volumes, ask_prices, ask_volumes, timestamp}}`，
  数量单位**手**，`timestamp` 毫秒
- `get_minute` / `iter_minute` / `get_intraday_batch` →
  `[symbol, datetime(北京墙钟), open, high, low, close, volume, amount]`，
  `volume` 手、`amount` 元（可空）
- `get_financials(table, symbols, latest_only)` → `symbol / period_end / announce_date` + canonical 列
- 类属性 `minute_history_days = 7`

## 构建与测试

```powershell
python scripts/validate_manifest.py   # 清单校验（不联网）
python scripts/run_tests.py           # 两个测试文件一起跑（不联网）
python scripts/smoke.py               # 真实接口冒烟
pwsh ./build.ps1                      # 产出 dist/market_data.zip
```

改完 `plugin.yaml` 先跑 `validate_manifest.py`；重新打包必须升版本号，否则面板拒绝覆盖。

## 注意事项

1. 腾讯行情串是 **GBK**，必须 `decode("gbk")`；新浪同理。
2. 五档字段索引固定：腾讯 9~18 买、19~28 卖；新浪 10~19 买、20~29 卖（量是**股**，要 ÷100）。
3. 全量分钟用 `mkline` 的 `m1`（真 OHLC），**不要**用分时接口（OHLC 会退化）。
4. 逐只接口必须并发（`WORKERS=16`），串行拉全市场会慢一个数量级。
5. 财务走「按报告期批量」，不要改回逐只，否则全市场同步会从分钟级变成小时级。
6. 东财 `columns` 里带上模板没有的字段会整体报错，先用 `template_fields` 探测再裁剪。
7. 上游都是非官方接口，失败要显式抛 `ProviderRequestError`，不要吞成空数据。
