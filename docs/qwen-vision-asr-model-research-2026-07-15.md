# ShotLoom 的 Qwen 视觉与 ASR 模型选型研究

> 调研日期：2026-07-15（Asia/Shanghai）  
> 资料范围：仅阿里云百炼 / DashScope 官方文档与官方模型发布记录。模型能力与稳定别名会更新，上线前应再次检查目标地域的模型列表。

本次读取到的官方页面元数据更新时间：Qwen-Omni 为 2026-07-08，非实时语音识别为 2026-07-14，语音识别模型列表为 2026-07-06，视觉理解模型列表为 2026-07-06。

## 结论

建议把视觉理解与语音识别拆成两条模型链路：

- 视觉镜头分析使用 `qwen3.7-plus`。这是准确的正式 Model ID（不是 `qwen-3.7plus`），截至调研日是百炼官方推荐的旗舰视觉理解模型。
- 全片 ASR 使用 `qwen3-asr-flash-filetrans` 的 DashScope 异步任务接口，并开启 `enable_words=true`。该接口返回结构化的句级与字/词级时间戳，适合作为台词归属镜头、字幕和音频区间检索的时间轴真源。
- 不建议让 `qwen3.5-omni-plus` 单独承担精确 ASR。它适合音视频联合理解、会议纪要、字幕生成和声音语义分析，但官方没有为 Omni 的自然语言回答承诺结构化句/词级对齐精度；模型按提示生成的时间段不应被当成剪辑级精确标注。
- `qwen3-vl-plus` 仍是有效模型，但官方已放到“旧版及其他模型”，新项目不应优先于 `qwen3.7-plus`。

推荐的数据流：

```text
原视频
├── qwen3-asr-flash-filetrans（一次全片异步转写）
│   └── transcript + sentence/word timestamps（毫秒）
└── 镜头检测与切片
    └── qwen3.7-plus（视觉分析、非思考模式结构化 JSON）
        └── 与 ASR 按绝对时间区间求交 → 每镜头台词/声音字段
```

## 1. Qwen-Omni 是否适合当前项目

