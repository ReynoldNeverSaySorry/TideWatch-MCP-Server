# TideWatch Hackathon 视频方案 v0.2

> **TideWatch**
> **Born to Predict. Taught by the Tide.**
> **生于预测，师从市场。**

## 一、创作命题

多数 AI 在给出答案后就结束了。TideWatch 的故事从答案之后开始：记录信号，等待 5/10/20 个交易日，让市场批改，再把错误沉淀成因子权重、方向阈值与行为护栏。

影片不按功能模块介绍产品，而用四次“潮汐”讲清它如何成长：

1. **The Tide of Conflict**：面对相互矛盾的证据，弱判断不应交易。
2. **The Tide of Ambiguity**：模棱两可的方向不是谨慎，而是噪声。
3. **The Tide of Confidence**：最自信的判断也可能最危险。
4. **The Tide of Honesty**：成熟不是回答更多，而是没把握时保持沉默。

## 二、双线叙事

| 故事线 | 起点 | 过程 | 终点 |
|---|---|---|---|
| 情感线 | 自信、急于回答 | 犯错、受教、自省 | 克制、诚实 |
| 技术线 | 多维分析生成信号 | 记录 → 回填 → 分析 → 改规则 | 可持续验证的策略闭环 |

## 三、叙事节奏

| 章节 | 内容 | 时长 |
|---|---|---:|
| 序章 | AI 的答案会消失 | 0:00-0:15 |
| 诞生 | TideWatch 建立成绩单 | 0:15-0:35 |
| 第一浪 | 冲突与低分护栏 | 0:35-0:58 |
| 第二浪 | 砍掉弱多死亡地带 | 0:58-1:17 |
| 第三浪 | 过度自信、翻转与因子重估 | 1:17-1:44 |
| 第四浪 | 置信度门槛与诚实 | 1:44-2:04 |
| 今日 | 真实产品闭环 | 2:04-2:15 |
| 归潮 | 主题升华与片名回扣 | 2:15-2:25 |

## 四、详细分镜

| # | 时间 | 画面 | 英文旁白 | 中文字幕 | 事实来源 |
|---|---:|---|---|---|---|
| 0 | 0:00-0:04 | 黑场。远处潮声，一条细弱 K 线亮起又熄灭。 | （沉默） | - | 概念镜头 |
| 1 | 0:04-0:15 | 多个 AI 结论卡片快速出现：BUY、SELL、87% CONFIDENT，随后像退潮一样消失。 | Most AI systems make a prediction, then move on. The answer remains. The lesson disappears. | 大多数 AI 做出预测，然后继续向前。答案留下，教训却消失了。 | 主题铺垫 |
| 2 | 0:15-0:25 | TideWatch Dashboard 从黑暗中浮现；技术、资金、消息、市场体制四条数据流汇入。 | TideWatch was born to read the market: price, momentum, money, news, and the market regime around them. | TideWatch 生来用于理解市场：价格、动量、资金、消息，以及它们所处的市场体制。 | 产品架构 |
| 3 | 0:25-0:35 | 一条信号写入时间线，时钟推进 5d、10d、20d，结果回填。闭环圆环第一次合上。 | But it did one thing differently. Every signal became a promise. And the market came back to grade it. | 但它多做了一件事：每个信号都是一次承诺，而市场终会回来批改。 | 信号追踪系统 |
| 4 | 0:35-0:48 | 第一浪覆盖画面。明确标注“同一股票、两次信号”：威海广泰 `+40/+45 / conflict / -9.3%`；并排展示锦浪科技 `+92 / conflict / +15.8%`，绝对评分 50 的门槛在两者之间亮起。 | Its first lesson came from contradiction. Two conflicted calls on the same stock scored plus forty and plus forty-five. Both fell 9.3 percent. Another scored plus ninety-two and rose 15.8. | 第一课来自矛盾：同一只股票的两个冲突信号评分 +40 和 +45，五日均下跌 9.3%；另一个冲突信号评分 +92，五日上涨 15.8%。 | v1 原始提交与博文案例 |
| 5 | 0:48-0:58 | 琥珀色冲突框亮起；规则被写入：`CONFLICT + |SCORE| < 50 → WAIT ADVISED`。 | Lesson one: when evidence conflicts and conviction is weak, do nothing. A mistake became a guardrail. | 第一课：证据冲突、判断不强时，不交易。一次错误，变成一道护栏。 | v1 冲突+低分护栏（高优先级建议，不阻止信号入库） |
| 6 | 0:58-1:10 | 第二浪。82 signals → 52 backfilled；区间图中 `[+25,+50)` 被红色圈出，`0/4`。 | More signals returned. A so-called slightly bullish zone had failed four times out of four, losing 6.58 percent on average. | 更多信号完成回填。所谓“弱多”区间四次全错，平均下跌 6.58%。 | v2 策略日志 |
| 7 | 1:10-1:17 | “BULLISH ≥ +25” 被划掉，改成 “BULLISH ≥ +50”；弱多沉入 WAIT。 | TideWatch stopped softening bad answers. It removed the answer. | TideWatch 不再美化不可靠的答案，而是直接删除这个答案。 | v2 看多门槛 |
| 8 | 1:17-1:31 | 第三浪更高。评分柱图：[70,85) 89.5%，[85,95) 56.3%。高分柱突然坍塌。 | Then came the most unsettling lesson. Near-perfect scores were right only 56.3 percent of the time, while the lower band reached 89.5 percent. | 接着是最反直觉的一课：接近满分的判断只有 56.3% 正确，较低区间却达到 89.5%。 | v3 过度自信分析 |
| 9 | 1:31-1:44 | 三张规则卡依次落下：OVERCONFIDENCE ×0.7、REVERSAL ×0.6、MA5 ↓ / THREE RED CANDLES ↑。 | Confidence was no longer taken at face value. Reversals were penalized. Noisy factors lost weight. Stronger evidence gained it. | 系统不再照单全收自己的自信。方向翻转被惩罚，噪声因子降权，更可靠的证据得到加强。 | v3 置信度与因子调整 |
| 10 | 1:44-1:56 | 第四浪退去，露出 135 signals / 129 backfilled。72.1% 与 47.8% 分屏对照。 | With 135 signals, the hidden variable finally surfaced. High-confidence calls reached 72.1 percent. Low-confidence calls fell to 47.8. | 当信号增长到 135 条，隐藏变量终于浮现：高置信度达到 72.1%，低置信度只有 47.8%。 | v4 置信度分层 |
| 11 | 1:56-2:04 | `confidence < 40` 后，BUY/SELL 标签平静地收回为 WAIT。画面短暂静音。 | So TideWatch learned its hardest lesson: when confidence is low, do not force a direction. | TideWatch 学会了最难的一课：没有把握时，不要强行给出方向。 | v4 P0 门槛 |
| 12 | 2:04-2:15 | 真实 Demo 蒙太奇：MCP 对话 → Dashboard 冲突提示 → 信号复盘 → 微信盘后简报。 | Today, every analysis enters the same loop: predict, remember, verify, reflect, and return stronger. | 今天，每次分析都进入同一个循环：预测、记忆、验证、自省，然后再次出发。 | 当前产品闭环 |
| 13 | 2:15-2:25 | 海面恢复平静，K 线与潮线重合。Logo 与副标题出现。 | It was built to read the market. But only the market could teach it how. TideWatch. Born to predict. Taught by the tide. | 它被创造来理解市场，但只有市场能教会它如何成长。TideWatch，生于预测，师从市场。 | 主题收束 |

