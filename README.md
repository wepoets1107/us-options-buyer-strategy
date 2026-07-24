# 美股期权买方候选扫描 · US Options Buyer

> 美股个股期权「买方」策略候选扫描器：IV 百分位 · VRP 波动风险溢价 · 定价移动 vs 估计移动 · 三类推荐（买 Call / 买 Put / 双买）
> US single-stock options **buyer** candidate scanner: IV percentile · VRP (vol risk premium) · priced move vs expected move · three callouts (Long Call / Long Put / Long Straddle)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)](https://www.python.org)

---

## 中文说明

### 这是什么

一个纯免费数据源（yfinance + Nasdaq 财报日历）驱动的美股个股期权买方策略扫描器。

它每天扫描 160+ 只高流动性美股，计算每只标的的 IV 百分位、VRP（隐含波动率 − 已实现波动率）、ATM straddle 定价移动、以及基于历史财报实际移动的「估计移动」，再用一套可解释的闸门，把全池筛成三类可执行的买方候选：

- **买 Call**：偏多 + IV 不过分贵
- **买 Put**：偏空 + IV 不过分贵
- **双买（Long Straddle）**：方向不明但估计移动显著大于期权定价移动（事件波动）

### 核心特性

- **零密钥、纯免费**：只用 yfinance（行情/期权链）与 Nasdaq 公开财报日历，无需任何 API key。
- **大样本池**：160+ 只热门美股，分 5 组 —— 大型成长、周期/金融/能源/工业、消费零售、医疗、事件型 ETF。
- **双轴打分**：波动轴（IV 百分位、VRP、定价移动） + 方向/动量轴（催化剂方向、技术动量）+ 流动性轴，分别合成 Call / Put / Straddle 三组评分。
- **可解释闸门**：任何推荐都需「IV 不过分贵」（VRP 闸门）；双买额外要求「估计移动 − 定价移动」为正且足够大（防事件后 IV crush）。
- **实时看板**：Flask 服务，后台线程定时重建快照，前端 30s 轮询 `/api/snapshot` 刷新。首屏内联数据，避免空白。
- **期权链缓存**：2 小时 pickle 缓存，避免 100+ 只每轮重抓被 yfinance 限流。

### 快速开始

```bash
# 1. 准备 Python 3.13+ 虚拟环境
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行（构建快照并启动看板）
python run.py
# 打开 http://127.0.0.1:5041
```

### 配置说明

所有参数集中在 `config.py`（无需任何配置文件）：

- `WATCHLIST`：固定观察池，按 5 个分组组织。
- `PORT`：看板端口（默认 5041）。
- `VRP_OK` / `VRP_STRADDLE_MAX`：IV 不过分贵的通用闸门与双买额外上限。
- `MOVE_EDGE_MIN` / `DIR_SUB_MIN` / `DIR_GAP` / `BIG_GAP`：分类闸门阈值。
- `CALL_PUT_THRESH` / `STRADDLE_THRESH`：评分触发门槛。
- `MIN_DTE` / `MAX_DTE`：买入到期窗口（默认 14~30 天，避开狠 theta）。
- `MIN_OPTION_VOLUME` / `MIN_OPTION_OI` / `MAX_BID_ASK_SPREAD`：流动性硬门槛。

### 目录结构

```
config.py        配置（观察池、端口、全部阈值与权重）
data_feed.py     yfinance 拉取 + SSL 中文路径补丁 + 期权链 2h 缓存
signals.py       IV 百分位 / VRP / 定价移动 / 估计移动 / 单边 call·put 成本
scoring.py       Call / Put / Straddle 三组评分 + 三类分类闸门
catalysts.py     催化剂/事件表（财报日、历史移动中位数）
fetch_calendar.py  Nasdaq 公开财报日历抓取（免密钥）
universe.py      观察池加载与流动性过滤
report.py        快照构建（snapshot.json / snapshot.csv / dashboard.html）
web/app.py       Flask 看板（首屏内联 + /api/snapshot 轮询）
web/index.html   前端（三模块单评分 + 全池明细）
run.py           一键入口：构建快照 -> 启动看板
```

### ⚠️ 风险提示

本项目仅用于研究与学习，所有数据来自公开免费源，不构成任何投资建议。期权买方策略亏损有限但归零概率高，请勿直接用于实盘。

---

## English

### What is this

A US single-stock options **buyer** strategy scanner driven entirely by free data sources (yfinance + Nasdaq earnings calendar).

Every run it scans 160+ highly liquid US stocks, computing each ticker's IV percentile, VRP (implied − realized volatility), ATM straddle priced move, and an "expected move" derived from historical post-earnings actual moves. A set of explainable gates then filters the whole pool into three actionable buyer callouts:

- **Long Call**: bullish bias + IV not excessively rich
- **Long Put**: bearish bias + IV not excessively rich
- **Long Straddle**: unclear direction but expected move materially larger than the option-priced move (event volatility)

### Key features

- **Zero keys, fully free**: Only yfinance (quotes / option chains) and the public Nasdaq earnings calendar — no API key required.
- **Large universe**: 160+ popular US stocks in 5 groups — mega growth, cyclical / financial / energy / industrial, consumer & retail, healthcare, and event ETFs.
- **Dual-axis scoring**: Volatility axis (IV percentile, VRP, priced move) + direction / momentum axis (catalyst direction, technical momentum) + liquidity axis, combined into three separate Call / Put / Straddle scores.
- **Explainable gates**: Every callout requires "IV not excessively rich" (VRP gate); straddles additionally require a positive and sufficiently large expected-move − priced-move edge (guards against post-event IV crush).
- **Live dashboard**: Flask service with a background thread rebuilding the snapshot and a frontend polling `/api/snapshot` every 30s. First paint inlines data to avoid blank pages.
- **Option-chain cache**: 2-hour pickle cache so 100+ tickers don't get rate-limited by yfinance on every rebuild.

### Quick start

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python run.py
# open http://127.0.0.1:5041
```

### Configuration

All parameters live in `config.py` (no config file needed):

- `WATCHLIST`: fixed universe, organized in 5 groups.
- `PORT`: dashboard port (default 5041).
- `VRP_OK` / `VRP_STRADDLE_MAX`: IV-not-too-rich gate and the extra straddle cap.
- `MOVE_EDGE_MIN` / `DIR_SUB_MIN` / `DIR_GAP` / `BIG_GAP`: classification gate thresholds.
- `CALL_PUT_THRESH` / `STRADDLE_THRESH`: score trigger thresholds.
- `MIN_DTE` / `MAX_DTE`: buy expiry window (default 14~30 days, avoiding heavy theta).
- `MIN_OPTION_VOLUME` / `MIN_OPTION_OI` / `MAX_BID_ASK_SPREAD`: hard liquidity floors.

### Project structure

```
config.py         Config (universe, port, all thresholds & weights)
data_feed.py     yfinance fetch + SSL non-ASCII-path patch + 2h chain cache
signals.py       IV percentile / VRP / priced move / expected move / single call·put cost
scoring.py       Call / Put / Straddle scores + three-way classification gates
catalysts.py     Catalyst / event table (earnings dates, historical move median)
fetch_calendar.py  Nasdaq public earnings calendar scraper (keyless)
universe.py      Universe loading & liquidity filter
report.py        Snapshot builder (snapshot.json / snapshot.csv / dashboard.html)
web/app.py       Flask dashboard (inline first paint + /api/snapshot polling)
web/index.html   Frontend (per-module single score + full-pool detail)
run.py           One-shot entry: build snapshot -> launch dashboard
```

### ⚠️ Disclaimer

For research and education only. All data comes from public free sources and does not constitute investment advice. Long-options strategies have limited downside but a high probability of expiring worthless — do not use in production without proper verification.

---

## ☕ 打赏 / Donate

如果这个项目对你有帮助，欢迎打赏支持冰火岛社区持续产出。

If this project helped you, tips are welcome to support the Binghuodao community.

**EVM 钱包 / EVM wallet:**
`0x29f091DAA3dfee8100645ee24239bCC3ae174B42`

（支持 ETH / ARB / BASE / 等 EVM 链 · Supported on ETH / ARB / BASE / any EVM chain）

---

## License

[MIT](LICENSE) © 2026 wepoets1107
