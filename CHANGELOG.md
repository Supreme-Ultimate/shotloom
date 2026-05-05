# Changelog

## 0.2.0

### Added
- 短期签名公开视频 URL：大视频可通过 Qwen 可访问的公网 URL 输入，避免 Base64 10MB 限制。
- 自动分析路由：短视频优先整片上下文，长视频自动分块段落，选中镜头重分析仍走单镜头回退。
- 分块上下文分析完成每个 chunk 后会即时写入该 chunk 内镜头结果，并按 chunk 更新进度。
- 二层级段落分析：按对白连续、动作连续、反应链、情绪节拍和叙事功能合并多个镜头。
- 前端新增“段落分析”标签页，并在镜头详情显示分析来源与跨镜头连续性。
- Excel/PDF 导出新增上下文分析来源、声音/动作连续性和段落分析内容。

### Changed
- Qwen Omni 输入模式支持 `auto` / `base64` / `url`，默认小文件 Base64、大文件签名 URL。
- 镜头级结果可由整片/分块上下文生成，缺失镜头自动回退到原有短镜头合并/单镜头分析。
- 分块 prompt 使用当前输入片段的相对时间轴，同时保留原视频时间作为参考，避免镜头内容与段落叙事错位。
- 前端分析进度优先显示后端提供的整片/分块状态文案，不再固定显示单镜头进度。
- 新增上下文路由相关环境变量，便于开源用户按模型、成本和视频大小调整。

## 0.1.0

### Added

- Docker Compose deployment with Postgres, Redis, backend worker, backend API, and frontend.
- User authentication, admin user management, and credit balance management.
- Video upload, shot detection, thumbnail generation, shot analysis, selected-shot analysis, cancellation, and whole-video analysis.
- Qwen Omni OpenAI-compatible multimodal analysis path with audio-aware prompt fields.
- Configurable prompt and analysis-field profiles via `backend/prompt_configs/default.json` and `PROMPT_CONFIG_PATH`.
- PDF and Excel report export.
- Chinese and English README files.
- MIT license, contribution guide, security policy, and audit notes.

### Fixed

- User data isolation so normal users only see their own videos.
- Stale analysis progress reconciliation after worker failures or page refreshes.
- Re-detect flow clearing stale shot lists and updating status immediately.
- Short video clip handling for models with minimum input duration requirements.
- PDF export runtime dependencies and WeasyPrint/pydyf compatibility.
- PDF report image/text layout overlap.
