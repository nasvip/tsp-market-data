# 行情与财务插件（TSP）

给 [Tick Stock Panel](https://github.com/shy3130/tick-stock-panel) 用的**一个插件**，接管四个数据集，全部走公开接口，**不需要任何 API Key、不消耗额度**：

| 数据集 | 上游 | 覆盖 | 兜底 |
|---|---|---|---|
| `depth5` 五档 | 腾讯 `qt.gtimg.cn` 批量 | 一次 400 只 | 新浪 `hq.sinajs.cn` |
| `minute` 分钟K | 新浪 1 分钟 | 单只 1900 根 ≈ 8 个交易日 | — |
| `full_minute` 全量分钟 | 腾讯 `m1` K 线 | 当日全量，全市场约 1.5 分钟 | 新浪当日分钟 |
| `financial` 财务五表 | 东方财富 F10 | 全市场 12 个季度 | — |

## 装法

1. 面板 → 设置 → 导入与备份 → 选 `market_data.zip` → 安装
2. 设置 → 数据源 →「行情与财务（东财+腾讯+新浪）」→ **选择启用能力**，勾选要接管的数据集
3. 逐项点「试拉」验证

能力路由是**按数据集独立**的：你可以只把五档和全量分钟切过来，日K/实时继续走 TickFlow 或 fuyao。

## 财务部分

- 五张表：`income` / `balance_sheet` / `cash_flow` / `metrics` / `shares`
- 输出列：`symbol` / `period_end` / `announce_date` + 各表 canonical 列
- 一般企业 `G*`、银行 `B*`、证券 `S*`、保险 `I*` 四套报表模板自动回退
- `metrics.roe_diluted` 上游无摊薄 ROE 单列，保持空值

## 已知限制

- 分钟历史约 8 个交易日，做更长周期的分钟回测不够。
- 全量分钟不提供成交额（腾讯 m1 接口不给），该列留空，面板均价线会降级显示 `—`。
- 银行报表没有「流动资产合计 / 存货 / 短期借款」等科目，对应列为空，属行业口径差异。
- 所有上游都是非官方公开接口，可能限流或改字段；代码里有 4 req/s 限速、3 次重试、15 分钟缓存。
- 首次财务全表同步约 10 分钟，建议收盘后跑。

## 开发

```powershell
python scripts/validate_manifest.py   # 清单校验（不联网）
python scripts/run_tests.py           # 单测（不联网）
python scripts/smoke.py               # 真实接口冒烟
pwsh ./build.ps1                      # 产出 dist/market_data.zip
```