## 五、必须让观众记住的三个画面

1. **信号写入后，5/10/20 日结果回来批改**：一分钟内讲清产品闭环。
2. **89.5% 对 56.3% 的柱形坍塌**：制造全片最反直觉的认知冲击。
3. **BUY/SELL 收回为 WAIT**：把“克制”拍成一个可见的产品行为。

## 六、视觉方向

### 基调

- 主色：深海蓝黑、雾白、冷青。
- 警示色：琥珀，仅用于冲突和需要克制的时刻。
- 涨跌色：沿用产品现有 A 股红涨绿跌，不重新发明视觉语义。
- 字体：英文使用有金融编辑感的窄体无衬线；中文使用思源黑体。

### 画面比例

- 约 70%：真实 Dashboard、MCP 对话、数据库回填和策略图表。
- 约 20%：由真实数据重绘的动态图形。
- 约 10%：Market Fusion 金融潮汐、黑场等概念镜头。

### 动效原则

- 每次“浪”进入时，数据覆盖前一版规则；退潮后留下新规则。
- 版本号只作为小字时间标记，不作为章节标题。
- 股票数据雨、牛熊与价值符号只能融入海水、K 线和市场体制叙事；不使用独立雕像、金币堆、实体火箭或庆祝暴涨式画面。
- 图表必须保留样本数，避免只展示百分比。

## 七、声音设计

- 开场只有潮声、时钟和低频脉冲。
- 每次结果回填使用克制的单次落点声，不用赌场提示音。
- 第三浪出现 89.5% / 56.3% 时，音乐第一次抽空。
- `confidence < 40 → WAIT` 时留 0.5-1 秒静默。
- 结尾从机械节拍回到真实海浪，完成“系统向市场学习”的声音回环。

## 八、合规与可信度

- 屏幕角落显示：`Historical observations, not investment advice.`
- 所有百分比同时显示样本数与 `5-day outcome` 口径。
- 不使用“预测准确率”“稳定盈利”等无边界表达。
- v1-v4 均表述为数据分析后由开发者与 Agent 复核并部署，不伪装为系统自主修改生产代码。

## 九、待确认

- [ ] 官方视频时长是否限制在 2:00 内
- [ ] 是否要求真人出镜
- [ ] 英文旁白使用真人还是 AI 声音
- [ ] 演示账户采用哪组脱敏股票
- [ ] 是否需要结尾二维码或 GitHub 地址

## 十、事实核验

逐项来源、样本口径和允许表述见 `FACT-CHECK.md`。任何旁白、字幕或图卡调整都必须同步复核该表。
