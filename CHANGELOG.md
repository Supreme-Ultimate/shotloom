# Changelog

## 0.2.0

### Added
- 自动分析路由：短视频优先整片上下文，长视频自动分块段落，选中镜头重分析仍走单镜头回退。
- 二层级段落分析：按对白连续、动作连续、反应链、情绪节拍和叙事功能合并多个镜头。
- 前端新增“段落分析”标签页，并在镜头详情显示分析来源与跨镜头连续性。
- Excel/PDF 导出新增上下文分析来源、声音/动作连续性和段落分析内容。

### Changed
- 镜头级结果可由整片/分块上下文生成，缺失镜头自动回退到原有短镜头合并/单镜头分析。
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
