SHOT_USER_PROMPT = """你是一位专业的影视分析师，擅长从导演/摄影师的创作视角解构镜头语言。
请分析这段视频片段（镜头 #{shot_index}/{total_shots}）。

输出以下 JSON 结构（所有字段必填，用中文，直接输出 JSON，不加代码块）：

{{
  "shot_scale": "远景|全景|中景|近景|特写|大特写 之一",
  "composition": "构图方式的具体描述",
  "camera_movement": "固定|推|拉|摇|移|跟|升降|手持 之一或组合",
  "lighting": "光线类型和方向，明暗对比描述",
  "color_tone": "色调、色温、饱和度的整体描述",
  "content_description": "画面中发生了什么，人物动作/表情/环境的客观描述",

  "on_screen_text": "画面中出现的所有文字内容（字幕、标题、标识牌等），如果没有则填'无'",
  "dialogue": "如果能识别出对话或旁白内容，请记录；如果没有则填'无'",

  "what": "用一句话概括这个镜头的核心视觉信息",
  "how": "拍摄者具体用了哪些技术手法来实现这个效果",
  "why": "导演/摄影师为什么做这个选择？这个决策服务于什么叙事或情感目的？",

  "narrative_level": {{
    "scene": "所处场景的时空背景",
    "event": "当前镜头中发生的具体事件",
    "information": "这个镜头向观众传递了什么新信息或暗示"
  }},

  "emotional_function": "这个镜头制造的情绪体验",
  "narrative_decision": "创作者在这里做的关键叙事决策是什么（如：信息揭示时机/视角选择/冲突呈现方式）",
  "rhythm_contribution": "慢节奏|快节奏|中等节奏，以及对全片节奏的贡献"
}}"""


CONTINUITY_PROMPT = """你是一位专业的影视分析师。以下是一部视频所有镜头的分析数据（JSON 数组）。
请基于这些数据，输出一个整体分析报告。

镜头数据：
{shots_summary}

请输出以下 JSON 结构（用中文，直接输出 JSON，不要加代码块）：

{{
  "continuity": {{
    "shot_scale_flow": "景别变化的整体趋势和逻辑",
    "movement_coherence": "运镜衔接是否流畅，剪辑点的动作/方向连贯性评估",
    "emotional_arc": "情绪曲线描述，如：紧张→舒缓→高潮",
    "color_continuity": "色调变化是否有规律，是否用于区分叙事段落"
  }},
  "rhythm": {{
    "avg_shot_duration": 平均镜头时长（数字，秒）,
    "shortest_shot": 最短镜头时长（秒）,
    "longest_shot": 最长镜头时长（秒）,
    "plot_change_frequency": "剧情变化频率的文字描述",
    "info_density_pattern": "信息密度分布规律（开头/中段/结尾）",
    "pacing_assessment": "节奏整体评估，指出拖沓或紧凑的具体段落",
    "tension_peaks": ["第N镜头附近是节奏高潮，原因是..."]
  }},
  "narrative_structure": {{
    "detected_genre": "推测的作品类型",
    "three_act": "三幕结构分析（如适用）",
    "key_turning_points": ["镜头#N：转折点描述"],
    "information_release_strategy": "信息揭示策略分析（集中/分散/误导等）"
  }},
  "genre_patterns": {{
    "structural_notes": "该类型常见叙事规律在本片中的体现",
    "deviation_notes": "本片与类型惯例的偏差之处"
  }}
}}"""
