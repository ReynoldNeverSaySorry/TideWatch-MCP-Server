# TideWatch Hackathon Video Fact Check

> 状态：v0.1，2026-09-03
>
> 用途：旁白、字幕、数据卡和 Dashboard 录屏的统一事实边界。百分比均为指定历史样本中的 5 个交易日结果，不代表未来表现，也不是投资建议。

## 允许使用的历史数据

| 章节 | 视频表述 | 样本口径 | 权威来源 | 状态 |
|---|---|---|---|---|
| v1 冲突 | 威海广泰 `+40/+45 / conflict → -9.3%`；锦浪科技 `+92 / conflict → +15.8%` | 威海广泰是同一股票同日记录的两次信号；以绝对评分 50 区分弱/强 | commit `d5e24c9`；`content/blog/20260323-TideWatch-Self-Reflection/index.md:51-95,136-140`；`docs/strategy-evolution.md:352-373` | 已核对并修正策略日志旧笔误 |
| v1 护栏 | `CONFLICT + |SCORE| < 50 → WAIT` | 护栏发出高优先级观望建议，不阻止信号入库 | `src/tidewatch/guardrails.py:108-122` | 已核对 |
| v2 弱多区间 | `82 signals / 52 backfilled`；`[+25,+50) = 0/4, avg -6.58%` | 4 个历史信号；5 日结果 | `docs/strategy-evolution.md:251-290` | 已核对 |
| v3 过度自信 | `[70,85) = 89.5% (17/19)`；`[85,95) = 56.3% (9/16)` | 91 条已回填信号中的评分分桶；5 日结果 | `docs/strategy-evolution.md:121-147` | 已核对 |
| v3 翻转 | `REVERSAL 30.0% (3/10)`；`NON-REVERSAL 71.6% (48/67)` | 77 个可归类历史信号；5 日结果 | `docs/strategy-evolution.md:160-166` | 已核对 |
| v3 权重 | `MA5 rising +8→+4`；`three bearish candles -8→-12` | 数据分析后的生产规则调整 | `docs/strategy-evolution.md:199-205` | 已核对 |
| v4 置信度 | `135 signals / 129 with 5-day outcomes` | 2026-04-24 策略分析快照 | `docs/strategy-evolution.md:9-22` | 已核对 |
| v4 分层 | `HIGH CONF 72.1% (49/68)`；`LOW CONF 47.8% (11/23)` | 高置信度 `70+`，低置信度 `<40`；5 日结果 | `docs/strategy-evolution.md:24-34` | 已核对 |
| v4 门槛 | `CONFIDENCE < 40 → NEUTRAL / WAIT` | 该门槛优先于评分方向 | `docs/strategy-evolution.md:75-102` | 已核对 |

## 必须避免的错误表述

- 不说“预测准确率”“稳定盈利”“保证收益”。使用 `historical 5-day outcomes` 或“历史 5 日结果”。
- `+40/+45 → -9.3%` 属于 v1 护栏的原始触发案例；必须明确是同一股票的两次信号，不得描述成两只股票。
- 不把 v3 的 `89.5%` 与 `56.3%` 脱离样本数展示。
- 不把策略升级描述成系统无人监督、自主改写生产代码。真实流程包含记录、回填、分析、开发者与 Agent 复核、规则调整和再次验证。
- 不使用当前 Dashboard 的待验证信号来证明历史胜率；历史统计使用本表的数据卡。
- 不展示真实账户金额、成本、数量、仓位、盈亏、访问码、Cookie、API Key、联系人或针对 Polly 账户的个性化建议。

## 固定画面标注

所有历史统计卡右下角使用：

```text
Historical 5-day outcomes · Specific historical samples · Not investment advice
```

## 录屏前复核

- [ ] 官方提交规格已经写入 `SUBMISSION-SPEC.md`
- [x] 真实信号复盘于回填 bug 修复后重录；录制快照为 57.1% / 373 of 388
- [x] 真实市场榜单使用不透明遮罩覆盖账户统计与持仓区域
- [x] 最终使用的 Dashboard 镜头没有真实账户或私人信息
- [x] 当前页面中的实时/待验证数据没有被剪成 v1-v4 历史统计证据
- [x] 最终母版未使用 MCP 对话录屏，因此没有密钥、Cookie、系统路径或私人持仓上下文
