# 美股个股期权买方策略 · PLAN

## 0. 定位与边界
- 策略类型：个股 / ETF 期权买方（long call / long put / long straddle 或 strangle）
- 持有窗口：目标第 7 天离场；买入到期选 14-30 DTE（不买 7 DTE，theta 太狠）
- 非预测系统：本质是「催化剂 + 波动率错配」筛选器，输出候选清单 + 评分，不自动下单
- 与 us-etf-strategy 区分：那边是现货持有 / 调仓；这边是期权买方博弈波动，两套东西

## 1. 标的宇宙（固定观察池）
分层清单（初版内置，后续可调），全为期权高流动性标的：
- 巨轮成长 / 高 beta：NVDA TSLA AAPL AMZN META GOOGL MSFT AMD NFLX
- 周期 / 金融 / 能源：JPM XOM CVX BAC
- 事件驱动 ETF：SPY QQQ XLE XLF GLD
（约 20 只）
流动性硬门槛：ATM 期权日均成交量、持仓量、买卖价差过滤（价差过宽直接否）

## 2. 数据层 data_feed.py
- 主源 yfinance（managed venv 已装 0.2.63）
- SSL 补丁：复用 us-etf-strategy 的证书修复 —— 把 certifi 的 cacert.pem 复制到纯英文路径（如项目内 certs/ 或 C:/tmp/ca.pem），启动前注入 CURL_CA_BUNDLE / SSL_CERT_FILE / REQUESTS_CA_BUNDLE 指向它（Windows 用户名含中文时，curl_cffi 读证书路径会挂）
- 拉取内容：
  - 标的历史价格（>= 1 年日线，算 IV 百分位与已实现波动率）
  - 期权链（各到期日、各 strike 的 IV、bid/ask、volume、openInterest、Greeks）
  - 财报日历（yfinance .earnings / earnings_date）
  - 分析师 / 评级（yfinance 覆盖有限，v1 先用价格动量代理）
- 数据缓存：本地 pickle/json 缓存，避免每次全拉（尊重 yfinance 限频）
- 催化剂日历：初版用财报日期 + 手动维护事件表（FDA / 并购 / 宏观），后续可接免费日历 API

## 3. 信号层 signals.py

### A 波动轴（值不值得买）
- A1 IV 百分位：当前 ATM IV 在自身过去 252 交易日 ATM IV 分布中的百分位；< 30% 给高分
  （yfinance 无历史 IV 真值，用「当前 ATM IV 对 trailing 已实现波动率分布」近似，跑后校准）
- A2 VRP：ATM IV - 近 30 日已实现波动率（年化）；为负说明期权被低估，加分
- A3 跨期结构：近月 ATM IV / 次近月 ATM IV；< 1 且临近事件，说明事件前被压低，加分
- A4 定价移动 vs 估计移动：
  - 定价移动 = 0.85 × ATM straddle 净价 / 现价（市场隐含的 1σ 移动）
  - 估计移动 = 基于催化剂幅度的经验估计（初版用历史财报后实际移动中位数，或事件类型查表）
  - 估计 > 定价 → 双买有 edge，双买分加分

### B 方向轴（call 还是 put）
- B1 催化剂方向：财报预期（营收 / 指引向好=多，不及预期=空）、FDA（获批=多，拒批=空）、宏观（鸽派=多风险资产，鹰派=空）
- B2 动量 + 趋势：
  - 5 日收益、20 日收益（正→call 分；负→put 分）
  - 价格相对 20 / 50 日均线位置（站上→call；跌破→put）
  - 近 20 日波动率（高波动→双买分加分）
- B3 偏度 skew：OTM call IV - OTM put IV（同 delta）。看涨偏度极端→买 call 贵（扣分）；看跌偏度极端→买 put 贵（扣分）

### C 适配轴（能不能买）
- C1 流动性：ATM 期权成交量、持仓量、买卖价差（宽→否）
- C2 到期可用：是否存在 14-30 DTE 且流动性足够的近月期权
- C3 卖方拥挤：Put/Call 比极端，作反向参考

## 4. 打分与分类 scoring.py
- 三个输出分（0-100）：call_score、put_score、straddle_score
- 加权（初值，跑后校准）：
  - call_score = w_方向多 × B1 + w_动量多 × B2 + w_便宜 × (A1+A2+A3) + w_流动性 × C1 - w_skew × 看涨偏度
  - put_score 对称
  - straddle_score = w_双买edge × (A4) + w_高波动 × B2波动 + w_方向不明 × (1 - |call-put| 归一) + w_便宜 × A
- 分类规则：
  1. call_score >= 阈值 且 put_score 低 且 IV 便宜 → 买 call 候选
  2. put_score >= 阈值 且 call_score 低 且 IV 便宜 → 买 put 候选
  3. |call_score - put_score| 小 且 straddle_score >= 阈值 且 IV 便宜 → 双买候选
  4. 都不达 → 不碰
- 阈值初值：call/put >= 60，straddle >= 55（待首批数据校准）

## 5. 输出层 report.py + 网页看板
- 本地网页（仿 options-eye 风格，独立端口，避开 5051/5050/5052 → 用 5060）
- 页面内容：
  - 候选总表：标的、推荐方向（call/put/straddle）、三分数、IV 百分位、VRP、催化剂、距催化天数、建议到期、ATM 权利金 / straddle 成本、定价移动 vs 估计移动、流动性评分
  - 三类分栏：买 call 候选 / 买 put 候选 / 双买候选
  - 明细抽屉：该标的期权链快照（近月流动性最好的几个 strike）
  - 今日新增信号：相对昨日新增 / 升级的候选
- 纯前端不自动刷新；手动跑脚本生成快照，网页读快照。或脚本内置定时重算 + 网页轮询（不建系统级常驻，符合规矩）

## 6. 脚本结构（先列，未动手）
```
us-options-buyer-strategy/
  config.py        # 观察池、阈值、权重、端口
  universe.py      # 固定观察池定义 + 流动性门槛
  data_feed.py     # yfinance 拉取 + SSL 补丁 + 缓存
  catalysts.py     # 财报日历 + 手动事件表
  signals.py       # A/B/C 三类信号计算
  scoring.py       # 三分数 + 分类
  report.py        # 生成快照 JSON
  web/             # 网页看板（Flask/FastAPI + Chart.js）
  run.py           # 一键跑：拉数据→算信号→打分→出快照→起网页
```
- 不建自动化常驻（规矩）。跑的方式：手动 `python run.py`，或以后仿 options-eye 做 pythonw 脱离启动器（按需）

## 7. 风险与诚实声明（写进网页页脚）
- 买方天然负 theta，胜率偏低，必须靠「移动 > 成本」盈利
- 本系统不预测，只筛选；信号 ≠ 建议，岛主自行决策
- 财报 IV crush 风险已在过滤中处理，但无法完全规避
- 数据依赖 yfinance 免费源，可能有延迟 / 缺字段

## 8. 下一步（待确认后动手）
1. 确认 PLAN → 建项目骨架（config / universe / data_feed 跑通一只票，验证 yfinance + SSL 补丁）
2. 补 signals / scoring，先出 CSV 验证打分逻辑
3. 接网页看板（端口 5060）
4. 首批数据跑出来校准阈值与权重