`qwen3.5-omni-plus` 适合“同时听和看”的语义任务。官方把 Qwen3.5-Omni 的适用场景列为长视频分析、会议纪要、字幕生成、内容审核和音视频交互；HTTP 模型支持文本、音频、图像和视频输入，单次支持最长 3 小时音频或 1 小时视频。视频文件的视觉信息与音频信息分开计费。[Qwen-Omni 官方文档](https://help.aliyun.com/zh/model-studio/qwen-omni)

因此，Omni 对 ShotLoom 的声音类型、环境声、音乐、声画关系、说话情绪等开放式判断有价值。但当前项目真正需要的是可稳定落库和映射镜头的时间轴，Omni 不应是唯一的转写来源。它更适合作为以下可选能力：

- 对 ASR 文本与画面做联合语义解释；
- 识别非语言声音、音乐和声画同步关系；
- 在 ASR 低置信或无对白片段提供补充描述。

如果成本、延迟和一致性优先，第一阶段甚至可以不调用 Omni：`qwen3.7-plus + 专用 ASR` 已覆盖视觉分析与台词时间轴两个核心需求。

## 2. Qwen 是否能做 ASR，以及时间戳能力

可以。百炼提供专用 Qwen-ASR 系列；文件型视频项目优先考虑 `qwen3-asr-flash-filetrans`：

- 非实时 HTTP 异步任务；
- 最长 12 小时、最大 2GB；
- 单次接受 1 个公网可访问的文件 URL；
- 支持 `mp4`、`mov`、`mkv`、`avi`、`flv`、`webm`、`mp3`、`wav`、`aac` 等主流音视频格式；服务端会对大部分格式重采样至 16kHz；
- 支持中文（含多种方言）、英语及多种其他语言；
- 固定返回时间戳，`enable_words=false`（默认）返回句级时间戳，`enable_words=true` 返回字/词级时间戳；时间戳单位为毫秒。

官方结果字段为：

- 句级：`sentences[].begin_time`、`sentences[].end_time`；
- 字/词级：`sentences[].words[].begin_time`、`end_time`、`text`。

字/词级时间戳官方明确支持中文、英语、日语、韩语、德语、法语、西班牙语、意大利语、葡萄牙语和俄语；其他语种不能保证准确性。需要注意，Qwen-ASR 当前不支持说话人分离；若多人访谈必须自动区分说话人，应评估支持 `diarization_enabled` 的 Fun-ASR 或 Paraformer。[非实时语音识别官方指南](https://help.aliyun.com/zh/model-studio/non-realtime-speech-recognition-user-guide)；[语音识别模型列表](https://help.aliyun.com/zh/model-studio/asr-model/)

`qwen3-asr-flash` 的 OpenAI 兼容接口虽然便于处理 5 分钟以内的音频，但官方明确说明该接口不返回时间戳。要获得时间戳，必须使用 `qwen3-asr-flash-filetrans` 的 DashScope 异步接口，而不是 OpenAI Chat Completions 形态。

### “毫秒级字段”不等于“绝对毫秒精度”

官方承诺的是时间戳以毫秒为单位、提供句级和字/词级对齐信息，并未给出所有噪声、音乐覆盖、多人重叠说话情况下的绝对误差上限。因此可以用它准确地定位某段音频中的台词，但上线前仍应以代表性素材测量边界误差；不要把数值单位误读为逐帧或采样级准确保证。

## 3. 如何分析指定视频时间段的音频

推荐“全片转写一次，再按区间映射”：

1. 把原视频或单独导出的音轨放到公网可访问的短期签名 URL / OSS URL。
2. 向 `/api/v1/services/audio/asr/transcription` 提交 `qwen3-asr-flash-filetrans` 异步任务，设置 `enable_words=true`。
3. 下载并持久化结果 JSON（官方返回的 `transcription_url` 默认仅 24 小时有效）。
4. 对目标区间 `[segment_start, segment_end)`，筛选与该区间有重叠的句或词，再按镜头边界裁分。

这样每条时间戳天然是相对原片起点的绝对时间，跨镜头台词也不会因逐镜头重复识别而丢失或重复。

如果因为隐私、文件大小或重试隔离必须先裁剪片段，也可以先用 FFmpeg/PyAV 导出 `[start, end)` 的音频/视频，再送 ASR；返回时间戳相对裁剪片段起点，落库时必须统一加上 `start` 偏移。裁切时建议保留少量前后 padding，并在回写时裁回目标区间，避免句首/句尾被 VAD 截断。这是工程建议，不是官方精度承诺。

本次检索的官方 Filetrans 参数中未发现对原始文件直接指定 `start_time` / `end_time`、只识别其中一段的请求参数，因此不应假定服务端支持区间裁切。

接口限制还包括异步轮询查询默认 20 QPS、最高可扩展至 100 QPS；生产环境可使用 EventBridge 回调，并应校验回调签名和处理重复事件。官方建议长音频使用 OSS URL、2–5 秒轮询间隔，并对噪声音频先做降噪。[非实时语音识别官方指南](https://help.aliyun.com/zh/model-studio/non-realtime-speech-recognition-user-guide)

## 4. 视觉模型名称、能力与接口

### `qwen3.7-plus`

它确实存在，并且是截至 2026-07-15 的官方首推视觉理解模型。官方模型表给出的能力是：

- 输入：文本、图像、视频（**不含音频**）；输出：文本；
- 1M 上下文，最大输出 64k；
- 最长视频 2 小时、最大 2GB；
- 最多 2,048 张图片、64 个视频；
- 支持 Function Calling、内置工具；
- 非思考模式支持结构化输出。

稳定别名是 `qwen3.7-plus`，官方同时列出快照 `qwen3.7-plus-2026-05-26`。官方发布记录显示该系列于 2026-06-01 在国际地域、2026-06-18 在日本地域发布；实际可用性必须以项目 API Key 所属地域为准。[视觉理解模型列表](https://help.aliyun.com/zh/model-studio/vision-model/)；[模型上下架与更新](https://help.aliyun.com/zh/model-studio/newly-released-models)

百炼文档将 Qwen3.7 / 3.6 / 3.5 多模态模型归入 `multimodal-generation` 调用路径，Python SDK 使用 `MultiModalConversation`；也可按官方支持的 OpenAI 兼容多模态接口接入。当前仓库的非 Omni 分支已经使用 `MultiModalConversation.call`，方向上可复用，但需要做真实 API 冒烟测试并核对目标地域端点。

### `qwen3.5-plus` 与 `qwen3-vl-plus`

- `qwen3.5-plus` 是有效的文本+图像+视频模型，不是 Omni；官方表中为 1M 上下文、最长 2 小时视频，但当前旗舰已是 `qwen3.7-plus`。
- `qwen3-vl-plus` 也是有效模型，最长 1 小时 / 2GB 视频，但官方已将 Qwen3-VL 放在“旧版及其他模型”，说明新项目建议使用更新系列。
- `qwen3.5-omni-plus` 才是同时支持文本、音频、图像、视频的全模态模型；它不是专业 ASR 时间戳接口。

## 5. 对当前仓库的迁移建议

不能只把 `.env` 的 `MODEL_NAME` 从 `qwen3.5-omni-plus` 改成 `qwen3.7-plus`，原因如下：

1. 当前 `ai_analyzer.py` 用模型名是否含 `omni` 选择两条完全不同的 API 路径。改名后会进入 `MultiModalConversation` 的 VL 分支。
2. 该 VL 分支当前固定 `fps=5.0`、`max_frames=100`，长于 20 秒的视频会受到 100 帧上限影响；整片/分块分析必须按素材长度、镜头密度和成本重新设计采样策略。
3. `qwen3.7-plus` 不读取音频，现有 prompt 中 `audio.dialogue`、`speaker`、`transcript_timestamps`、`music`、`ambient_sound` 等字段不能继续假定由视觉模型可靠生成。
4. 当前上下文分析会把模型生成的 `global_transcript` 当作台词时间轴权威。迁移后应改为先持久化 ASR 结果，再将对应时间段的 transcript 作为文本上下文交给视觉模型，最后按程序确定性地映射回镜头。
5. 建议新增独立配置，例如 `VISION_MODEL_NAME=qwen3.7-plus`、`ASR_MODEL_NAME=qwen3-asr-flash-filetrans`，不要继续让一个 `MODEL_NAME` 同时代表两类职责。

### 建议实施顺序

1. 先接入全片 ASR 异步任务、结果持久化和时间区间查询；保留现有 Omni 视觉链路。
2. 用一组代表性视频人工标注，测量句级/词级时间戳对镜头边界的误差，并确定 overlap / padding 策略。
3. 新增 `qwen3.7-plus` 视觉适配器，把 ASR 的当前镜头文本作为输入上下文；非思考模式请求结构化 JSON。
4. 对同一批视频 A/B 比较 Omni 与 `qwen3.7-plus + ASR` 的视觉字段质量、台词准确率、延迟与成本。
5. 达标后再切默认配置；Omni 可降级为按需的声音语义增强模型。

## 官方来源索引

- [视觉理解：模型能力、输入模态、视频限制、推荐顺序](https://help.aliyun.com/zh/model-studio/vision-model/)
- [Qwen-Omni：音视频理解方式与输入限制](https://help.aliyun.com/zh/model-studio/qwen-omni)
- [语音识别模型选型、格式、时长与地域](https://help.aliyun.com/zh/model-studio/asr-model/)
- [非实时语音识别：异步接口、时间戳字段与生产限制](https://help.aliyun.com/zh/model-studio/non-realtime-speech-recognition-user-guide)
- [模型上下架与更新：Qwen3.7、Omni、ASR 发布时间](https://help.aliyun.com/zh/model-studio/newly-released-models)
