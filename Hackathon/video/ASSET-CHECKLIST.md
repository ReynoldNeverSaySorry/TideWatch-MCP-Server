# TideWatch Video Asset Checklist

## P0：粗剪前必须完成

### 真实产品素材

- [ ] Dashboard 首页全屏录屏，使用演示或脱敏账户
- [ ] 个股详情打开过程，清晰显示四维分析与琥珀色冲突提示
- [ ] 信号复盘 Tab，展示历史判断、5 日结果和对错状态
- [ ] MCP 对话调用 `analyze_stock` 的完整过程
- [ ] `review_signals` 或策略统计结果的脱敏画面
- [ ] Jerry/微信盘后简报画面，隐藏头像、联系人和真实账户金额

### 四轮进化数据卡

- [ ] v1：威海广泰 `+40/+45 → -9.3%` 与锦浪科技 `+92 → +15.8%`
- [ ] v1：`CONFLICT + LOW SCORE = WAIT`
- [ ] v2：`82 signals / 52 backfilled`
- [ ] v2：`[+25,+50) = 0% (0/4), avg -6.58%`
- [ ] v3：`[70,85) = 89.5% (17/19)`
- [ ] v3：`[85,95) = 56.3% (9/16)`
- [ ] v3：`REVERSAL 30.0% vs NON-REVERSAL 71.6%`
- [ ] v3：因子权重变化 `MA5 rising +8→+4 / three bearish candles -8→-12`
- [ ] v4：`135 signals / 129 with 5-day outcomes`
- [ ] v4：`HIGH CONF 72.1% (49/68) / LOW CONF 47.8% (11/23)`
- [ ] v4：`CONFIDENCE < 40 → NEUTRAL`

> 所有数字卡必须同时展示样本数，角落标注 `Historical 5-day outcomes`。

### 闭环动画

- [ ] `Analyze`：生成带时间戳的信号
- [ ] `Remember`：信号写入 SQLite 时间线
- [ ] `Verify`：5d / 10d / 20d 结果回填
- [ ] `Reflect`：按方向、评分、体制、置信度、因子拆解
- [ ] `Refine`：形成阈值、权重或护栏改动
- [ ] `Repeat`：新规则进入下一轮信号

## P1：提升叙事质量

### 概念镜头

- [x] Market Fusion `01-born-to-predict.png`：K 线与数据雨从金融海潮中诞生
- [x] Market Fusion `02-bull-bear-conflict.png`：红色牛势与绿色熊势正面冲突
- [x] Market Fusion `03-overconfidence-crash.png`：冲天高分在峰顶碎裂、脚下坍塌
- [x] Market Fusion `04-choosing-wait.png`：红绿方向退场，只留水平青线
- [x] Market Fusion `05-taught-by-the-market.png`：历史 K 线与回填粒子汇为学习路径
- [x] Natural Tide 五张备选：用于安静过场和结尾呼吸

概念镜头可以实拍、素材库或生成，但不得出现可识别的真实证券价格和虚构收益承诺。

### 图表动效

- [ ] 评分分桶柱状图 `[70,85)` 对 `[85,95)`
- [ ] 置信度分层图 `72.1%` 对 `47.8%`
- [ ] BUY/SELL 标签收回为 WAIT 的动效
- [ ] MA5 降权、三连阴升权的权重刻度动效

## P2：声音与包装

- [ ] 英文临时旁白
- [ ] 英文终版旁白
- [ ] 中文字幕时间轴
- [ ] 潮声环境音
- [ ] 低频、克制的配乐
- [ ] 信号落库、结果回填、规则写入三组轻量音效
- [ ] 结尾 TideWatch Logo 与域名/GitHub
- [ ] 合规小字 `Historical observations, not investment advice.`

## 原始素材来源

### TideWatch 仓库

- `src/tidewatch/web/`：当前 Dashboard
- `docs/strategy-evolution.md`：v1-v4 数据依据
- `src/tidewatch/guardrails.py`：行为护栏真实实现
- `data/`：仅可使用脱敏导出，不直接录制生产数据库

### 博文与封面

以下路径相对于网站工作区根目录：

- `content/blog/20260323-TideWatch-Self-Reflection/cover.jpg`
- `content/blog/20260330-TideWatch-Strategy-Evolution/cover.jpg`
- `content/blog/20260411-TideWatch-Strategy-V3/cover.jpg`
- `content/blog/20260424-TideWatch-Strategy-V4/cover.jpg`

封面适合做章节纹理或转场参考，不代替真实产品画面。

## 建议文件命名

```text
assets/
├── screenshots/
│   ├── 03-signal-backfill.png
│   ├── 05-v1-conflict-guardrail.png
│   ├── 07-v2-threshold.png
│   ├── 09-v3-overconfidence.png
│   ├── 11-v4-confidence-gate.png
│   └── 12-dashboard-review.png
├── screen-recordings/
│   ├── dashboard-overview.mov
│   ├── stock-conflict-detail.mov
│   ├── signal-review.mov
│   └── mcp-analysis.mov
├── charts/
│   ├── v1-conflict-cases.mp4
│   ├── v2-death-zone.mp4
│   ├── v3-overconfidence.mp4
│   └── v4-confidence.mp4
├── generated/
│   ├── 01-birth.png
│   ├── 02-conflict.png
│   ├── 03-overconfidence.png
│   ├── 04-restraint.png
│   ├── 05-taught-by-the-tide.png
│   ├── 16x9/              # Natural Tide 1920x1080 剪辑版本
│   └── market-fusion/
│       ├── source/        # Market Fusion 1536x1024 源图
│       └── 16x9/          # Market Fusion 1920x1080 主剪辑版本
└── audio/
    ├── narration-en.wav
    ├── music.wav
    └── tide-ambience.wav
```

## 导出检查

- [ ] 1920×1080，16:9
- [ ] H.264 视频 + AAC 音频
- [ ] 人声峰值约 -6 dB，配乐不压旁白
- [ ] 中文字幕在手机尺寸下可读
- [ ] 图表停留时间足够读完数字与样本数
- [ ] 无账户金额、Cookie、API Key、访问码或私人联系人
- [ ] 所有统计值与 `docs/strategy-evolution.md` 逐项复核
- [ ] 输出 `exports/TideWatch-Hackathon-v1.mp4`
- [ ] 输出 `exports/TideWatch-Hackathon-v1.srt`
