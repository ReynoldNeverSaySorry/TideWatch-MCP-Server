# TideWatch Video Asset Checklist

## P0：粗剪前必须完成

### 真实产品素材

- [x] 真实 Dashboard 信号复盘录屏（修复回填 bug 后重录）：57.1% / 373 of 388；无账户数据
- [x] 真实 Dashboard 热门最强/最弱榜单录屏；不透明遮罩永久覆盖账户统计与持仓区域
- [x] Dashboard 首页脱敏备份，真实前端 + 浏览器拦截注入 fixture；不进入最终主剪
- [x] 个股详情打开过程，清晰显示四维分析与琥珀色冲突提示
- [x] 信号复盘 Tab，展示真实历史判断、5 日结果和对错状态
- [x] MCP `analyze_stock` schema-accurate 脱敏本地演示；明确标注 fixture，不伪装为生产调用
- [x] `review_signals` 脱敏画面，仅使用已核验的两个 v1 历史案例
- [x] 微信式盘后简报预览，使用脱敏消息壳，无头像、联系人、持仓或账户金额

### 四轮进化数据卡

- [x] v1：威海广泰 `+40/+45 / conflict → -9.3%`（同一股票、两次信号）与锦浪科技 `+92 / conflict → +15.8%`
- [x] v1：`CONFLICT + |SCORE| < 50 → WAIT ADVISED`（护栏建议，不阻止信号入库）
- [x] v2：`82 signals / 52 backfilled`
- [x] v2：`[+25,+50) = 0% (0/4), avg -6.58%`
- [x] v3：`[70,85) = 89.5% (17/19)`
- [x] v3：`[85,95) = 56.3% (9/16)`
- [x] v3：`REVERSAL 30.0% vs NON-REVERSAL 71.6%`
- [x] v3：因子权重变化 `MA5 rising +8→+4 / three bearish candles -8→-12`
- [x] v4：`135 signals / 129 with 5-day outcomes`
- [x] v4：`HIGH CONF 72.1% (49/68) / LOW CONF 47.8% (11/23)`
- [x] v4：`CONFIDENCE < 40 → NEUTRAL`

> 所有数字卡必须同时展示样本数，角落标注 `Historical 5-day outcomes`。

### 闭环动画

- [x] `Analyze`：生成带时间戳的信号
- [x] `Remember`：信号写入 SQLite 时间线
- [x] `Verify`：5d / 10d / 20d 结果回填
- [x] `Reflect`：按方向、评分、体制、置信度、因子拆解
- [x] `Refine`：形成阈值、权重或护栏改动
- [x] `Repeat`：新规则进入下一轮信号

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

- [x] 评分分桶柱状图 `[70,85)` 对 `[85,95)`
- [x] 置信度分层图 `72.1%` 对 `47.8%`
- [x] BUY/SELL 标签收回为 WAIT 的动效
- [x] MA5 降权、三连阴升权的权重刻度动效

## P2：声音与包装

- [x] 英文临时旁白（`assets/audio/narration-en-temp.wav`，保留作回退）
- [x] 英文终版旁白（`assets/audio/narration-en.wav`，macOS Samantha 本地合成）
- [x] 中文字幕时间轴（`assets/audio/subtitles-zh.srt`，29 条，已校正并烧录）
- [x] 潮声环境音（`assets/audio/tide-ambience.wav`，本地程序生成）
- [x] 低频、克制的配乐（`assets/audio/music.wav`，本地程序生成）
- [x] 信号落库、结果回填、规则写入三组轻量音效（本地程序生成占位版）
- [x] 片尾维持银蓝海面与中文字幕收束；按用户要求不加主标语、GitHub 或域名
- [x] 合规小字 `Historical observations, not investment advice.`（已进入全部数据卡）

## 原始素材来源

### TideWatch 仓库

- `src/tidewatch/web/`：当前 Dashboard
- `docs/strategy-evolution.md`：v1-v4 数据依据
- `src/tidewatch/guardrails.py`：行为护栏真实实现
- `data/`：仅可使用脱敏导出，不直接录制生产数据库
- `FACT-CHECK.md`：片中数字、样本口径和允许表述的逐项核验表

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

- [x] 1920×1080，16:9
- [x] H.264 视频 + AAC 音频
- [x] 人声峰值约 -6 dB，配乐不压旁白
- [x] 中文字幕在手机尺寸下可读
- [x] 图表停留时间足够读完数字与样本数
- [x] 无账户金额、Cookie、API Key、访问码或私人联系人
- [x] 所有统计值与 `docs/strategy-evolution.md` 逐项复核
- [x] 输出 `exports/TideWatch-Hackathon-v1.mp4`
- [x] 输出 `exports/TideWatch-Hackathon-v1.srt`

> 2026-09-04：最终母版已换入回填 bug 修复后的真实 Dashboard 录屏；画面抽查确认显示 `57.1%`、`373 / 388`，且账户与持仓数据未进入成片。官方提交规格仍待补齐，当前状态为 master cut，不等同于 submit-ready。

### 2026-09-04 最终导出复核

- [x] 主剪实际引用的 23 个图片、视频与音频素材全部存在，并通过 `ffprobe` 与完整解码
- [x] `ffprobe`：145.000 秒；1920×1080；30 fps；H.264 `yuv420p`；AAC 48 kHz stereo
- [x] 完整音视频解码：无错误输出
- [x] 黑场检测：仅 0–4 秒设计黑场
- [x] 静音检测：无超过 1 秒、低于 -45 dB 的异常静音
- [x] 响度检测：mean `-22.6 dB`；peak `-6.3 dB`
- [x] 全片每 5 秒故事板复核；另对 6s / 47s / 54s / 62s / 68s / 74s / 82s / 88s / 94s / 100s / 113s / 120s / 126s / 132s / 142s 做 15 点原尺寸抽查
- [x] 修复后 Dashboard 数据：`57.1%`、`373 / 388`、看多 `53% (31/58)`、看空 `65% (130/200)`
- [x] 两段真实 Dashboard 素材每 0.5 秒取样复核，共 23 帧；全程无账户、持仓、资金或私人信息闪现
- [x] 片尾无额外主标语、GitHub 或域名；仅保留旁白对应中文字幕
- [x] MP4 SHA-256：`373741be90e36835a1db437e75af7acd004fa8499d77ee37a3d568d289fd6257`
- [x] SRT 与审定字幕逐字节一致，共 29 条
