# video-analyzer

视频元数据智能分析系统 — 扔一个视频文件进来，自动抽帧分析画面、转写音频内容，最后合成一份完整的 B 站投稿元数据——标题、简介、标签、分区、封面建议、创作声明，全给你准备好。

Video Metadata Intelligence System — drop in a video file and get back a complete Bilibili publishing package: title, intro, tags, category, cover suggestion, and content declaration, all generated automatically from visual and audio analysis.

[![ClawHub](https://img.shields.io/badge/ClawHub-video--analyzer-blue)](https://clawhub.ai/CyberKurry/video-analyzer) [![GitHub](https://img.shields.io/badge/GitHub-CyberKurry%2Fvideo--analyzer-black)](https://github.com/CyberKurry/video-analyzer) [![SkillHub](https://img.shields.io/badge/SkillHub-video--analyzer-orange)](https://skillhub.cn/skills/video-analyzer) [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Version:** 1.0.0 | **Owner:** [CyberKurry](https://github.com/CyberKurry)

---

## ✨ 这是什么

Video Analyzer 从视频文件中自动提取关键帧和音频，用 AI 分别做视觉分析和语音转写，然后把两路结果合并，生成一份完整的、可直接用于 B 站投稿的结构化元数据。

```
视频文件
  │
  ├─→ 🖼️ 抽帧 + 视觉分析 ──→ 画面里有什么？文字是什么？哪帧适合做封面？
  │
  ├─→ 🔊 提取音频 + 转写 ──→ 说了什么？关键信息点有哪些？什么语气？
  │
  └─→ ✍️ 合成元数据 ──→ 标题、简介、标签、分区、封面建议、创作声明
```

视觉和音频**并行处理**，合成阶段等两者都跑完才启动。

## 🚀 快速开始

```bash
bash scripts/run.sh \
  --video 你的视频.mp4 --output /tmp/output \
  --transcribe audio-llm \
  --audio-llm-key YOUR_KEY --audio-llm-base https://api.example.com/v1 --audio-llm-model mimo-v2.5 \
  --vision-llm-key YOUR_KEY --vision-llm-base https://api.example.com/v1 --vision-llm-model mimo-v2.5 \
  --max-frames 15 \
  --synthesize-method api \
  --analyze-llm-key YOUR_KEY --analyze-llm-base https://api.example.com/v1 --analyze-llm-model gpt-5.5
```

一条命令，输出三个文件：

| 文件 | 内容 |
|------|------|
| `observations_visual.json` | 每帧画面的结构化分析（对象、文字、动作、风格、是否适合做封面） |
| `observations_audio.json` | 语音转写全文 + 说话人 + 关键信息点 + 语气 |
| `metadata.json` | 可直接用于投稿的元数据（标题、简介、标签、分区、封面建议、创作声明） |

三个 LLM（视觉 / 音频 / 合成）可以各用各的 key，也可以用同一个。

## 📊 实际效果

**输入：** 一段在市集拍的老北京天桥杂技表演视频（196 秒）

**输出的标题：**
> 徒手托球真的不碎？老北京天桥绝活让我捏把汗

**输出的简介：**
> 去逛市集，偶遇了一场老北京天桥风味的传统杂技表演，看得我手心直冒汗！视频里这位表演的师傅展示了一项极其危险的绝活：徒手托着一个球，主持人反复强调千万别碰到，因为一碰就可能碎掉伤人...

**输出的标签：** 古彩戏法、硬气功、老北京天桥、徒手托球、传统杂技、民间绝活、市集表演、非遗传承

**输出的封面建议：**
> 🥇 第 1 帧 — 红色灯笼和中式雕花门窗氛围感十足，主持人与表演者同框，画面色彩对比鲜明
> 🥈 第 10 帧 — 表演特写镜头

合成 prompt 把 LLM 定位为"资深 B 站内容运营"——标题和简介是给人看的，不是给机器看的。严禁 "深入浅出""全面解析""带你了解" 这类 AI 味空话。

## 🛣️ 两种模式

**外部 LLM API（推荐）：** 给 API key，脚本全自动调 LLM 分析。视觉、音频、合成三个阶段的 key 和 model 可以分别配。

**Agent 直读（无需外部 API）：** 不给 API key，脚本只抽帧和提取音频。Agent 用自己的模型直接看帧、听音频、生成 metadata。

两条线可以混搭——视觉走 API、音频走 Agent 直读，随你组合。缺参数自动降级到 agent-direct，不会崩。

## 🎞️ 智能抽帧

不需要手动设间隔，系统自动算：

| 视频时长 | 策略 | API 调用 |
|---------|------|---------|
| ≤ 4 分钟 | 单段，自适应间隔，15 帧 | 1 次 |
| 30 分钟 | 8 段，每段 15 帧，**段间并行（最多 4 路）** | 8 次并行 |
| 2 小时 | 30 段，最多 4 路并发 | 30 次 |

大帧自动压缩：超过 200KB 的帧自动缩放到 1280px 宽（JPEG quality 85），避免 API payload 过大导致 502。

## 🔊 四种音频转写

| 方式 | 说明 | 需要什么 |
|------|------|---------|
| **audio-llm** 🌟 | 多模态 LLM 直接听音频，输出结构化 JSON（转写+关键点+说话人+语气） | API key + 支持音频的模型 |
| **cloud** | 云端 Whisper API，输出纯文本转写 | `--whisper-api-key` + `--whisper-api-base` |
| **local** | 本地 Whisper，免费 | `pip install openai-whisper` |
| **agent-direct** | 只提取音频文件，让 Agent 自己读 | ffmpeg |

音频处理全自动：WAV 自动压缩成 MP3 → 文件太大自动分片（带 2 秒重叠去重）→ 转写 → 合并。

## ✍️ 合成 Prompt

**标题设计：**
- ✅ `"用 AI Agent 自动审查代码缺陷，我把自家项目翻了个底朝天"`
- ✅ `"ESP32 心率监测器：20 块钱的方案也能跑"`
- ❌ `"AI Agent 技术分享"` — 空泛，没信息量

**简介：** 帮观众判断"这个视频跟我有关吗"。自然语言分段，包含搜索关键词。不是摘要，是预告。

**封面建议：** 基于实际帧内容，说清楚为什么这帧好（信息密度？文字清晰？视觉冲击力？），附备选帧。

**创作声明：** 对齐 B 站网页端六选一单选：`内容无需标注` / `含AI生成内容` / `含虚构演绎内容` / `内容含营销信息` / `个人观点，仅供参考` / `内容为转载`

三种合成方式：
- `api` — 调 LLM 生成（推荐），失败自动退到启发式规则
- `agent` — 输出 prompt 文件，Agent 用自己的模型生成
- `manual` — 输出 Markdown 供人工审阅

## 🛡️ 三层容错

**第 1 层：网络重试** — API 返回 5xx 或断连 → 自动重试 3 次，指数退避

**第 2 层：解析重试** — 模型输出不是合法 JSON？把错误信息喂回去让它重新出。最多 3 轮

**第 3 层：优雅降级** — 视觉：占位观测；音频：保留原始文本；合成：启发式规则。参数缺失自动退到 agent-direct

## 📦 输出格式

### metadata.json

```json
{
  "title": "80字以内，像 UP 主写的标题",
  "intro": "2000字以内，给观众看的视频介绍",
  "tags": ["标签1", "标签2"],
  "category": "B站一级分区",
  "sub_category": "B站二级分区",
  "cover_suggestion": {
    "primary": "推荐帧文件名",
    "reason": "为什么这帧适合做封面",
    "secondary": "备选帧文件名"
  },
  "declaration": "内容无需标注",
  "copyright_claim": false
}
```

### observations_visual.json

每帧一个对象：`frame`（文件名）、`objects`（关键实体）、`desc`（~100字六要素描述）、`texts`（画面文字）、`actions`（动作事件）、`style`（风格标签）、`cover_candidate`（是否适合做封面）

### observations_audio.json

`transcript`（完整转写）、`speakers`（说话人）、`key_points`（3-8 个关键信息点）、`tone`（语气风格）

## 📁 文件结构

```
video-analyzer/
├── SKILL.md                # Agent 技能描述（AgentSkills.io 标准）
├── README.md               # 你正在读的这个
├── TOPOLOGY.md             # 架构拓扑（开发者参考）
├── references/
│   └── REFERENCE.md        # 完整参数表、JSON schema、独立使用示例
└── scripts/
    ├── common.py            # 公共工具（HTTP 重试、媒体时长、JSON 解析）
    ├── run.sh               # 一键编排（并行视觉+音频，然后合成）
    ├── visual.py            # 抽帧 + 视觉观测（自动压缩 + 段间并行）
    ├── transcribe.py        # 音频转写（4 种模式）
    └── analyze.py           # 合成投稿元数据（3 种方式）
```

## 📦 依赖

| 依赖 | 必需 | 用途 |
|------|------|------|
| **ffmpeg / ffprobe** | ✅ | 抽帧、音频提取、压缩 |
| **Python 3.8+** | ✅ | 纯 Python，API 模式不需要额外 pip 包 |
| **Pillow** | 推荐 | 帧图片压缩，没装自动退到 ffmpeg |
| **openai-whisper** | 可选 | 仅 `--transcribe local` 时需要 |
| **外部 LLM API** | 可选 | OpenAI 兼容的 chat completions 端点 |

## 📄 许可证 / License

MIT License — 可自由使用、修改、分发，需保留版权声明和 LICENSE 文件。详见 [LICENSE](LICENSE)。

MIT License — free to use, modify, and distribute with copyright notice retained. See [LICENSE](LICENSE) for details.

## 🔗 链接 / Links

- **ClawHub**: https://clawhub.ai/CyberKurry/video-analyzer
- **SkillHub**: https://skillhub.cn/skills/video-analyzer
- **GitHub**: https://github.com/CyberKurry/video-analyzer
- **Owner**: [CyberKurry](https://github.com/CyberKurry)
