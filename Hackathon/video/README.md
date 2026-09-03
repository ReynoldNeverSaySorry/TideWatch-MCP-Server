# TideWatch Hackathon Video

> **片名**: TideWatch
> **副标题**: Born to Predict. Taught by the Tide.
> **中文**: 生于预测，师从市场。
> **状态**: Pre-production v0.3（Market Fusion 主视觉完成）
> **建议时长**: 2:20-2:30
> **建议语言**: 英文旁白 + 中文字幕

## 影片定位

这不是一支“AI 选股功能展示”，而是一支关于 AI 如何接受现实反馈、修正自己并学会克制的成长短片。

- **主角**：TideWatch
- **老师**：真实市场
- **教材**：每一条被记录并回填的信号
- **冲突**：系统有能力给出答案，却未必应该给出答案
- **成长**：错误从结果变成规则，规则再接受下一轮验证

## 文档

| 文件 | 用途 |
|---|---|
| `VIDEO-PLAN.md` | 故事弧线、详细分镜、节奏与视觉原则 |
| `NARRATION.md` | 可直接录音的英文旁白与中文字幕 |
| `ASSET-CHECKLIST.md` | 截图、录屏、图表、概念镜头和导出清单 |

## 制作目录约定

```text
video/
├── README.md
├── VIDEO-PLAN.md
├── NARRATION.md
├── ASSET-CHECKLIST.md
├── prompts/              # 视觉圣经 + 五幕可复现提示词
├── assets/
│   ├── screenshots/       # Dashboard、信号复盘、MCP 对话
│   ├── screen-recordings/ # 完整闭环操作录屏
│   ├── charts/            # 由真实数据重绘的动态图表
│   ├── generated/         # 3:2 高分辨率源图 + 16x9/ Full HD 剪辑图
│   └── audio/             # 配音、配乐、音效
└── exports/               # 成片与字幕
```

素材目录在实际素材产生时创建，避免空目录占位。

## Market Fusion 主系列

| 文件 | 故事节点 | 建议用途 |
|---|---|---|
| `assets/generated/market-fusion/16x9/01-born-to-predict.png` | 生于预测 | 开场、产品诞生 |
| `assets/generated/market-fusion/16x9/02-bull-bear-conflict.png` | 牛熊冲突 | v1 行为护栏 |
| `assets/generated/market-fusion/16x9/03-overconfidence-crash.png` | 过度自信崩塌 | v3 数据反转高潮 |
| `assets/generated/market-fusion/16x9/04-choosing-wait.png` | 主动等待 | v4 低置信度归为观望 |
| `assets/generated/market-fusion/16x9/05-taught-by-the-market.png` | 师从市场 | 结尾片名与副标题 |

`market-fusion/source/` 保留 `1536×1024` Dream Painter 源图；`market-fusion/16x9/` 是居中裁切并放大后的 `1920×1080` 剪辑版本。该系列将 K 线、行情曲线、数据雨、牛熊市场与海潮融合，是默认剪辑素材。

原 `assets/generated/16x9/` 五张自然潮汐版继续保留，适合黑场、呼吸段落和章节间的低调过场。

## 一句话故事

TideWatch 生来用于预测市场，但真正教会它成长的，是市场对每一次预测的回答。

## 事实边界

- 历史胜率只描述指定样本与时间窗口，不暗示未来收益。
- “自我进化”指记录、回填、分析、人工/Agent 复核、代码调整与再次验证组成的闭环，不表述为无人监督自动改写生产策略。
- 片中账户、持仓、访问凭证全部使用演示数据或脱敏素材。

## 下一步

1. 锁定 Hackathon 官方时长和画幅要求。
2. 从生产 Dashboard 录制脱敏素材。
3. 根据 `ASSET-CHECKLIST.md` 制作四轮进化数据卡。
4. 先录临时旁白，再按声音节奏做粗剪。
5. 粗剪后复核所有数字、字幕和合规表述。
