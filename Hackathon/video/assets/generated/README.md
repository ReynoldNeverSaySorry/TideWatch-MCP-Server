# Generated Tide Series

Dream Painter 生成的 TideWatch 五幕概念图。

当前有两套视觉：

- `market-fusion/`：主系列。海潮中直接融入 K 线、数据雨、牛熊市场和回填记忆。
- 根目录与 `16x9/`：Natural Tide 备选系列。更安静，适合章节过场。

## 文件

| 源图 | 含义 | 对应影片段落 |
|---|---|---|
| `01-birth.png` | 青色信号从潮线中诞生 | 序章 / 诞生 |
| `02-conflict.png` | 两股证据冲突，琥珀色警告浮现 | 第一浪 |
| `03-overconfidence.png` | 高而空不如低而稳 | 第三浪 |
| `04-restraint.png` | 红绿方向消散，选择保持平静 | 第四浪 |
| `05-taught-by-the-tide.png` | 多次反馈汇成一条纪律 | 归潮 |

## 尺寸

- 根目录 PNG：`1536×1024`，Dream Painter 原始源图。
- `16x9/` PNG：`1920×1080`，居中裁切后的剪辑版本。

剪辑时默认使用 `16x9/`；需要重新取景或制作 Ken Burns 推拉时使用根目录源图。

## 可复现性

提示词与连续性约束位于 `../../prompts/`。`01-birth.png` 是母版，其余四张均以母版通过图生图生成，使用 `quality=medium` 保留机位与细节。

所有标题、数字和 Logo 均应在剪辑软件中叠加，不写入生成图。